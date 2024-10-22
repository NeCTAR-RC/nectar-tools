import contextlib
import importlib
import logging
import sys

from nectar_tools.audit.cmd import slack
from nectar_tools import cmd_base
from nectar_tools import exceptions

LOG = logging.getLogger(__name__)


@contextlib.contextmanager
def slack_context(command):
    args = command.args
    if args.slack_categories:
        config = slack.SlackConfig(args.slack_config, no_notify=args.no_notify)
        config.configure_handlers(args.slack_categories)
        try:
            yield command
        finally:
            config.unconfigure_handlers()
    else:
        yield command


class AuditCmdBase(cmd_base.CmdBase):
    def __init__(self):
        super().__init__(log_filename='audit.log')
        self.list_not_run = self.args.list
        self.limit = self.args.limit
        extra_args = self.get_extra_args()

        if self.args.check:
            try:
                module_str, class_method_str = self.args.check.split(':')
                class_str, method_str = class_method_str.split('.')
                module = importlib.import_module(module_str)
                auditor_class = getattr(module, class_str)
                auditor = auditor_class(
                    ks_session=self.session,
                    dry_run=self.dry_run,
                    limit=self.limit,
                    **extra_args,
                )
                method = getattr(auditor, method_str)
                with slack_context(self):
                    method()
                    summary = getattr(auditor, 'summary')
                    summary()
                sys.exit(0)
            except exceptions.LimitReached:
                LOG.info("Limit has been reached")
                sys.exit(0)
            except Exception as e:
                LOG.exception(e)
                sys.exit(1)

    def get_extra_args(self):
        return {}

    def run_audits(self, **kwargs):
        for auditor in self.AUDITORS:
            a = auditor(
                ks_session=self.session, dry_run=self.dry_run, limit=self.limit
            )
            a.run_all(list_not_run=self.list_not_run, **kwargs)

    def add_args(self):
        super().add_args()
        self.parser.add_argument(
            '-l',
            '--list',
            action='store_true',
            help="List audits but don't run them",
        )

        self.parser.add_argument(
            '--limit',
            type=int,
            default=0,
            help='Only process this many eligible items.',
        )
        self.parser.add_argument(
            '--slack-categories',
            type=str,
            help='Send slack notifications for these'
            'categories.  Takes a comma separated list of'
            'names that match sections in the slack '
            'config file.',
        )
        # In the long term, we may fold this into the main config file.
        self.parser.add_argument(
            '--slack-config',
            type=str,
            default="/etc/nectar/slack_config.ini",
            help='Pathname for the slack config file.',
        )
        # In the long term, we might want to support notifications via
        # other kinds of messaging.  We could then replace this with an
        # option to select different drivers ... including one that just
        # writes to stdout.
        self.parser.add_argument(
            '--slack-debug',
            action='store_true',
            dest='no_notify',
            help='Disable Slack audit notifications. '
            'When disabled (e.g. for testing), the '
            'notification text is written to stdout.',
        )
        self.parser.add_argument(
            'check', nargs='?', help="specific check to run"
        )
