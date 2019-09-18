from email.mime import text as mime_text
from freshdesk.v2 import api as fd_api
import jinja2
import logging
import os
import smtplib

from nectar_tools import config


CONF = config.CONFIG
LOG = logging.getLogger(__name__)


class Notifier(object):

    def __init__(self, project, template_dir, subject, dry_run=False):
        self.project = project
        self.dry_run = dry_run
        self.template_dir = template_dir
        self.subject = subject

    def send_message(self, stage, owner, extra_context={},
                     extra_recipients=[]):
        raise NotImplementedError()

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


class FreshDeskNotifier(Notifier):

    def __init__(self, project, template_dir, group_id, subject,
                 dry_run=False):
        super(FreshDeskNotifier, self).__init__(
            project, template_dir, subject, dry_run)

        self.api = fd_api.API(CONF.freshdesk.domain, CONF.freshdesk.key)
        self.group_id = int(group_id)

    def _create_ticket(self, email, cc_emails, description, extra_context={},
                       tags=[]):
        if self.dry_run:
            LOG.info('%s: Would create ticket, requester=%s, cc=%s',
                     self.project.id, email, cc_emails)
            ticket_id = 'NEW-ID'
        else:
            ticket = self.api.tickets.create_outbound_email(
                subject=self.subject,
                description=description,
                email=email,
                email_config_id=int(CONF.freshdesk.email_config_id),
                group_id=self.group_id,
                cc_emails=cc_emails,
                tags=tags)
            ticket_id = ticket.id
            LOG.info("%s: Created ticket %s, requester=%s, cc=%s",
                     self.project.id, ticket_id, email, cc_emails)

        return ticket_id

    def _update_ticket(self, ticket_id, text, cc_emails=[]):
        if self.dry_run:
            LOG.info("%s: Would send reply to ticket %s", self.project.id,
                     ticket_id)
        else:
            self.api.comments.create_reply(ticket_id, text,
                                           cc_emails=cc_emails)
            LOG.info("%s: Sent reply to ticket %s", self.project.id, ticket_id)

    def _update_ticket_requester(self, ticket_id, owner):
        if self.dry_run:
            LOG.info("%s: Would update ticket requester to %s",
                     self.project.id, owner)
        else:
            # Update ticket owner without checking if the owner is changed
            # as it needs more api calls otherwise(get_ticket then get_contact)
            self.api.tickets.update_ticket(ticket_id, email=owner)
            LOG.info("%s: Update ticket requester to %s", self.project.id,
                     owner)

    def _add_note_to_ticket(self, ticket_id, text):
        if self.dry_run:
            LOG.info("%s: Would add private note to ticket %s",
                     self.project.id, ticket_id)
        else:
            self.api.comments.create_note(ticket_id, text)
            LOG.info("%s: Added private note to ticket %s", self.project.id,
                     ticket_id)


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
        msg['From'] = CONF.notifier.email_from
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
                s = smtplib.SMTP(CONF.notifier.smtp_host)
                s.sendmail(msg['From'], extra_recipients, msg.as_string())
            except smtplib.SMTPRecipientsRefused as err:
                LOG.error('Error sending email: %s', str(err))
            finally:
                s.quit()
        else:
            LOG.info('Would send email to %s, cc=%s: %s',
                     owner, extra_recipients, self.subject.rstrip())
