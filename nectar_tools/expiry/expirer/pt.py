import datetime
from dateutil.relativedelta import relativedelta
from email.mime import text as mime_text
import enum
import jinja2
import logging
import os
import re
import smtplib

from nectar_tools import auth
from nectar_tools import config
from nectar_tools.expiry import exceptions
from nectar_tools.expiry import expiry_states

from nectar_tools.expiry.expirer import base


CONF = config.CONFIG
LOG = logging.getLogger(__name__)

PT_RE = re.compile(r'^pt-\d+$')
USAGE_LIMIT_HOURS = 4383  # 6 months in hours


class CPULimit(enum.Enum):
    UNDER_LIMIT = 0
    NEAR_LIMIT = 1
    AT_LIMIT = 2
    OVER_LIMIT = 3


class PTExpirer(base.Expirer):

    def __init__(self, project, ks_session=None, now=datetime.datetime.now(),
                 dry_run=False):
        super(PTExpirer, self).__init__(project, ks_session, now, dry_run)
        self.project_set_defaults()
        self.n_client = auth.get_nova_client(ks_session)

    def project_set_defaults(self):
        self.project.owner = getattr(self.project, 'owner', None)
        self.project.expiry_status = getattr(self.project, 'expiry_status', '')
        self.project.expiry_next_step = getattr(self.project,
                                                'expiry_next_step', '')
        self.project.status = getattr(self.project, 'status', '')
        self.project.expires = getattr(self.project, 'expires', '')

    def should_process_project(self):
        has_owner = self.project.owner is not None
        personal = self.is_personal_project()
        if personal and not has_owner:
            LOG.warn("Project %s (%s) has no owner", self.project.id,
                     self.project.name)
        return personal and has_owner and not self.is_ignored_project()

    def is_personal_project(self):
        return PT_RE.match(self.project.name)

    def is_ignored_project(self):
        status = self.get_status()
        if status is None:
            return False
        elif status == 'admin':
            LOG.debug('Project %s is admin. Will never expire',
                      self.project.id)
            return True
        elif status.startswith('ticket-'):
            url = 'https://support.ehelp.edu.au/helpdesk/tickets/%s' \
                  % status.rsplit('-', 1)[1]
            LOG.debug('Project %s is ignored. See %s', self.project.id, url)
            return True
        return False

    def process(self):
        if not self.should_process_project():
            raise exceptions.InvalidProjectTrial()

        status = self.get_status()
        LOG.debug("Processing project %s (%s) status: %s",
                  (self.project.name, self.project.id, status))

        if status in [expiry_states.ARCHIVED, expiry_states.ARCHIVE_ERROR]:
            if self.project_at_next_step_date():
                self.delete_resources()

        elif status == expiry_states.SUSPENED:
            if self.project_at_next_step_date():
                self.archive_project()

        elif status == expiry_states.ARCHIVING:
            LOG.debug('Checking archive status')
            self.check_archiving_status()
        else:
            try:
                limit = self.check_cpu_usage()
                return self.notify(limit)
            except Exception as e:
                LOG.error("Failed to get usage for project %s",
                          self.project.id)
                LOG.error(e)

    def get_status(self):
        status = self.project.expiry_status
        if not status:
            # Legacy
            status = self.project.status
            if status:
                self._update_project(expiry_status=self.project.status,
                                     status='')
                self.project.expiry_status = self.project.status
        return status or 'OK'

    def get_next_step_date(self):
        expiry_next_step = self.project.expiry_next_step
        if not expiry_next_step:
            # expires is legacy
            expiry_next_step = self.project.expires
            if expiry_next_step:
                self._update_project(expiry_next_step=self.project.expires,
                                     expires='')
                self.project.expiry_next_step = self.project.expires

        if not expiry_next_step:
            LOG.warning('No "next step" date set')
            return None
        try:
            return datetime.datetime.strptime(expiry_next_step,
                                              base.DATE_FORMAT)
        except ValueError:
            LOG.error('Invalid expiry_next_step date: %s for project %s',
                      (expiry_next_step, self.project.id))
        return None

    def project_at_next_step_date(self):
        expires = self.get_next_step_date()
        if expires and expires <= self.now:
            LOG.debug('Ready for next step (%s)', expires)
            return True
        else:
            LOG.debug('Not yet ready for next step (%s)', expires)
            return False

    def check_cpu_usage(self):
        limit = USAGE_LIMIT_HOURS
        start = datetime.datetime(2011, 1, 1)
        end = self.now + relativedelta(days=1)
        usage = self.n_client.usage.get(self.project.id, start, end)
        cpu_hours = getattr(usage, 'total_vcpus_usage', None)

        LOG.debug("Total VCPU hours: %s", cpu_hours)

        if cpu_hours < limit * 0.8:
            return CPULimit.UNDER_LIMIT
        elif cpu_hours < limit:
            return CPULimit.NEAR_LIMIT
        elif cpu_hours < limit * 1.2:
            return CPULimit.AT_LIMIT
        elif cpu_hours >= limit * 1.2:
            return CPULimit.OVER_LIMIT

    def notify(self, event):
        limits = {
            CPULimit.UNDER_LIMIT: lambda *x: False,
            CPULimit.NEAR_LIMIT: self.notify_near_limit,
            CPULimit.AT_LIMIT: self.notify_at_limit,
            CPULimit.OVER_LIMIT: self.notify_over_limit
        }
        if event != CPULimit.UNDER_LIMIT:
            LOG.debug(event)
        return limits[event]()

    def notify_near_limit(self):
        if self.get_status() == expiry_states.QUOTA_WARNING:
            return False

        LOG.info("%s: Usage is over 80 - setting status to quota warning",
                 self.project.name)
        self.send_email('first')
        self._update_project(expiry_status=expiry_states.QUOTA_WARNING)
        return True

    def notify_at_limit(self):
        if self.get_status() == expiry_states.PENDING_SUSPENSION:
            LOG.debug("Usage OK for now, ignoring")
            return False

        LOG.info("usage is over 100%%, setting status to "
                 "pending suspension for %s", self.project.name)
        self.nova_archiver.zero_quota()
        new_expiry = self.now + relativedelta(months=1)
        new_expiry = new_expiry.strftime(base.DATE_FORMAT)
        self._update_project(expiry_status=expiry_states.PENDING_SUSPENSION,
                             expiry_next_step=new_expiry)
        self.send_email('second')
        return True

    def notify_over_limit(self):
        if self.get_status() != expiry_states.PENDING_SUSPENSION:
            return self.notify_at_limit()
        if not self.project_at_next_step_date():
            return False

        LOG.info("Usage is over 120%%, suspending project %s",
                 self.project.name)

        self.nova_archiver.zero_quota()
        self.nova_archiver.stop_project()
        new_expiry = self.now + relativedelta(months=1)
        new_expiry = new_expiry.strftime(base.DATE_FORMAT)
        self._update_project(expiry_status=expiry_states.SUSPENED,
                             expiry_next_step=new_expiry)
        self.send_email('final')
        return True

    def send_email(self, status):
        recipient = self.project.owner.email
        if not self.project.owner.enabled:
            LOG.warning('User %s is disabled. Not sending email.', recipient)
            return

        text = self.render_template(status)
        if text is None:
            return

        subject, text = text.split('----', 1)

        msg = mime_text.MIMEText(text)
        msg['From'] = CONF.expiry.email_from
        msg['To'] = recipient
        msg['Subject'] = subject

        if not self.dry_run:
            LOG.info('sending email to %s: %s', (recipient, subject.rstrip()))
            try:
                s = smtplib.SMTP(CONF.expiry.smtp_host)
                s.sendmail(msg['From'], [recipient], msg.as_string())
            except smtplib.SMTPRecipientsRefused as err:
                LOG.error('Error sending email: %s', str(err))
            finally:
                s.quit()
        else:
            LOG.info('would send email to %s: %s', (recipient,
                                                    subject.rstrip()))

    def render_template(self, status):

        tmpl = ''
        if status == 'first':
            tmpl = 'first-notification.tmpl'
        elif status == 'second':
            tmpl = 'second-notification.tmpl'
        elif status == 'final':
            tmpl = 'final-notification.tmpl'
        template_dir = os.path.realpath(os.path.join(os.path.dirname(__file__),
                                                     '../templates'))
        env = jinja2.Environment(loader=jinja2.FileSystemLoader(template_dir))
        try:
            template = env.get_template(tmpl)
        except jinja2.TemplateNotFound:
            LOG.error('Template "%s" not found. '
                      'Make sure status is correct.', tmpl)
            return None

        template = template.render({'project': self.project})
        return template
