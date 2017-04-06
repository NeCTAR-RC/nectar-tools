from email.mime import text as mime_text
from freshdesk.v2 import api as fd_api
import jinja2
import logging
import os
import smtplib

from nectar_tools import auth
from nectar_tools import config


CONF = config.CONFIG
LOG = logging.getLogger(__name__)


class Notifier(object):

    def __init__(self, project, template_dir, ks_session=None, dry_run=False):
        self.project = project
        self.k_client = auth.get_keystone_client(ks_session)
        self.managers = None
        self.members = None
        self.dry_run = dry_run
        self.template_dir = template_dir

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

    def finish(self):
        """Called when expiry is finsh

        Clean up any notifications
        """
        return

    def get_recipients(self):
        """Returns a tuple of recipients and ccs """

        managers = self._get_project_managers()
        members = self._get_project_members()

        manager_emails = []
        member_emails = []
        for manager in managers:
            if manager.enabled and manager.email:
                manager_emails.append(manager.email.lower())
        for member in members:
            if member.enabled and member.email and \
               member.email.lower() not in manager_emails:
                member_emails.append(member.email.lower())

        if not manager_emails:
            manager_emails = member_emails
            member_emails = []

        return (manager_emails, member_emails)

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
                                                     'templates',
                                                     self.template_dir))
        env = jinja2.Environment(loader=jinja2.FileSystemLoader(template_dir))
        try:
            template = env.get_template(tmpl)
        except jinja2.TemplateNotFound:
            LOG.error('Template "%s" not found. Looked in %s',
                      tmpl, template_dir)
            return None
        context = {'project': self.project}
        context.update(extra_context)
        template = template.render(context)
        return template


class FreshDeskNotifier(Notifier):

    def __init__(self, project, template_dir, group_id, subject,
                 ks_session=None, dry_run=False):
        super(FreshDeskNotifier, self).__init__(
            project, template_dir, ks_session, dry_run)

        self.api = fd_api.API(CONF.freshdesk.domain, CONF.freshdesk.key)
        self.group_id = int(group_id)
        self.subject = subject

    def send_message(self, stage, extra_context={}, extra_recipients=[]):
        if stage == 'first':
            tmpl = 'first-warning.tmpl'
        elif stage == 'second':
            tmpl = 'second-warning.tmpl'
        elif stage == 'final':
            tmpl = 'final-warning.tmpl'
        text = self.render_template(tmpl, extra_context)

        ticket_id = self._get_ticket_id()

        if ticket_id < 1:
            ticket_id = self._create_ticket(extra_context)
            LOG.info("Created ticket %s", ticket_id)
            self._set_ticket_meta(ticket_id)

        self._update_ticket(ticket_id, text, extra_recipients)

    def finish(self, message=None):
        ticket_id = self._get_ticket_id()
        if ticket_id:
            if message:
                self._add_note_to_ticket(ticket_id, message)

            if not self.dry_run:
                # Status 4 == Resolved
                LOG.info("%s: Resolving ticket %s", self.project.id, ticket_id)
                self.api.tickets.update_ticket(ticket_id, status=4)
            else:
                LOG.info("%s: Would resolve ticket %s", self.project.id,
                         ticket_id)

    def _set_ticket_meta(self, ticket_id):
        if not self.dry_run:
            self.k_client.projects.update(self.project.id,
                                          expiry_ticket_id=str(ticket_id))
        msg = '%s: Setting expiry_ticket_id=%s' % (self.project.id,
                                                   ticket_id)
        LOG.debug(msg)

    def _get_ticket_id(self):
        try:
            return int(getattr(self.project, 'expiry_ticket_id', 0))
        except ValueError:
            return 0

    def _create_ticket(self, extra_context={}):
        managers = self._get_project_managers()
        members = self._get_project_members()
        extra_context.update({'managers': managers, 'members': members})

        description = self.render_template(
            'ticket-description.tmpl', extra_context=extra_context)
        if self.dry_run:
            LOG.info('Would create ticket')
            return 'NEW-ID'
        else:
            LOG.info('Creating new Freshdesk ticket')
            ticket = self.api.tickets.create_ticket(
                description=description,
                subject=self.subject,
                email=CONF.freshdesk.agent_email,
                group_id=self.group_id,
                tags=['expiry'])
            return ticket.id

    def _update_ticket(self, ticket_id, text, extra_recipients=[]):
        managers, members = self.get_recipients()
        recipients = managers + members

        for extra in extra_recipients:
            if extra.lower() not in recipients:
                recipients.append(extra.lower())

        if recipients:
            if self.dry_run:
                LOG.info("Would send reply to ticket %s", ticket_id)
                LOG.info("Ticket recipients %s", recipients)
            else:
                LOG.info("Sending reply to ticket %s", ticket_id)
                self.api.comments.create_reply(ticket_id, text,
                                               cc_emails=recipients)
        else:
            LOG.error("%s: No members or managers to send reply to")

    def _add_note_to_ticket(self, ticket_id, text):
        if self.dry_run:
            LOG.info("Would add note to ticket %s '%s'", ticket_id, text)
        else:
            LOG.info("Adding note to ticket %s", ticket_id)
            self.api.comments.create_note(ticket_id, text)
