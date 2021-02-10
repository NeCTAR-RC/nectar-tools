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

            if self.repair:
                if not self.dry_run:
                    LOG.info("%s: Setting flavor_name", instance['id'])
                    self.g_client.resource.update(
                        'instance', instance['id'],
                        {'flavor_name': flavor_name})
                else:
                    LOG.info("%s: Would set flavor_name", instance['id'])

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
                if self.repair:
                    if not self.dry_run:
                        LOG.info("%s: Setting AZ", instance['id'])
                        self.g_client.resource.update(
                            'instance', instance['id'],
                            {'availability_zone': az})
                    else:
                        LOG.info("%s: Would set AZ", instance['id'])
            else:
                LOG.error("%s: Nova instance has no AZ",
                          instance['id'])
                continue

    def ensure_marked_deleted(self):
        self._ensure_marked_deleted('2010-01-01', '2015-01-01')
        self._ensure_marked_deleted('2015-01-01', '2016-01-01')
        self._ensure_marked_deleted('2016-01-01', '2017-01-01')
        self._ensure_marked_deleted('2017-01-01', '2018-01-01')
        self._ensure_marked_deleted('2018-01-01', '2019-01-01')
        self._ensure_marked_deleted('2019-01-01', '2020-01-01')
        self._ensure_marked_deleted('2020-01-01', '2020-02-01')
        self._ensure_marked_deleted('2020-02-01', '2020-03-01')
        self._ensure_marked_deleted('2020-03-01', '2020-04-01')
        self._ensure_marked_deleted('2020-04-01', '2020-05-01')
        self._ensure_marked_deleted('2020-05-01', '2020-06-01')
        self._ensure_marked_deleted('2020-06-01', '2020-07-01')
        self._ensure_marked_deleted('2020-07-01', '2020-08-01')
        self._ensure_marked_deleted('2020-08-01', '2020-09-01')
        self._ensure_marked_deleted('2020-09-01', '2020-10-01')
        self._ensure_marked_deleted('2020-10-01', '2020-11-01')
        self._ensure_marked_deleted('2020-11-01', '2020-12-01')
        self._ensure_marked_deleted('2020-12-01', '2021-01-01')
        self._ensure_marked_deleted('2021-01-01', '2021-02-01')
        self._ensure_marked_deleted('2021-02-01', '2021-03-01')
        self._ensure_marked_deleted('2021-03-01', '2021-04-01')
        self._ensure_marked_deleted('2021-04-01', '2021-05-01')
        self._ensure_marked_deleted('2021-05-01', '2021-06-01')

    def _ensure_marked_deleted(self, start, end):
        instances = self.g_client.resource.search(
            resource_type='instance',
            query="ended_at = none and started_at >= '%s' and started_at <= '%s'" % (start, end),
            limit=3000,
        )
        LOG.info("Start %s, End %s", start, end)
        LOG.info("Found %s instances", len(instances))

        for instance in instances:
            LOG.debug("Processing instance %s", instance['id'])
            try:
                nova_instance = self.n_client.servers.get(instance['id'])
                LOG.debug("Found running instance")
                continue
            except novaclient.exceptions.NotFound:
                opts = {'deleted': True,
                        'all_tenants': True,
                        'user_id': instance['user_id'],
                        'project_id': instance['project_id'],
                        'name': instance['display_name']}
                        # 'host': instance['host']}
                try:
                    nova_instances = self.n_client.servers.list(
                        search_opts=opts)
                except Exception:
                    LOG.error("Failed to list instances")
                    continue

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
            deleted_at = getattr(nova_instance, 'OS-SRV-USG:terminated_at',
                                 None)
            if deleted_at:
                if self.repair:
                    LOG.info("%s: Setting ended_at, host=%s, AZ=%s",
                             instance['id'], instance['availability_zone'],
                             instance['host'])
                    self.g_client.resource.update(
                        'instance', instance['id'],
                        {'started_at': nova_instance.created})
                    self.g_client.resource.update(
                        'instance', instance['id'],
                        {'ended_at': deleted_at})
                else:
                    LOG.info("%s: Would set ended_at", instance['id'])
            else:
                LOG.error("%s: Nova instance has no deleted_at",
                          instance['id'])
                continue
