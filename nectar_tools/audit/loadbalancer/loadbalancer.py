import logging

import openstack

from nectar_tools.audit import base
from nectar_tools import auth
from nectar_tools import config


CONF = config.CONFIG
LOG = logging.getLogger(__name__)


class LoadBalancerAuditor(base.Auditor):

    def setup_clients(self):
        super().setup_clients()
        self.openstack = auth.get_openstacksdk(sess=self.ks_session)
        self.n_client = auth.get_nova_client(sess=self.ks_session)

    def check_nova_instances(self):
        instances = self.n_client.servers.list(
            search_opts={'all_tenants': True,
                         'tenant_id': CONF.octavia.project_id})
        for instance in instances:
            if not instance.name.startswith('amphora-'):
                LOG.debug("Skipping instance %s", instance.name)
                continue
            amp_id = instance.name.replace('amphora-', '')
            try:
                self.openstack.load_balancer.get_amphora(amp_id)
            except openstack.exceptions.ResourceNotFound:
                LOG.warn("Not amp found for instance %s(%s)", instance.name,
                         instance.id)
                if self.repair:
                    instance.delete()
                    LOG.info("Deleted orphaned amp instance %s", instance.id)
