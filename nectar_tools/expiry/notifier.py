import logging

from nectar_tools import auth
from nectar_tools import config
from nectar_tools import exceptions
from nectar_tools import notifier


CONF = config.CONFIG
LOG = logging.getLogger(__name__)


class ExpiryNotifier(notifier.FreshDeskNotifier):
    def __init__(
        self,
        resource_type,
        resource,
        template_dir,
        group_id,
        subject,
        ks_session=None,
        dry_run=False,
        ticket_id_key='expiry_ticket_id',
    ):
        full_template_dir = f"expiry/{template_dir}"
        super().__init__(
            resource_type,
            resource,
            full_template_dir,
            group_id,
            subject,
            dry_run,
        )
        self.ticket_id_key = ticket_id_key
        self.k_client = auth.get_keystone_client(ks_session)
        self.g_client = auth.get_glance_client(ks_session)
        self.n_client = auth.get_nova_client(ks_session)
        self.kube_client = auth.get_kube_client()

    def send_message(
        self, stage, owner, extra_context={}, extra_recipients=[], tags=[]
    ):
        text = self.render_template(f'{stage}.tmpl', extra_context)

        ticket_id = self._get_ticket_id()

        if ticket_id > 0:
            self._update_ticket_requester(ticket_id, owner)
            self._update_ticket(ticket_id, text, cc_emails=extra_recipients)
        else:
            ticket_id = self._create_ticket(
                email=owner,
                cc_emails=extra_recipients,
                description=text,
                extra_context=extra_context,
                tags=['expiry'] + tags,
            )
            self._set_ticket_id(ticket_id)

            try:
                details = self.render_template(
                    f'{self.resource_type}-details.tmpl', extra_context
                )
            except exceptions.TemplateNotFound:
                LOG.debug("Details template not found, ignoring")
            else:
                self._add_note_to_ticket(ticket_id, details)

    def finish(self, message=None):
        ticket_id = self._get_ticket_id()
        if ticket_id:
            if message:
                self._add_note_to_ticket(ticket_id, message)

            if not self.dry_run:
                # Status 5 == Closed
                LOG.info("%s: Closing ticket %s", self.resource.id, ticket_id)
                self.api.tickets.update_ticket(ticket_id, status=5)
            else:
                LOG.info(
                    "%s: Would close ticket %s", self.resource.id, ticket_id
                )

    def _set_ticket_id(self, ticket_id):
        kwargs = {self.ticket_id_key: str(ticket_id)}
        if not self.dry_run:
            if self.resource_type == 'project':
                self.k_client.projects.update(self.resource.id, **kwargs)
            elif self.resource_type == 'image':
                self.g_client.images.update(self.resource.id, **kwargs)
            elif self.resource_type == 'instance':
                self.n_client.servers.set_meta(self.resource.id, kwargs)
            elif self.resource_type == 'jupyterhub_volume':
                body = {'metadata': {'annotations': kwargs}}
                self.kube_client.patch_namespaced_persistent_volume_claim(
                    self.resource.id,
                    CONF.kubernetes_client.namespace,
                    body=body,
                )
        LOG.debug('%s: Setting %s', self.resource.id, kwargs)

    def _get_ticket_id(self):
        try:
            if self.resource_type == 'instance':
                return int(self.resource.metadata.get(self.ticket_id_key, 0))
            elif self.resource_type == 'jupyterhub_volume':
                return int(
                    self.resource.metadata.annotations.get(
                        self.ticket_id_key, 0
                    )
                )
            else:
                return int(getattr(self.resource, self.ticket_id_key, 0))
        except ValueError:
            return 0
