import logging

from nectar_tools.audit.metric import base
from nectar_tools import auth

import nectar_tools.audit.common as look_up_table

LOG = logging.getLogger(__name__)


class FloatingIPAuditor(base.ResourceAuditor):
    """Finds floating IPs that are attached to instances at different sites"""
    def setup_clients(self):
        super().setup_clients()
        self.neutronc = auth.get_neutron_client(sess=self.ks_session)
        self.novac = auth.get_nova_client(sess=self.ks_session)

    def check_availability_zone(self):
        floating_ips = self.neutronc.list_floatingips()
        for floating_ip in floating_ips['floatingips']:
            port_id = floating_ip["port_id"]

            # if there is no port id, this floating ip
            # can't be attached to an instance
            if port_id is None:
                continue

            port = self.neutronc.show_port(port_id)
            device_owner = port['port']['device_owner']

            # We are looking for device_owner string
            # that looks like compute:AZ
            if device_owner is None:
                continue

            device_owner_name = device_owner.split(':')[0]
            if device_owner_name != "compute":
                continue

            device_id = port['port']['device_id']
            floating_ip_id = floating_ip['id']
            net_name = self.neutronc.show_network(
                floating_ip['floating_network_id'])['network']['name']

            instance = self.novac.servers.get(device_id)
            az = getattr(instance, 'OS-EXT-AZ:availability_zone', None)

            # Translate Network name and AZ into sites
            networkSite = look_up_table.NETWORK_SITE_MAP.get(net_name)
            AZSite = look_up_table.AZ_SITE_MAP.get(az)

            if net_name is None or AZSite is None or networkSite != AZSite:
                LOG.info("Floating IP %s is from %s but instance %s is in %s",
                          floating_ip_id, networkSite, device_id, AZSite
            )
