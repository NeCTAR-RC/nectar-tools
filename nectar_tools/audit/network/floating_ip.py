import logging

from nectar_tools.audit.metric import base
from nectar_tools import auth

import nectar_tools.audit.network.siteLookUpTable as lookUpTable

LOG = logging.getLogger(__name__)


# This audit finds floating networks that are attached to an instance on a different site  # noqa
class FloatingIPAuditor(base.ResourceAuditor):

    def setup_clients(self):
        super().setup_clients()
        self.neutronc = auth.get_neutron_client(sess=self.ks_session)
        self.novac = auth.get_nova_client(sess=self.ks_session)

    def check_availability_zone(self):
        floating_ips = self.neutronc.list_floatingips()
        for floating_ip in floating_ips['floatingips']:
            port_id = floating_ip["port_id"]

            # if there is no port id, this floating ip can't be attached to an instance  # noqa
            if port_id is None:
                continue

            port = self.neutronc.show_port(port_id)
            device_owner = port['port']['device_owner']

            # We are looking for device_owner string that looks like compute:AZ  # noqa
            if device_owner is None:
                continue

            device_owner_name = device_owner.split(':')[0]
            if device_owner_name != "compute":
                continue

            device_id = port['port']['device_id']
            floating_ip_id = floating_ip['id']
            network_name = self.neutronc.show_network(floating_ip['floating_network_id'])['network']['name']  # noqa

            instance = self.novac.servers.get(device_id)
            az = getattr(instance, 'OS-EXT-AZ:availability_zone', None)

            # Translate Network name and AZ into sites
            networkSite = lookUpTable.NetworkToSite.get(network_name)  # noqa
            AZSite = lookUpTable.AZToSite.get(az)

            if network_name is None or AZSite is None or networkSite != AZSite:  # noqa
                LOG.error("floating_ip_id %s network_name %s network_site %s instance_id %s instance_AZ %s instance_site %s", floating_ip_id, network_name, networkSite, device_id, az, AZSite )  # noqa
