import logging

from nectar_tools.audit import base
from nectar_tools import auth


LOG = logging.getLogger(__name__)


class ResourceProviderAuditor(base.Auditor):

    def __init__(self, ks_session, repair=False):
        super().__init__(ks_session, repair)
        self.p_client = auth.get_placement_client(sess=ks_session)
        self.n_client = auth.get_nova_client(sess=ks_session)

    def check_hypervisor_exists(self):
        resource_providers = self.p_client.resource_providers.list()
        hypervisors = self.n_client.hypervisors.list()
        rp_lookup = {r.name: r for r in resource_providers}
        resource_providers = set([r.name for r in resource_providers
                                  if hasattr(r.inventories(), 'VCPU')])
        hypervisors = set([h.hypervisor_hostname for h in hypervisors])

        deleted_hypervisors = resource_providers - hypervisors
        for h in deleted_hypervisors:
            LOG.warn("Resource provider %s no longer a hypervisor", h)
            rp = rp_lookup[h]
            if self.repair:
                for consumer_id in rp.allocations():
                    self.p_client.allocations.delete(consumer_id)
                    LOG.info("Deleted stale allocation for consumer %s",
                             consumer_id)
                try:
                    self.p_client.resource_providers.delete(rp.id)
                except Exception as e:
                    LOG.exception(e)
                else:
                    LOG.info("Deleted resource provider %s", h)
