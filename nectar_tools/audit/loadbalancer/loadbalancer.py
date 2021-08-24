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
        self.g_client = auth.get_glance_client(sess=self.ks_session)

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
                LOG.warn("No amp found for instance %s(%s)", instance.name,
                         instance.id)
                self.repair(f"Deleting orphaned amp instance {instance.id}",
                            lambda: instance.delete())

    def old_amphora_image(self):
        images = self.g_client.images.list(filters={'tag': ['octavia']})
        latest_image = list(images)[0]

        LOG.debug(f"Latest image ID is {latest_image.id}")

        lbs = self.openstack.load_balancer.load_balancers()
        for lb in lbs:
            if lb.provisioning_status != 'ACTIVE':
                LOG.debug(f"LB {lb.id} in state {lb.provisioning_status}")
                continue

            amphorae = self.openstack.load_balancer.amphorae(
                loadbalancer_id=lb.id)
            for amp in amphorae:
                if amp.get('image_id') != latest_image.id:
                    LOG.warn(f"LB {lb.id} not using latest image")
                    self.repair(
                        f"Fail over LB {lb.id}", lambda:
                        self.openstack.load_balancer.failover_load_balancer(
                            lb.id)
                        )
                    break
                else:
                    LOG.debug(f"LB {lb.id} using latest image")
