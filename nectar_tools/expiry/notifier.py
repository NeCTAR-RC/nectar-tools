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

    def __init__(self, project, template_dir, subject, ks_session=None,
                 dry_run=False):
        self.project = project
        self.k_client = auth.get_keystone_client(ks_session)
        self.dry_run = dry_run
        self.template_dir = template_dir
        self.subject = subject

    def finish(self):
        """Called when expiry is finsh

        Clean up any notifications
        """
        return

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


class EmailNotifier(Notifier):

    def send_message(self, stage, owner, extra_context={},
                     extra_recipients=[]):
        if stage == 'first':
            tmpl = 'first-warning.tmpl'
        elif stage == 'second':
            tmpl = 'second-warning.tmpl'
        elif stage == 'final':
            tmpl = 'final-warning.tmpl'
        text = self.render_template(tmpl, extra_context)

        msg = mime_text.MIMEText(text)
        msg['From'] = CONF.expiry.email_from
        msg['To'] = owner
        msg['Subject'] = self.subject
        if extra_recipients:
            msg['cc'] = ", ".join(extra_recipients)

        if not self.dry_run:
            LOG.info('sending email to %s, cc=%s: %s',
                     owner, extra_recipients, self.subject.rstrip())
            try:
                if owner not in extra_recipients:
                    extra_recipients.append(owner)
                s = smtplib.SMTP(CONF.expiry.smtp_host)
                s.sendmail(msg['From'], extra_recipients, msg.as_string())
            except smtplib.SMTPRecipientsRefused as err:
                LOG.error('Error sending email: %s', str(err))
            finally:
                s.quit()
        else:
            LOG.info('Would send email to %s, cc=%s: %s',
                     owner, extra_recipients, self.subject.rstrip())


class FreshDeskNotifier(Notifier):

    def __init__(self, project, template_dir, group_id, subject,
                 ks_session=None, dry_run=False):
        super(FreshDeskNotifier, self).__init__(
            project, template_dir, subject, ks_session, dry_run)

        self.api = fd_api.API(CONF.freshdesk.domain, CONF.freshdesk.key)
        self.group_id = int(group_id)

    def send_message(self, stage, owner, extra_context={},
                     extra_recipients=[]):
        if stage == 'first':
            tmpl = 'first-warning.tmpl'
        elif stage == 'second':
            tmpl = 'second-warning.tmpl'
        elif stage == 'final':
            tmpl = 'final-warning.tmpl'
        text = self.render_template(tmpl, extra_context)

        ticket_id = self._get_ticket_id()

        if ticket_id > 0:
            self._update_ticket(ticket_id, text, cc_emails=extra_recipients)
        else:
            ticket_id = self._create_ticket(email=owner,
                                            cc_emails=extra_recipients,
                                            description=text,
                                            extra_context=extra_context)
            LOG.info("Created ticket %s", ticket_id)
            self._set_ticket_id(ticket_id)

            details = self.render_template(
                'project-details.tmpl', extra_context)

            self._add_note_to_ticket(ticket_id, details)

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

    def _set_ticket_id(self, ticket_id):
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

    def _create_ticket(self, email, cc_emails, description, extra_context={}):
        if self.dry_run:
            LOG.info('Would create ticket, requester=%s, cc=%s', email,
                     cc_emails)
            ticket_id = 'NEW-ID'
        else:
            LOG.info('Creating new Freshdesk ticket')
            ticket = self.api.tickets.create_outbound_email(
                subject=self.subject,
                description=description,
                email=email,
                email_config_id=int(CONF.freshdesk.email_config_id),
                group_id=self.group_id,
                cc_emails=cc_emails,
                tags=['expiry'])
            ticket_id = ticket.id

        return ticket_id

    def _update_ticket(self, ticket_id, text, cc_emails=[]):
        if self.dry_run:
            LOG.info("Would send reply to ticket %s", ticket_id)
        else:
            LOG.info("Sending reply to ticket %s", ticket_id)
            self.api.comments.create_reply(ticket_id, text,
                                           cc_emails=cc_emails)

    def _add_note_to_ticket(self, ticket_id, text):
        if self.dry_run:
            LOG.info("Would add private note to ticket %s", ticket_id)
        else:
            LOG.info("Adding private note to ticket %s", ticket_id)
            self.api.comments.create_note(ticket_id, text)
