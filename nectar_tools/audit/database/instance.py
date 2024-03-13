import logging

from novaclient import exceptions as n_exc
from troveclient.apiclient import exceptions as t_exc

from nectar_tools.audit import base
from nectar_tools import auth
from nectar_tools import config


CONF = config.CONFIG
LOG = logging.getLogger(__name__)


class DatabaseInstanceAuditor(base.Auditor):

    def setup_clients(self):
        super().setup_clients()
        self.openstack = auth.get_openstacksdk(sess=self.ks_session)
        self.n_client = auth.get_nova_client(sess=self.ks_session)
        self.q_client = auth.get_neutron_client(sess=self.ks_session)
        self.t_client = auth.get_trove_client(sess=self.ks_session)
        self.c_client = auth.get_cinder_client(sess=self.ks_session)
        self.k_client = auth.get_keystone_client(sess=self.ks_session)

    def check_allowed_cidrs(self):
        instances = self.t_client.mgmt_instances.list()
        for i in instances:
            trove_access_raw = i.access.get('allowed_cidrs', ['0.0.0.0/0'])
            trove_access = []
            for ip in trove_access_raw:
                if '/' not in ip:
                    ip = f'{ip}/32'
                trove_access.append(ip)
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

    def clean_stale_instances(self):
        t_instances = self.t_client.mgmt_instances.list()
        search_opts = {'tenant_id': CONF.trove.project_id,
                       'all_tenants': True}
        n_instances = self.n_client.servers.list(search_opts=search_opts)

        t_ids = set([i.server_id for i in t_instances])
        n_ids = set([i.id for i in n_instances])

        stale = n_ids - t_ids
        for i in stale:
            self.repair(f"Deleting stale nova instance {i}, "
                        f"no corresponding db instance",
                        self.n_client.servers.delete,
                        server=i)

    def clean_stale_secgroups(self):
        secgroups = self.q_client.list_security_groups(
            tenant_id=CONF.trove.project_id)['security_groups']

        instances = self.t_client.mgmt_instances.list()
        ids = [i.id for i in instances]
        for g in secgroups:
            name = g.get('name')
            if not name.startswith('trove_sg-'):
                continue
            id = name[9:]
            if id not in ids:
                try:
                    self.repair(f"Delete old seggroup for instance {id}",
                                self.q_client.delete_security_group,
                                security_group=g.get('id'))
                except Exception as e:
                    LOG.error(f"Failed to delete secgroup {g.get('id')}, "
                              f"for instance {id}")
                    LOG.exception(e)

    def clean_stale_volumes(self):
        search_opts = {'project_id': CONF.trove.project_id,
                       'all_tenants': True}
        volumes = self.c_client.volumes.list(search_opts=search_opts)

        instances = self.t_client.mgmt_instances.list()
        ids = [i.id for i in instances]

        for v in volumes:
            if v.name.startswith('trove-'):
                id = v.name[6:]
            elif v.name.startswith('datastore-'):
                id = v.name[10:]
            else:
                LOG.info(f'Skipping volume {v.name} ({v.id})')
                continue

            if id not in ids:
                if v.status == 'in-use':
                    instance = v.attachments[0].get('server_id')
                    try:
                        self.n_client.servers.get(instance)
                    except n_exc.NotFound:
                        self.repair(f"Reset volume {v.id} state instance gone",
                                    self.c_client.volumes.reset_state,
                                    volume=v.id, state='error',
                                    attach_status='detached')
                try:
                    self.repair(f"Delete old volume {v.id} for instance {id}",
                                self.c_client.volumes.force_delete,
                                volume=v.id)
                except Exception as e:
                    LOG.error(f"Failed to delete volume {v.id}, "
                              f"for instance {id}")
                    LOG.exception(e)

    def check_running_with_deleted_project(self):
        for inst in self.t_client.mgmt_instances.list():
            project = self.k_client.projects.get(inst.tenant_id)
            if not project.enabled or getattr(
                    project, 'expiry_status', 'active') == 'deleted':
                LOG.error("Instance %s belongs to a deleted project %s",
                          inst.id, project.id)
                self.repair(f"Deleted instance {inst.id}",
                            self.t_client.instances.delete,
                            instance=inst)

    def check_status(self):
        for inst in self.t_client.mgmt_instances.list():
            if inst.status == 'ERROR':
                LOG.error(f"Instance {inst.id} in {inst.status} state")
            elif inst.status == 'SHUTDOWN':
                project = self.k_client.projects.get(inst.tenant_id)
                expiry_status = getattr(project, 'expiry_status', 'active')
                if expiry_status == 'active':
                    LOG.error(f"Instance {inst.id} shut down but project not "
                              "under expiry")
            elif inst.server.get('status') == 'SHUTOFF':
                LOG.error(f"Instance {inst.id} nova instance shutoff")
            else:
                try:
                    self.t_client.databases.list(inst)
                except t_exc.BadRequest:
                    LOG.error(f"Instance {inst.id} RPC communication error")
                else:
                    LOG.debug(f"Instance {inst.id} RPC communication active")

    def check_datastore_latest(self):
        default_datastores = {}
        datastores = self.t_client.datastores.list()
        for ds in datastores:
            default_datastores[ds.name] = ds.default_version
        for inst in self.t_client.mgmt_instances.list():
            ds_type = inst.datastore.get('type')
            ds_version = inst.datastore.get('version')
            datastore_version = self.t_client.datastore_versions.get(
                ds_type, ds_version)
            if default_datastores[ds_type] != datastore_version.id:
                LOG.error(f"Outdated datastore, {inst.id} running "
                          f"{ds_type} {ds_version}")
