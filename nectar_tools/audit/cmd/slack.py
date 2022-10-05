import json
import logging
import pathlib
import re

import requests

from nectar_tools import config

CONF = config.CONFIG

LOG = logging.getLogger(__name__)

# The Slack notification mechanism uses LogHandlers to filter and
# transform the log events.  The filtering is configurable via a
# separate config file.  The methodology and much of the code is
# could be refactored to support other kinds of audit notification.
#
# The current implementation will emit one Slack notification for
# each log event that passes the filtering.
#
# The current implementation stores the notified log events in a
# flat file that is loaded at the start of the next run.  When the 'cron'
# host is containerized, it will be necessary to persist the state
# outside of the container.  The simple way would be to PUT and GET
# the file to Swift in a wrapper script.  Another option would be to
# store the log events in a database.
#
# Future:
#
#  - Implement a way to aggregate the notifications; e.g. per 'category'
#    or per Slack group
#  - Generalize to support other notification channels using a single config
#    file for all.
#  - Change things so that the log handlers can be configured via a python
#    logging config file.  This will entail reworking the way that logging
#    is configured in nectar_tools/log.py.


class SlackConfigError(Exception):
    pass


# There is a Notifier base class in the nectar_tools.notifier module,
# but it is designed for uses-cases where a templated (HTML) message is
# to be sent to a specific user; e.g. as email or via Freshdesk as a
# ticket.  Our use-case here is different in almost every respect.

class SlackNotifier(object):

    def __init__(self, handler):
        self.handler = handler

    def send(self, record):
        alt = getattr(record, 'alternative_message', None)
        if alt:
            text = alt % record.args if record.args else alt
        else:
            text = record.getMessage()

        group = self.handler.group
        if group:
            if '{' in group:
                extra = getattr(record, 'extra', {})
                group = group.format(**extra)
            text = "@%s - %s" % (group, text)

        LOG.debug(f"Slack message is '{text}'")
        if self.handler.conf.no_notify:
            print(text)
        else:
            try:
                body = {
                    "type": "mrkdwn",
                    "text": text,
                    "link_names": 1,
                }
                r = requests.post(self.handler.webhook, json.dumps(body))
                if r.status_code >= 400:
                    if isinstance(r.reason, bytes):
                        try:
                            reason = r.reason.decode("utf-8")
                        except UnicodeDecodeError:
                            reason = r.reason.decode("iso-8859-1")
                    else:
                        reason = r.reason
                    logging.error("Slack POST failed: "
                                  f"status_code={r.status_code}, "
                                  f"reason = {reason}")
            except ConnectionError as e:
                logging.exception("Problem connecting to Slack", e)


class SlackFilterSpec(object):
    """This class represents a 'filter_n' line in the config file."""

    def __init__(self, filter_text, key, separator_1, separator_2):
        self.extra_regexes = {}
        self.arg_regexes = []
        self.message_regex = None
        self.alternative_message = None

        filter_text = filter_text.strip()
        if not filter_text:
            raise SlackConfigError(f"Empty filter spec for '{key}'")
        for pair in filter_text.split(separator_1):
            parts = pair.split(separator_2)
            if len(parts) != 2:
                raise SlackConfigError(
                    f"Expected key-value pair but got '{pair}' "
                    f"in filter spec for '{key}'")
            k, v = parts
            k = k.strip()
            v = v.strip()
            if len(k) == 0 or len(v) == 0:
                raise SlackConfigError(
                    f"Key or value missing for '{pair}' "
                    f"in filter spec for '{key}'")
            if k == 'msg':
                self.message_regex = re.compile(v)
            elif k == 'alt':
                self.alternative_message = v
            elif k.isnumeric():
                arg_no = int(k)
                if arg_no >= len(self.arg_regexes):
                    # Pad out array with 'None'
                    for i in range(len(self.arg_regexes), arg_no + 1):
                        self.arg_regexes.append(None)
                self.arg_regexes[arg_no] = re.compile(v)
            else:
                self.extra_regexes[k] = re.compile(v)
        if self.message_regex is None:
            raise SlackConfigError(
                f"No 'msg=<regex>' in filter spec for '{key}'")

    def filter(self, record):
        if not self.message_regex.match(record.msg):
            return False

        for i in range(0, len(self.arg_regexes)):
            arg_re = self.arg_regexes[i]
            if arg_re and (i >= len(record.args)
                           or not arg_re.match(str(record.args[i]))):
                return False
        extra = getattr(record, 'extra', {})
        for k, r in self.extra_regexes.items():
            if k not in extra or not r.match(str(extra[k])):
                return False
        return True


class hashable_record(dict):
    def __init__(self, msg, args, extra):
        self['msg'] = msg
        self['args'] = tuple((str(a) for a in args))
        self['extra'] = extra

    def __hash__(self):
        return hash((self['msg'], self['args'],
                     tuple(self['extra'].items())))

    def __eq__(self, other):
        return (self['msg'] == other['msg']
                and self['args'] == other['args']
                and self['extra'] == other['extra'])


class SlackLogHandler(logging.Handler):
    def __init__(self, conf, category, webhook, channel, group, levelno,
                 logname, filters, incremental):
        super().__init__(levelno)
        self.set_name(logname)
        self.webhook = webhook
        self.channel = channel
        self.group = group
        self.category = category
        self.notifier = SlackNotifier(self)
        self.incremental = incremental
        self.conf = conf

        # NB the superclass has a 'filters' attribute with 'and' semantics.
        self.or_filters = filters

        self.records = set()
        self.previous_records = set()
        if self.incremental:
            self.dir_path = pathlib.Path(self.conf['DEFAULT'].state_dir)
            if not self.dir_path.is_dir():
                raise RuntimeError(f"Audit state directory: '{self.dir_path}'"
                                   " does not exist or isn't a directory")
            self.state_path = pathlib.Path(
                self.dir_path, f"{category}-state.json")
            if self.state_path.exists() and not self.conf.reset:
                LOG.debug("Loading state from %s", self.state_path)
                with open(self.state_path, 'r') as f:
                    self.previous_records = set((
                        hashable_record(r['msg'], r['args'], r['extra'])
                        for r in json.load(f)))

    def filter(self, record):
        if not super().filter(record):
            return False
        if not self.or_filter(record):
            return False
        # Suppress records that we notified last time, and also
        # deduplicate them
        info = hashable_record(record.msg, record.args,
                               getattr(record, 'extra', {}))
        res = (info not in self.previous_records
               and info not in self.records)
        self.records.add(info)
        return res

    def or_filter(self, record):
        if len(self.or_filters) == 0:
            return True
        for f in self.or_filters:
            if f.filter(record):
                if f.alternative_message:
                    setattr(record, 'alternative_message',
                            f.alternative_message)
                return True
        return False

    def emit(self, record):
        LOG.debug(f"Sending Slack message for category {self.category} "
                  f"to channel {self.channel}")
        self.notifier.send(record)

    def complete(self):
        if self.incremental and not self.conf.no_notify:
            temp = pathlib.Path(f"{str(self.state_path)}.new")
            LOG.debug("Saving state to %s", temp)
            with open(temp, 'w') as f:
                json.dump(tuple(self.records), f)
            LOG.debug("Renaming %s to %s", temp, self.state_path)
            temp.replace(self.state_path)


class SlackConfig(config.ConfigBase):

    FILTER_RE = re.compile(r'^filter_(\d+)$')

    def __init__(self, config_file, no_notify=False, reset=False):
        """The 'no_notify' flag suppresses the Slack notifications.
        The 'reset' flag causes the notification state files to be
        ignored.
        """

        super().__init__()
        if not config_file:
            raise SlackConfigError("No Slack config filename provided")
        self.read(config_file)
        self.handlers = []
        self.no_notify = no_notify
        self.reset = reset

    def sort_key(self, fk):
        return int(self.FILTER_RE.match(fk).group(1))

    def create_handlers(self, categories):
        """Construct a list of LogHandler objects corresponding to
        the 'categories' argument, based on the info in this SlackConfig.
        """

        res = []
        for category in categories:
            if category not in self:
                raise SlackConfigError(
                    f"Can't find category '{category}' in Slack config")
            section = self[category]
            separator_1 = section.get('separator_1', ',')
            separator_2 = section.get('separator_2', '=')
            webhook = section.get('slack_webhook', None)
            if not webhook:
                try:
                    webhook = CONF.slack.slack_webhook
                except AttributeError:
                    webhook = None
            if not webhook:
                raise SlackConfigError(
                    "Cannot find a Slack webhook in either the Slack config "
                    "or the main nectar_tools config")
            channel = section.get('slack_channel', None)
            group = section.get('slack_group', None)
            level = section.get('log_level', 'NOTSET')
            levelno = logging._checkLevel(level)
            logname = section.get('log_name', '')
            incremental = section.get('incremental', '') == 'True'

            # The filters need to in numeric order ...
            filter_keys = sorted(
                [k for k in section.keys() if self.FILTER_RE.match(k)],
                key=lambda fk: self.sort_key(fk))
            filters = [
                SlackFilterSpec(section[k], f"[{category}]: {k}",
                                separator_1, separator_2)
                for k in filter_keys]

            res.append(SlackLogHandler(self, category, webhook, channel, group,
                                       levelno, logname, filters, incremental))
        return res

    def configure_handlers(self, categories_arg):
        """Create log handlers for the categories chosen and add them
        to the 'nectar_tools' logger.
        """

        if len(self.handlers) > 0:
            raise SlackConfigError("Handlers already configured")

        categories = categories_arg.split(',')
        root = logging.getLogger('nectar_tools')
        self.handlers = self.create_handlers(categories)
        for h in self.handlers:
            root.addHandler(h)

    def unconfigure_handlers(self):
        """Complete and remove previously configured log handlers from
        the root logger.
        """

        root = logging.getLogger('nectar_tools')
        for h in self.handlers:
            h.complete()
            root.removeHandler(h)
        self.handlers = []
