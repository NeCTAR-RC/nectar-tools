import logging
import re

from novaclient import exceptions as n_exc
from troveclient.apiclient import exceptions as t_exc

from nectar_tools.audit import base
from nectar_tools import auth
from nectar_tools import config
from nectar_tools import exceptions


CONF = config.CONF
LOG = logging.getLogger(__name__)

# The trove guest agent runs an RPC server on the topic
# guestagent.<instance_id> with the instance ID as its host, so
# oslo.messaging declares these queues for it:
#   guestagent.<instance_id>
#   guestagent.<instance_id>.<instance_id>
#   guestagent.<instance_id>_fanout_<random hex>
UUID_RE = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
GUESTAGENT_QUEUE_RE = re.compile(
    rf'^guestagent\.(?P<instance_id>{UUID_RE})(?:\.|_fanout_|$)'
)


def guestagent_queue_instance_id(name):
    """Return the ID of the instance a guestagent queue belongs to

    Returns None for queues that aren't guest agent RPC queues.
    """
    match = GUESTAGENT_QUEUE_RE.match(name)
    return match.group('instance_id') if match else None


class DatabaseInstanceAuditor(base.Auditor):
    def setup_clients(self):
        super().setup_clients()
        self.openstack = auth.get_openstacksdk(sess=self.ks_session)
        self.n_client = auth.get_nova_client(sess=self.ks_session)
        self.q_client = self.openstack.network
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
            name = f'trove_sg-{i.id}'
            sgs = self.q_client.security_groups(name=name)
            for group in sgs:
                for rule in group.security_group_rules:
                    if (
                        rule['direction'] == 'ingress'
                        and rule['protocol'] != 'icmp'
                    ):
                        access.append(rule['remote_ip_prefix'])

            access.sort()
            trove_access.sort()
            if access != trove_access:
                LOG.error(
                    "Database instance %s secgroups out of sync. "
                    "trove=%s, neutron=%s",
                    i.id,
                    trove_access,
                    access,
                )

    def clean_stale_instances(self):
        t_instances = self.t_client.mgmt_instances.list()
        search_opts = {'tenant_id': CONF.trove.project_id, 'all_tenants': True}
        n_instances = self.n_client.servers.list(search_opts=search_opts)

        t_ids = set([i.server_id for i in t_instances])
        n_ids = set([i.id for i in n_instances])

        stale = n_ids - t_ids
        for i in stale:
            self.repair(
                f"Deleting stale nova instance {i}, "
                f"no corresponding db instance",
                self.n_client.servers.delete,
                server=i,
            )

    def clean_stale_secgroups(self):
        secgroups = self.q_client.security_groups(
            project_id=CONF.trove.project_id
        )

        instances = self.t_client.mgmt_instances.list()
        ids = [i.id for i in instances]
        for g in secgroups:
            name = g.name
            if not name.startswith('trove_sg-'):
                continue
            id = name[9:]
            if id not in ids:
                try:
                    self.repair(
                        f"Delete old secgroup for instance {id}",
                        self.q_client.delete_security_group,
                        security_group=g.id,
                    )
                except Exception:
                    LOG.exception(
                        "Failed to delete secgroup %s, for instance %s",
                        g.id,
                        id,
                    )

    def clean_stale_volumes(self):
        search_opts = {
            'project_id': CONF.trove.project_id,
            'all_tenants': True,
        }
        volumes = self.c_client.volumes.list(search_opts=search_opts)

        instances = self.t_client.mgmt_instances.list()
        ids = [i.id for i in instances]

        for v in volumes:
            if not v.name:
                continue
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
                        self.repair(
                            f"Reset volume {v.id} state instance gone",
                            self.c_client.volumes.reset_state,
                            volume=v.id,
                            state='error',
                            attach_status='detached',
                        )
                try:
                    self.repair(
                        f"Delete old volume {v.id} for instance {id}",
                        self.c_client.volumes.force_delete,
                        volume=v.id,
                    )
                except Exception:
                    LOG.exception(
                        "Failed to delete volume %s, for instance %s",
                        v.id,
                        id,
                    )

    def clean_stale_guestagent_queues(self):
        """Delete RabbitMQ queues left behind by deleted database instances

        The guest agent's RPC queues are declared without auto-delete so
        they stay on the broker after the instance and its guest are gone.
        """
        rabbit = auth.get_trove_rabbitmq_client()
        vhost = CONF.trove.rabbitmq_vhost

        # List the queues before the instances so an instance created in
        # between is never mistaken for a deleted one.
        queues = rabbit.list_queues(
            vhost, columns=['name', 'consumers', 'messages']
        )
        ids = set(i.id for i in self.t_client.mgmt_instances.list())

        for queue in queues:
            name = queue['name']
            instance_id = guestagent_queue_instance_id(name)
            if instance_id is None:
                LOG.debug("Skipping non guestagent queue %s", name)
                continue
            if instance_id in ids:
                continue
            if queue.get('consumers'):
                # Something is still connected, deleting the queue would
                # only have the consumer redeclare it
                LOG.warning(
                    "Queue %s has %s consumer(s) but instance %s "
                    "doesn't exist",
                    name,
                    queue['consumers'],
                    instance_id,
                )
                continue
            try:
                self.repair(
                    f"Delete queue {name} for deleted instance {instance_id}",
                    rabbit.delete_queue,
                    vhost=vhost,
                    name=name,
                    if_unused=True,
                )
            except exceptions.LimitReached:
                raise
            except Exception:
                LOG.exception(
                    "Failed to delete queue %s, for instance %s",
                    name,
                    instance_id,
                )

    def check_running_with_deleted_project(self):
        for inst in self.t_client.mgmt_instances.list():
            project = self.k_client.projects.get(inst.tenant_id)
            if (
                not project.enabled
                or getattr(project, 'expiry_status', 'active') == 'deleted'
            ):
                LOG.error(
                    "Instance %s belongs to a deleted project %s",
                    inst.id,
                    project.id,
                )
                self.repair(
                    f"Deleted instance {inst.id}",
                    self.t_client.instances.delete,
                    instance=inst,
                )

    def check_status(self):
        for inst in self.t_client.mgmt_instances.list():
            if inst.status == 'ERROR':
                LOG.error("Instance %s in %s state", inst.id, inst.status)
            elif inst.status == 'SHUTDOWN':
                project = self.k_client.projects.get(inst.tenant_id)
                expiry_status = getattr(project, 'expiry_status', 'active')
                if expiry_status == 'active':
                    LOG.error(
                        "Instance %s shut down but project not under expiry",
                        inst.id,
                    )
            elif inst.server is None:
                LOG.error("Instance %s has no nova server", inst.id)
            elif inst.server.get('status') == 'SHUTOFF':
                LOG.error("Instance %s nova instance shutoff", inst.id)
            else:
                try:
                    self.t_client.databases.list(inst)
                except t_exc.BadRequest:
                    LOG.error("Instance %s RPC communication error", inst.id)
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
                ds_type, ds_version
            )
            if default_datastores[ds_type] != datastore_version.id:
                LOG.error(
                    "Outdated datastore, %s running %s %s",
                    inst.id,
                    ds_type,
                    ds_version,
                )
