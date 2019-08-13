import jinja2
import logging

from nectar_tools import auth
from nectar_tools import config
from nectar_tools import notifier


CONF = config.CONFIG
LOG = logging.getLogger(__name__)


class ExpiryNotifier(notifier.FreshDeskNotifier):

    def __init__(self, resource_type, resource, template_dir, group_id,
                 subject, ks_session=None, dry_run=False):
        super(ExpiryNotifier, self).__init__(
            resource_type, resource, template_dir, group_id, subject, dry_run)
        self.k_client = auth.get_keystone_client(ks_session)
        self.g_client = auth.get_glance_client(ks_session)
        self.n_client = auth.get_nova_client(ks_session)

    def send_message(self, stage, owner, extra_context={},
                     extra_recipients=[]):
        if stage == 'first':
            tmpl = 'first-warning.tmpl'
        elif stage == 'second':
            tmpl = 'second-warning.tmpl'
        elif stage == 'final':
            tmpl = 'final-warning.tmpl'
        elif stage == 'archived':
            tmpl = 'archived.tmpl'
        text = self.render_template(tmpl, extra_context)

        ticket_id = self._get_ticket_id()

        if ticket_id > 0:
            self._update_ticket(ticket_id, text, cc_emails=extra_recipients)
        else:
            ticket_id = self._create_ticket(email=owner,
                                            cc_emails=extra_recipients,
                                            description=text,
                                            extra_context=extra_context,
                                            tags=['expiry'])
            self._set_ticket_id(ticket_id)
            try:
                details = self.render_template(
                    '%s-details.tmpl' % self.resource_type, extra_context)

                self._add_note_to_ticket(ticket_id, details)

            except jinja2.TemplateNotFound:
                LOG.info("Skip adding note for ticket %s, %s-details.tmpl \
                         template is not found", ticket_id, self.resource_type)

    def finish(self, message=None):
        ticket_id = self._get_ticket_id()
        if ticket_id:
            if message:
                self._add_note_to_ticket(ticket_id, message)

            if not self.dry_run:
                # Status 4 == Resolved
                LOG.info("%s: Resolving ticket %s", self.resource.id,
                         ticket_id)
                self.api.tickets.update_ticket(ticket_id, status=4)
            else:
                LOG.info("%s: Would resolve ticket %s", self.resource.id,
                         ticket_id)

    def _set_ticket_id(self, ticket_id):
        if not self.dry_run:
            if self.resource_type == 'project':
                self.k_client.projects.update(self.resource.id,
                    expiry_ticket_id=str(ticket_id))
            elif self.resource_type == 'image':
                self.g_client.images.update(self.resource.id,
                    nectar_expiry_ticket_id=str(ticket_id))
                # use "nectar_" prefix for image property protection
            elif self.resource_type == 'instance':
                self.n_client.servers.set_meta(self.resource.id,
                    {'expiry_ticket_id': str(ticket_id)})
        msg = '%s: Setting expiry_ticket_id=%s' % (self.resource.id,
                                                   ticket_id)
        LOG.debug(msg)

    def _get_ticket_id(self):
        try:
            if self.resource_type == 'project':
                return int(getattr(self.resource, 'expiry_ticket_id', 0))
            elif self.resource_type == 'image':
                return int(getattr(self.resource,
                                   'nectar_expiry_ticket_id', 0))
            elif self.resource_type == 'instance':
                return int(self.resource.metadata.get(
                           'expiry_ticket_id', 0))
        except ValueError:
            return 0
