from email.mime import text as mime_text
from freshdesk.v2 import api as fd_api
import jinja2
import logging
import os
import smtplib

from nectar_tools import auth
from nectar_tools import config

from nectar_tools.expiry import common


CONF = config.CONFIG
LOG = logging.getLogger(__name__)


class Notifier(object):

    def __init__(self, project, ks_session=None, dry_run=False):
        self.project = project
        self.k_client = auth.get_keystone_client(ks_session)
        self.managers = None
        self.members = None
        self.dry_run = dry_run

    def _get_project_managers(self):
        if self.managers is None:
            role = CONF.expiry.manager_role_id
            self.managers = self._get_users_by_role(role)
        return self.managers

    def _get_project_members(self):
        if self.members is None:
            role = CONF.expiry.member_role_id
            self.members = self._get_users_by_role(role)
        return self.members

    def _get_users_by_role(self, role):
        members = self.k_client.role_assignments.list(
            project=self.project, role=role)
        users = []
        for member in members:
            users.append(self.k_client.users.get(member.user['id']))
        return users

    def get_recipients(self):
        """Returns a tuple of recipients and ccs """

        users = self._get_project_managers()
        cc_users = self._get_project_members()

        recipients = []
        ccs = []
        for user in users:
            if user.enabled and user.email:
                recipients.append(user.email)
        for user in cc_users:
            if user.enabled and user.email and user.email not in recipients:
                ccs.append(user.email)

        if not recipients:
            recipients = ccs
            ccs = []

        return (recipients, ccs)

    def send_email(self, subject, text, users=[]):
        if not users:
            recipients, ccs = self.get_recipients()
        else:
            recipients = [u.email for u in users if u.enabled]
            ccs = []

        if not recipients:
            LOG.warning('Users %s are disabled. Not sending email.', users)
            return

        msg = mime_text.MIMEText(text)
        msg['From'] = CONF.expiry.email_from
        msg['To'] = ", ".join(recipients)
        msg['Subject'] = subject
        if ccs:
            msg['cc'] = ", ".join(ccs)

        if not self.dry_run:
            LOG.info('sending email to %s: %s',
                     recipients + ccs, subject.rstrip())
            try:
                s = smtplib.SMTP(CONF.expiry.smtp_host)
                s.sendmail(msg['From'], recipients + ccs, msg.as_string())
            except smtplib.SMTPRecipientsRefused as err:
                LOG.error('Error sending email: %s', str(err))
            finally:
                s.quit()
        else:
            LOG.info('Would send email to %s: %s',
                     recipients + ccs, subject.rstrip())
        return text, recipients + ccs

    def render_template(self, tmpl, extra_context={}):
        template_dir = os.path.realpath(os.path.join(os.path.dirname(__file__),
                                                     './templates'))
        env = jinja2.Environment(loader=jinja2.FileSystemLoader(template_dir))
        try:
            template = env.get_template(tmpl)
        except jinja2.TemplateNotFound:
            LOG.error('Template "%s" not found. Make sure status is correct.',
                      tmpl)
            return None
        context = {'project': self.project}
        context.update(extra_context)
        template = template.render(context)
        return template


FD_DOMAIN = 'dhdnectartest.freshdesk.com'
FD_KEY = 'qQCgV563bRnZg7tNJdQ'


class FreshDeskNotifier(Notifier):

    def __init__(self, project, ks_session=None, dry_run=False):
        super(FreshDeskNotifier, self).__init__(project, ks_session, dry_run)
        self.api = fd_api.API(CONF.freshdesk.domain, CONF.freshdesk.key)

    def send_message(self, stage, extra_context={}):
        if stage == 'first':
            tmpl = 'allocations/first-warning.tmpl'
        elif stage == 'second':
            tmpl = 'allocations/second-warning.tmpl'
        elif stage == 'final':
            tmpl = 'allocations/final-warning.tmpl'
        text = self.render_template(tmpl, extra_context)

        ticket_id = getattr(self.project, 'expiry_ticket_id', None)

        if not ticket_id:
            subject = 'Allocation Expiry: Project %s' % self.project.name
            description = 'Allocation expiry for %s (%s)' % (
                self.project.name, self.project.id)
            ticket_id = self._create_ticket(subject, description)
            LOG.info("Created ticket %s", ticket_id)

        self._update_ticket(ticket_id, text)

    def _set_ticket_meta(self, ticket_id):
        if not self.dry_run:
            self.k_client.projects.update(self.project.id,
                                          expiry_ticket_id=ticket_id)
        msg = '%s: Setting expiry_ticket_id=%s' % (self.project.id,
                                                   ticket_id)
        LOG.debug(msg)

    def _create_ticket(self, subject, text):
        to, cc = self.get_recipients()
        if self.dry_run:
            LOG.info('Would create ticket')
            return 'NEW-ID'
        else:
            LOG.info('Creating new Freshdesk ticket')
            ticket = self.api.tickets.create_ticket(
                description=text,
                subject=subject,
                email=CONF.freshdesk.agent_email,
                priority=4,
                status=6,
                tags=['expiry'])
            return ticket.id

    def _update_ticket(self, ticket_id, text):
        to, cc = self.get_recipients()
        if self.dry_run:
            LOG.info("Would send reply to ticket %s", ticket_id)
            LOG.info("Ticket recipients %s", to + cc)
        else:
            LOG.info("Sending reply to ticket %s", ticket_id)
            self.api.comments.create_reply(ticket_id, text, cc_emails=to + cc)
