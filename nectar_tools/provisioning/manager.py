import collections
from keystoneauth1 import exceptions as keystone_exc
import logging
import neutronclient
import novaclient
import prettytable

from nectarallocationclient import client

from nectar_tools import auth
from nectar_tools import config
from nectar_tools import exceptions
from nectar_tools.expiry import archiver
from nectar_tools.expiry import expirer
from nectar_tools.provisioning import notifier as provisioning_notifier


CONF = config.CONFIG
LOG = logging.getLogger(__name__)


class ProvisioningManager(object):

    def __init__(self, ks_session=None, noop=False, force=False,
                 no_notify=False, *args, **kwargs):
        self.force = force
        self.no_notify = no_notify
        self.noop = noop
        self.ks_session = ks_session
        self.client = client.Client(1, session=ks_session)
        self.k_client = auth.get_keystone_client(ks_session)
        self.a_client = auth.get_allocation_client(ks_session)

    def provision(self, allocation):
        if allocation.provisioned:
            if not self.force:
                raise exceptions.InvalidProjectAllocation(
                    "Allocation already provisioned")
        LOG.info("%s: Provisioning %s", allocation.id, allocation.project_name)
        project = None
        if allocation.project_id:
            try:
                project = self.k_client.projects.get(allocation.project_id)
            except keystone_exc.NotFound as exc:
                raise exceptions.InvalidProjectAllocation(
                    "Existing project not found") from exc
        is_new_project = True
        if not project:
            # New allocation
            try:
                self.k_client.projects.find(name=allocation.project_name)
            except keystone_exc.NotFound:
                pass
            else:
                raise exceptions.InvalidProjectAllocation(
                    "Project already exists")

            if allocation.convert_trial_project:
                project = self.convert_trial(allocation)
            else:
                project = self.create_project(allocation)
            if not self.noop:
                allocation = self.update_allocation(allocation,
                                                    project_id=project.id)
            self._grant_owner_roles(allocation, project)
        else:
            project = self.update_project(allocation)
            is_new_project = False

        designate_archiver = archiver.DesignateArchiver(
            {'project': project}, self.ks_session, dry_run=self.noop)
        designate_archiver.create_resources()

        report = self.quota_report(allocation, html=True,
                                   show_current=not is_new_project)
        self.set_quota(allocation)
        self.notify_provisioned(allocation, is_new_project, project, report)
        allocation = self.update_allocation(allocation, provisioned=True)
        LOG.info("%s: Allocation provisioned successfully", allocation.id)

        if not is_new_project:
            self.revert_expiry(project=project)

    def revert_expiry(self, project):
        allocation_expirer = expirer.AllocationExpirer(
            project, self.ks_session, dry_run=self.noop)

        allocation_expirer.revert_expiry()

    def update_allocation(self, allocation, **kwargs):
        if self.noop:
            LOG.info("%s: Would update allocation %s", allocation.id, kwargs)
            return allocation

        LOG.debug("%s: Updating allocation %s", allocation.id, kwargs)
        allocation.update(**kwargs)
        # Get a fresh copy of object
        return allocation.manager.get(allocation.id)

    def get_project_metadata(self, allocation):
        metadata = dict(name=allocation.project_name,
                        description=allocation.project_description,
                        allocation_id=allocation.id,
                        expires=allocation.end_date)

        zones = self.get_compute_zones(allocation)
        if zones:
            metadata.update(compute_zones=",".join(zones))
        return metadata

    def get_compute_zones(self, allocation):
        """Returns a list of zones based on allocation home

        If national or no mapping then return []
        """

        zone_map = self.a_client.zones.compute_homes()
        zones = zone_map.get(allocation.allocation_home)
        if zones:
            return zones
        return []

    def get_out_of_zone_instances(self, allocation, project):
        """Returns list of instances that a project has running in
        zones that it shouldn't based on its allocation home.
        """
        zones = self.get_compute_zones(allocation)
        if not zones:
            return []
        nova_archiver = archiver.NovaArchiver(
            {'project': project}, self.ks_session)
        instances = nova_archiver._all_instances()
        out_of_zone = []
        for instance in instances:
            az = getattr(instance, 'OS-EXT-AZ:availability_zone')
            if az not in zones:
                # We set this attribute so we can use it in templating
                setattr(instance, 'availability_zone', az)
                out_of_zone.append(instance)
        return out_of_zone

    def create_project(self, allocation):
        domain_mappings = collections.defaultdict(lambda: 'default')
        domain_mappings['auckland'] = 'b38a521521d844e49daf98571fa8a153'
        domain = domain_mappings[allocation.allocation_home]
        if self.noop:
            LOG.info("%s: Would create new keystone project in domain %s",
                     allocation.id, domain)
            return None

        metadata = self.get_project_metadata(allocation)
        metadata.update(domain=domain)
        project = self.k_client.projects.create(**metadata)
        LOG.info("%s: Created new keystone project %s", allocation.id,
                 project.id)
        return project

    def update_project(self, allocation):
        if self.noop:
            LOG.info("%s: Would update keystone project %s with expires = %s",
                     allocation.id, allocation.project_id, allocation.end_date)
            return self.k_client.projects.get(allocation.project_id)
        LOG.info("%s: Updating keystone project %s", allocation.id,
                 allocation.project_id)

        metadata = self.get_project_metadata(allocation)
        project = self.k_client.projects.update(allocation.project_id,
                                                **metadata)
        return project

    def _grant_owner_roles(self, allocation, project):
        try:
            manager = self.k_client.users.find(name=allocation.contact_email)
        except keystone_exc.NotFound as exc:
            raise exceptions.InvalidProjectAllocation(
                "Can't find keystone user for manager'") from exc

        if self.noop:
            LOG.info("%s: Would grant manager and member roles to %s",
                     allocation.id, manager.name)
            return

        self.k_client.roles.grant(CONF.keystone.manager_role_id,
                                  project=project,
                                  user=manager)
        LOG.info("%s: Add manager role to %s", allocation.id, manager.name)
        self.k_client.roles.grant(CONF.keystone.member_role_id,
                                  project=project,
                                  user=manager)
        LOG.info("%s: Add member role to %s", allocation.id, manager.name)

    def notify_provisioned(self, allocation, is_new_project, project, report):
        if not allocation.notifications or self.no_notify:
            LOG.info("%s: Noifications disabled, skipping", allocation.id)
            return
        if self.noop:
            LOG.info("%s: Would notify %s", allocation.id,
                     allocation.contact_email)
            return
        out_of_zone_instances = []
        compute_zones = self.get_compute_zones(allocation)
        if is_new_project:
            notification = 'new'
        else:
            notification = 'update'
            out_of_zone_instances = self.get_out_of_zone_instances(allocation,
                                                                   project)
        notifier = provisioning_notifier.ProvisioningNotifier(project)
        extra_context = {'allocation': allocation, 'report': report,
                         'out_of_zone_instances': out_of_zone_instances,
                         'compute_zones': compute_zones}
        notifier.send_message(notification, allocation.contact_email,
                              extra_context=extra_context)

    def convert_trial(self, allocation):
        LOG.info("%s: Converting project trial", allocation.id)
        try:
            manager = self.k_client.users.find(name=allocation.contact_email)
        except keystone_exc.NotFound as exc:
            raise exceptions.InvalidProjectAllocation(
                "User for manager not found") from exc

        old_pt = self.k_client.projects.get(manager.default_project_id)
        if not old_pt.name.startswith('pt-'):
            raise exceptions.InvalidProjectAllocation(
                "User's default project is not a pt- project")

        if self.noop:
            LOG.info("%s: Would create new PT %s", allocation.id, old_pt.name)
            LOG.info("%s: Would update %s to be %s", allocation.id,
                     old_pt.name, allocation.project_name)
            return
        new_pt_tmp_name = "%s_copy" % old_pt.name
        new_pt = self.k_client.projects.create(name=new_pt_tmp_name,
                                               domain=old_pt.domain_id,
                                               description=old_pt.description)

        self.k_client.users.update(manager, default_project=new_pt)

        # Rename existing pt to new project name/desc.
        # Reset status in case their pt- is pending suspension.
        project = self.k_client.projects.update(
            old_pt.id,
            name=allocation.project_name,
            description=allocation.project_description,
            status='',
            expiry_next_step='',
            expiry_status='',
            expiry_ticket_id=0,
            expiry_updated_at=''
        )
        self.k_client.projects.update(new_pt, name=old_pt.name)
        self.k_client.roles.grant(CONF.keystone.member_role_id,
                                  project=new_pt,
                                  user=manager)

        nova_archiver = archiver.NovaArchiver(
            {'project': project}, self.ks_session)
        nova_archiver.enable_resources()

        return project

    def set_quota(self, allocation):
        self.set_nova_quota(allocation)
        self.set_cinder_quota(allocation)
        self.set_neutron_quota(allocation)
        self.set_swift_quota(allocation)
        self.set_trove_quota(allocation)
        self.set_manila_quota(allocation)

    def quota_report(self, allocation, show_current=True, html=False):

        exclude = ['cinder.gigabytes',
                   'neutron.subnet',
                   'manila.gigabytes',
                   'manila.shares',
                   'manila.snapshots',
                   'manila.snapshot_gigabytes',
                   'nova.flavor:compute-v3',
                   'nova.flavor:memory-v3',
               ]
        resource_map = {
            'nova.instances': 'Instances',
            'nova.cores': 'VCPUs',
            'nova.ram': 'RAM (GB)',
            'swift.object': 'Object store (GB)',
            'trove.volumes': 'Database storage (GB)',
            'trove.instances': 'Database instances',
            'cinder.gigabytes_melbourne': "Volume storage Melbourne (GB)",
            'cinder.gigabytes_monash': "Volume storage Monash (GB)",
            'cinder.gigabytes_intersect': "Volume storage Intersect (GB)",
            'cinder.gigabytes_QRIScloud': "Volume storage QRIScloud (GB)",
            'cinder.gigabytes_auckland': "Volume storage Auckland (GB)",
            'cinder.gigabytes_sa': "Volume storage eRSA (GB)",
            'cinder.gigabytes_tasmania': "Volume storage Tasmania (GB)",
            'cinder.gigabytes_NCI': "Volume storage NCI (GB)",
            'cinder.gigabytes_pawsey': "Volume storage Pawsey (GB)",
            'neutron.network': "Networks",
            'neutron.router': "Routers",
            'neutron.floatingip': "Floating IPs",
            'neutron.loadbalancer': "Load Balancers",
            'manila.gigabytes_QRIScloud-GPFS':
                'Shared Filesystem Storage QRIScloud (GB)',
            'manila.snapshot_gigabytes_QRIScloud-GPFS':
                'Shared Filesystem Snapshot Storage QRIScloud (GB)',
            'manila.snapshots_QRIScloud-GPFS':
                'Shared Filesystem Snapshots QRIScloud',
            'manila.shares_QRIScloud-GPFS':
                'Shared Filesystem Shares QRIScloud',
        }
        current = collections.OrderedDict()
        allocated = collections.OrderedDict()

        def _prefix_dict(quotas, prefix, data):
            for key, value in quotas.items():
                data["%s.%s" % (prefix, key)] = value

        if show_current:
            _prefix_dict(self.get_current_nova_quota(allocation),
                         'nova', current)
            _prefix_dict(self.get_current_cinder_quota(allocation),
                         'cinder', current)
            _prefix_dict(self.get_current_swift_quota(allocation),
                         'swift', current)
            _prefix_dict(self.get_current_neutron_quota(allocation),
                         'neutron', current)
            _prefix_dict(self.get_current_trove_quota(allocation),
                         'trove', current)
            _prefix_dict(self.get_current_manila_quota(allocation),
                         'manila', current)

        _prefix_dict(allocation.get_allocated_nova_quota(),
                     'nova', allocated)
        _prefix_dict(allocation.get_allocated_cinder_quota(),
                     'cinder', allocated)
        _prefix_dict(allocation.get_allocated_swift_quota(),
                     'swift', allocated)
        _prefix_dict(allocation.get_allocated_neutron_quota(),
                     'neutron', allocated)
        _prefix_dict(allocation.get_allocated_trove_quota(),
                     'trove', allocated)
        _prefix_dict(allocation.get_allocated_manila_quota(),
                     'manila', allocated)

        table = prettytable.PrettyTable(
            ["Resource", "Current", "Allocated", "Diff"])
        table.align = 'r'
        table.align["Resource"] = 'l'
        for resource, allocated in allocated.items():
            try:
                current_quota = current[resource]
                if current_quota < 0:
                    current_quota = 0
                diff = allocated - current_quota
                if diff > 0:
                    diff = '+%s' % diff
            except KeyError:
                current_quota = ''
                diff = ''
            try:
                pretty_resource = resource_map[resource]
            except KeyError:
                pretty_resource = resource
            if resource not in exclude and \
               not (resource.startswith('cinder.volumes')
                    or resource.startswith('cinder.snapshots')):
                table.add_row([pretty_resource, current_quota, allocated,
                               diff])
        if html:
            return table.get_html_string(
                format=True, attributes={
                    'border': 1,
                    'style': 'border-width: 1px; border-collapse: collapse;'
                })
        print("Quota Report for Project %s" % allocation.project_id)
        print(table)

    def get_current_nova_quota(self, allocation):
        if not allocation.project_id:
            return {}
        client = auth.get_nova_client(self.ks_session)
        current = client.quotas.get(allocation.project_id)
        quotas = current._info
        quotas['ram'] = quotas['ram'] / 1024
        return quotas

    def set_nova_quota(self, allocation):
        allocated_quota = allocation.get_allocated_nova_quota()
        flavor_classes = []
        for quota in list(allocated_quota):
            if quota.startswith('flavor:'):
                flavor_classes.append(quota.split(':')[1])
                allocated_quota.pop(quota)

        for flavor_class in flavor_classes:
            self.flavor_grant(allocation, flavor_class)
        if self.noop and allocated_quota:
            LOG.info("%s: Would set nova quota to %s", allocation.id,
                     allocated_quota)
            return
        if allocated_quota:
            client = auth.get_nova_client(self.ks_session)
            client.quotas.delete(tenant_id=allocation.project_id)
            allocated_quota['ram'] = int(allocated_quota['ram']) * 1024
            client.quotas.update(tenant_id=allocation.project_id,
                                 force=True, **allocated_quota)
            LOG.info("%s: Set Nova Quota %s", allocation.id, allocated_quota)

    def flavor_grant(self, allocation, flavor_class):
        if self.noop:
            LOG.info("%s: Would grant access to %s flavors", allocation.id,
                     flavor_class)
            return
        client = auth.get_nova_client(self.ks_session)
        flavors = client.flavors.list(is_public=None)
        for flavor in flavors:
            fc = flavor.get_keys().get('flavor_class:name')
            if fc == flavor_class:
                try:
                    client.flavor_access.add_tenant_access(
                        flavor, allocation.project_id)
                    LOG.info("%s: Granted access to flavor %s", allocation.id,
                             flavor.name)
                except novaclient.exceptions.Conflict:
                    LOG.info("%s: Already has access to flavor %s",
                             allocation.id, flavor.name)

    def get_current_cinder_quota(self, allocation):
        if not allocation.project_id:
            return {}
        client = auth.get_cinder_client(self.ks_session)
        current = client.quotas.get(allocation.project_id)
        return current._info

    def set_cinder_quota(self, allocation):
        allocated_quota = allocation.get_allocated_cinder_quota()
        if self.noop and allocated_quota:
            LOG.info("%s: Would set cinder quota to %s", allocation.id,
                     allocated_quota)
            return
        client = auth.get_cinder_client(self.ks_session)
        client.quotas.delete(tenant_id=allocation.project_id)
        if allocated_quota:
            client.quotas.update(tenant_id=allocation.project_id,
                                 **allocated_quota)
            LOG.info("%s: Set Cinder Quota %s", allocation.id, allocated_quota)

    def get_current_swift_quota(self, allocation):
        if not allocation.project_id:
            return {}
        SWIFT_QUOTA_KEY = 'x-account-meta-quota-bytes'
        client = auth.get_swift_client(self.ks_session,
                                       project_id=allocation.project_id)
        account = client.get_account()
        try:
            quota = int(account[0][SWIFT_QUOTA_KEY]) / 1024 / 1024 / 1024
        except KeyError:
            quota = 0
        return {'object': quota}

    def set_swift_quota(self, allocation):
        allocated_quota = allocation.get_allocated_swift_quota()
        quota_bytes = allocated_quota['object'] * 1024 * 1024 * 1024
        SWIFT_QUOTA_KEY = 'x-account-meta-quota-bytes'

        if self.noop:
            LOG.info("%s: Would set Swift Quota: bytes=%s", allocation.id,
                     quota_bytes)
            return
        client = auth.get_swift_client(self.ks_session,
                                       project_id=allocation.project_id)
        client.post_account(
            headers={SWIFT_QUOTA_KEY: quota_bytes})
        LOG.info("%s: Set Swift Quota: bytes=%s", allocation.id, quota_bytes)

    def get_current_trove_quota(self, allocation):
        if not allocation.project_id:
            return {}
        client = auth.get_trove_client(self.ks_session)
        current = client.quota.show(allocation.project_id)
        data = {}
        for resource in current:
            data[resource.resource] = resource.limit
        return data

    def set_trove_quota(self, allocation):
        allocated_quota = allocation.get_allocated_trove_quota()

        if self.noop:
            LOG.info("%s: Would set Trove Quota: %s", allocation.id,
                     allocated_quota)
            return
        client = auth.get_trove_client(self.ks_session)
        client.quota.update(allocation.project_id, allocated_quota)
        LOG.info("%s: Set Trove Quota: %s", allocation.id, allocated_quota)

    def get_current_manila_quota(self, allocation):
        if not allocation.project_id:
            return {}
        client = auth.get_manila_client(self.ks_session)
        quotas = client.quotas.get(allocation.project_id)._info
        for share_type in client.share_types.list():
            type_quotas = client.quotas.get(allocation.project_id,
                                           share_type=share_type.id)
            type_quotas = {k + '_%s' % share_type.name: v
                           for k, v in type_quotas._info.items()}
            quotas.update(type_quotas)
        return quotas

    def set_manila_quota(self, allocation):
        allocated_quota = allocation.get_allocated_manila_quota()
        if self.noop:
            LOG.info("%s: Would set manila quota to %s", allocation.id,
                     allocated_quota)
            return
        client = auth.get_manila_client(self.ks_session)
        client.quotas.delete(tenant_id=allocation.project_id)

        global_quota = {
            'shares': allocated_quota.pop('shares'),
            'gigabytes': allocated_quota.pop('gigabytes'),
            'snapshots': allocated_quota.pop('snapshots'),
            'snapshot_gigabytes': allocated_quota.pop('snapshot_gigabytes')}

        client.quotas.update(tenant_id=allocation.project_id, **global_quota)
        LOG.info("%s: Set Global Manila Quota %s", allocation.id,
                 allocated_quota)
        for share_type in client.share_types.list():
            client.quotas.delete(tenant_id=allocation.project_id,
                                 share_type=share_type.id)
            type_quotas = {}
            resources = ['shares', 'gigabytes',
                         'snapshots', 'snapshot_gigabytes']
            for resource in resources:
                try:
                    type_quotas[resource] = allocated_quota.pop(
                        '%s_%s' % (resource, share_type.name))
                except KeyError:
                    continue
            if type_quotas:
                LOG.info("%s: Set Manila Quota for %s to %s", allocation.id,
                         share_type.name, type_quotas)
                client.quotas.update(tenant_id=allocation.project_id,
                                     share_type=share_type.id, **type_quotas)

    def get_current_neutron_quota(self, allocation):
        if not allocation.project_id:
            return {}
        client = auth.get_neutron_client(self.ks_session)
        return client.show_quota(allocation.project_id)['quota']

    def set_neutron_quota(self, allocation):
        allocated_quota = allocation.get_allocated_neutron_quota()
        if self.noop:
            LOG.info("%s: Would set Neutron Quota: %s", allocation.id,
                     allocated_quota)
            return

        client = auth.get_neutron_client(self.ks_session)
        try:
            client.delete_quota(allocation.project_id)
        except neutronclient.common.exceptions.NotFound:
            pass

        if allocated_quota:
            body = {'quota': allocated_quota}
            client.update_quota(allocation.project_id, body)
            LOG.info("%s: Set Neutron Quota: %s", allocation.id,
                     allocated_quota)
