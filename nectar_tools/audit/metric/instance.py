import datetime

import logging

import novaclient

from nectar_tools.audit.metric import base
from nectar_tools import auth
from nectar_tools import config

CONF = config.CONFIG

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

    def ensure_instance_consistency(self):
        MAX_TIME_DIFF = 3600

        marker = None
        count = 0
        instances = []
        changes_since = datetime.date.today() - datetime.timedelta(
            days=self.extra_args['days_ago'])
        changes_since = changes_since.isoformat()
        tempest_project_ids = CONF.tempest.tempest_project_ids.split(',')
        while True:
            opts = {'deleted': False,
                    'all_tenants': True,
                    'marker': marker,
                    'availability_zone': '^' + self.extra_args['az'] + '$',
                    'changes-since': changes_since}
            instances_chunk = self.n_client.servers.list(search_opts=opts)
            count += 1
            LOG.debug("Retrieve nova instances - #%d call with marker %s",
                      count, marker)
            if len(instances_chunk) < 1 or (
                    len(instances) == 1 and instances[0]['id'] == marker):
                break
            for i in instances_chunk:
                if i.tenant_id not in tempest_project_ids and \
                  i.status not in ['ERROR', 'BUILDING']:
                    instances.append(i)
            marker = instances_chunk[-1].id

        total = len(instances)
        LOG.info("Processing %d instances", total)
        processed = 0
        for i in instances:
            processed += 1
            id, start, end, project_id = (i.id,
                getattr(i, 'OS-SRV-USG:launched_at'),
                getattr(i, 'OS-SRV-USG:terminated_at'), i.tenant_id)
            LOG.debug("Processed %s #%s/%s", id, processed, total)
            if start:
                start = datetime.datetime.fromisoformat(start)
            else:
                LOG.warning('Starting time missing for %s in nova', id)
                continue
            if end:
                end = datetime.datetime.fromisoformat(end)
                duration = (end - start)
            else:
                duration = 'ongoing'

            try:
                gnocchi_instance = self.g_client.resource.get('instance', id)
            except Exception:
                if not end:
                    LOG.warning('Running instance %s not in gnocchi', id)
                elif duration.total_seconds() > MAX_TIME_DIFF:
                    LOG.warning("No instance in gnocchi %s - project: %s "
                                "duration: %s", id, project_id, duration)
            else:
                updates = {}

                g_start = gnocchi_instance.get('started_at').split('+')[0]
                try:
                    g_start = datetime.datetime.strptime(
                        g_start, '%Y-%m-%dT%H:%M:%S.%f')
                except ValueError:
                    g_start = datetime.datetime.strptime(
                        g_start, '%Y-%m-%dT%H:%M:%S')

                g_end = gnocchi_instance.get('ended_at')
                if g_end is not None:
                    g_end = g_end.split('+')[0]
                    try:
                        g_end = datetime.datetime.strptime(
                            g_end, '%Y-%m-%dT%H:%M:%S.%f')
                    except ValueError:
                        g_end = datetime.datetime.strptime(
                            g_end, '%Y-%m-%dT%H:%M:%S')

                if abs((g_start - start).total_seconds()) > MAX_TIME_DIFF:
                    updates['started_at'] = str(start)
                    LOG.debug('Updating gnocchi start time for %s', id)
                if end and not g_end:
                    updates['ended_at'] = str(end) + '.9'
                    LOG.debug('Deleted instance not set in gnocchi for %s', id)
                elif g_end and not end:
                    updates['ended_at'] = None
                    LOG.debug('Non-deleted instance deleted in gnocchi for %s',
                             id)
                elif end and g_end and \
                    abs((g_end - end).total_seconds()) > MAX_TIME_DIFF:
                    updates['ended_at'] = str(end)
                    LOG.debug('Updating gnocchi end time for %s', id)

                if 'started_at' in updates:
                    self.repair(f"{id}: Setting started_at",
                                lambda: self.g_client.resource.update(
                                    'instance', id,
                                    {'started_at': updates['started_at']}))
                elif 'ended_at' in updates:
                    self.repair(f"{id}: Setting ended_at",
                                lambda: self.g_client.resource.update(
                                    'instance', id,
                                    {'ended_at': updates['ended_at']}))
