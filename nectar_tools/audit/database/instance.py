import logging

from nectar_tools.audit import base
from nectar_tools import auth

LOG = logging.getLogger(__name__)


class DatabaseInstanceAuditor(base.Auditor):

    def setup_clients(self):
        super().setup_clients()
        self.openstack = auth.get_openstacksdk(sess=self.ks_session)
        self.n_client = auth.get_nova_client(sess=self.ks_session)
        self.q_client = auth.get_neutron_client(sess=self.ks_session)
        self.t_client = auth.get_trove_client(sess=self.ks_session)

    def check_allowed_cidrs(self):
        instances = self.t_client.mgmt_instances.list()
        for i in instances:
            trove_access = i.access.get('allowed_cidrs', ['0.0.0.0/0'])
            access = []
            name = 'trove_sg-%s' % i.id
            sgs = self.q_client.list_security_groups(
                name=name)['security_groups']
            for group in sgs:
                for rule in group['security_group_rules']:
                    if rule['direction'] == 'ingress' \
                       and rule['protocol'] != 'icmp':
                        access.append(rule['remote_ip_prefix'])

            access.sort()
            trove_access.sort()
            if access != trove_access:
                LOG.error("Database instance %s secgroups out of sync. "
                          "trove=%s, neutron=%s", i.id, trove_access, access)
