import logging

from nectar_tools.audit import base
from nectar_tools import auth


LOG = logging.getLogger(__name__)


class ResourceProviderAuditor(base.Auditor):
    def setup_clients(self):
        super().setup_clients()
        self.p_client = auth.get_placement_client(sess=self.ks_session)
        self.n_client = auth.get_nova_client(sess=self.ks_session)

    def check_hypervisor_exists(self):
        resource_providers = self.p_client.resource_providers.list()
        hypervisors = self.n_client.hypervisors.list()
        rp_lookup = {r.name: r for r in resource_providers}
        resource_providers = set(
            [
                r.name
                for r in resource_providers
                if hasattr(r.inventories(), 'VCPU')
            ]
        )
        hypervisors = set([h.hypervisor_hostname for h in hypervisors])

        deleted_hypervisors = resource_providers - hypervisors
        for h in deleted_hypervisors:
            LOG.warning("Resource provider %s no longer a hypervisor", h)
            rp = rp_lookup[h]
            for consumer_id in rp.allocations():
                self.repair(
                    f"Deleting stale allocation for consumer {consumer_id}",
                    lambda: self.p_client.allocations.delete(consumer_id),
                )

            def do_repair():
                try:
                    self.p_client.resource_providers.delete(rp.id)
                except Exception as e:
                    LOG.exception(e)

            self.repair(f"Deleting resource provider {h}", do_repair)
