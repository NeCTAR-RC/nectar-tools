import logging

import novaclient

from nectar_tools.audit.metric import base
from nectar_tools import auth


LOG = logging.getLogger(__name__)


class InstanceAuditor(base.ResourceAuditor):

    def setup_clients(self):
        super().setup_clients()
        self.n_client = auth.get_nova_client(sess=self.ks_session)

    def ensure_flavor_name(self):
        flavors = self.n_client.flavors.list(is_public=None)
        flavors = {x.id: x.name for x in flavors}

        instances = self.g_client.resource.search(
            resource_type='instance',
            query="flavor_name = ''",
            limit=1000
        )
        LOG.debug("Found %s instances", len(instances))
        for instance in instances:
            try:
                flavor_name = flavors[instance['flavor_id']]
            except KeyError:
                LOG.error("%s: flavor_id points to non-existant flavor %s",
                          instance['id'], instance['flavor_id'])
                continue

            self.repair(f"{instance['id']}: Setting flavor_name",
                        lambda: self.g_client.resource.update(
                            'instance', instance['id'],
                            {'flavor_name': flavor_name}))

    def ensure_availability_zone(self):
        instances = self.g_client.resource.search(
            resource_type='instance',
            query="availability_zone = none",
            limit=1000,
        )
        LOG.debug("Found %s instances", len(instances))
        for instance in instances:
            LOG.debug("Processing instance %s", instance['id'])
            try:
                nova_instance = self.n_client.servers.get(instance['id'])
                LOG.debug("Found running instance")
            except novaclient.exceptions.NotFound:
                opts = {'deleted': True,
                        'all_tenants': True,
                        'user_id': instance['user_id'],
                        'project_id': instance['project_id'],
                        'name': instance['display_name']}
                nova_instances = self.n_client.servers.list(search_opts=opts)

                nova_instance = None
                if nova_instances:
                    for i in nova_instances:
                        if i.id == instance['id']:
                            nova_instance = i
                            break
                if nova_instance is None or not nova_instances:
                    LOG.warn("Can't find deleted instance in nova %s",
                             instance)
                    continue

            az = getattr(nova_instance, 'OS-EXT-AZ:availability_zone', None)
            if az:
                self.repair(f"{instance['id']}: Setting AZ",
                            lambda: self.g_client.resource.update(
                                'instance', instance['id'],
                                {'availability_zone': az}))
            else:
                LOG.error("%s: Nova instance has no AZ",
                          instance['id'])
                continue
