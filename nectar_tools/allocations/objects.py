import collections
from keystoneauth1 import exceptions as keystone_exc
import logging
import neutronclient
import prettytable

from nectar_tools import allocations
from nectar_tools.allocations import states
from nectar_tools import auth
from nectar_tools import config
from nectar_tools import exceptions
from nectar_tools.expiry import archiver
from nectar_tools.expiry import expirer
from nectar_tools.provisioning import notifier as provisioning_notifier


CONF = config.CONFIG
LOG = logging.getLogger(__name__)


class Quota(object):

    def __init__(self, manager, data):
        for key, value in data.items():
            setattr(self, key, value)

    def __repr__(self):
        return "<Quota %s %s %s>" % (self.zone, self.resource, self.quota)


class Allocation(object):

    def __init__(self, manager, data, ks_session, noop=False):
        self.ks_session = ks_session
        self.k_client = auth.get_keystone_client(ks_session)
        self.quotas = []
        self.service_quotas = None
        self.manager = manager
        self.noop = noop
        for key, value in data.items():
            if key == 'quotas':
                for quota in value:
                    self.quotas.append(allocations.Quota(manager, quota))
            else:
                setattr(self, key, value)

    def __repr__(self):
        return "<Allocation %s>" % self.id

    def provision(self):
        if self.provisioned:
            raise exceptions.InvalidProjectAllocation(
                "Allocation already provisioned")
        LOG.info("%s: Provisioning %s", self.id, self.project_name)
        project = None
        if self.project_id:
            try:
                project = self.k_client.projects.get(self.project_id)
            except keystone_exc.NotFound as exc:
                raise exceptions.InvalidProjectAllocation(
                    "Existing project not found") from exc
        is_new_project = True
        if not project:
            # New allocation
            try:
                self.k_client.projects.find(name=self.project_name)
            except keystone_exc.NotFound as exc:
                pass
            else:
                raise exceptions.InvalidProjectAllocation(
                    "Project already exists")

            if self.convert_trial_project:
                project = self.convert_trial()
            else:
                project = self.create_project()
            self._grant_owner_roles(project)
        else:
            project = self.update_project()
            is_new_project = False

        report = self.quota_report(html=True, show_current=not is_new_project)
        self.set_quota()
        self.notify_provisioned(is_new_project, project, report)
        self.update(provisioned=True)
        LOG.info("%s: Allocation provisioned successfully", self.id)

        if not is_new_project:
            self.revert_expiry(project=project)

    def revert_expiry(self, project):
        allocation_expirer = expirer.AllocationExpirer(
            project, self.ks_session, dry_run=self.noop)

        allocation_expirer.revert_expiry()

    def create_project(self):
        domain_mappings = collections.defaultdict(lambda: 'default')
        domain_mappings['auckland'] = 'b38a521521d844e49daf98571fa8a153'
        domain = domain_mappings[self.funding_node]
        if self.noop:
            LOG.info("%s: Would create new keystone project in domain %s",
                     self.id, domain)
            return None

        project = self.k_client.projects.create(
            name=self.project_name,
            domain=domain,
            description=self.project_description,
            allocation_id=self.id,
            expires=self.end_date)
        LOG.info("%s: Created new keystone project %s", self.id, project.id)
        self.update(project_id=project.id)
        return project

    def _grant_owner_roles(self, project):
        try:
            manager = self.k_client.users.find(name=self.contact_email)
        except keystone_exc.NotFound as exc:
            raise exceptions.InvalidProjectAllocation(
                "Can't find keystone user for manager'") from exc

        if self.noop:
            LOG.info("%s: Would grant manager and member roles to %s", self.id,
                     manager.name)
            return

        self.k_client.roles.grant(CONF.keystone.manager_role_id,
                                  project=project,
                                  user=manager)
        LOG.info("%s: Add manager role to %s", self.id, manager.name)
        self.k_client.roles.grant(CONF.keystone.member_role_id,
                                  project=project,
                                  user=manager)
        LOG.info("%s: Add member role to %s", self.id, manager.name)

    def update_project(self):
        if self.noop:
            LOG.info("%s: Would update keystone project %s with expires = %s",
                     self.id, self.project_id, self.end_date)
            return self.k_client.projects.get(self.project_id)
        LOG.info("%s: Updating keystone project %s", self.id, self.project_id)
        project = self.k_client.projects.update(self.project_id,
                                                allocation_id=self.id,
                                                expires=self.end_date)
        return project

    def update(self, **kwargs):
        if self.noop:
            LOG.info("%s: Would update allocation %s", self.id, kwargs)
            return
        # Handle special case where allocation updated to deleted state
        if kwargs == {'status': 'D'}:
            return self.delete()

        LOG.debug("%s: Updating allocation %s", self.id, kwargs)
        self.manager.update_allocation(self.id, **kwargs)
        for k, v in kwargs.items():
            setattr(self, k, v)

    def delete(self):
        if self.noop:
            LOG.info("%s: Would delete allocation", self.id)
            return
        LOG.debug("%s: Deleting allocation", self.id)
        self.manager.update_allocation(self.id, status=states.DELETED)
        if self.parent_request:
            LOG.debug("%s: Deleting parent allocation %s", self.id,
                      self.parent_request)
            self.manager.update_allocation(self.parent_request,
                                           status=states.DELETED)

        self.status = states.DELETED

    def notify_provisioned(self, is_new_project, project, report):
        if self.noop:
            LOG.info("%s: Would notify %s", self.id, self.contact_email)
            return
        if is_new_project:
            notification = 'new'
        else:
            notification = 'update'
        notifier = provisioning_notifier.ProvisioningNotifier(project)
        extra_context = {'allocation': self, 'report': report}
        notifier.send_message(notification, self.contact_email,
                              extra_context=extra_context)

    def convert_trial(self):
        LOG.info("%s: Converting project trial", self.id)
        try:
            manager = self.k_client.users.find(name=self.contact_email)
        except keystone_exc.NotFound as exc:
            raise exceptions.InvalidProjectAllocation(
                "User for manager not found") from exc

        old_pt = self.k_client.projects.get(manager.default_project_id)
        if not old_pt.name.startswith('pt-'):
            raise exceptions.InvalidProjectAllocation(
                "User's default project is not a pt- project")

        if self.noop:
            LOG.info("%s: Would create new PT %s", self.id, old_pt.name)
            LOG.info("%s: Would update %s to be %s", self.id, old_pt.name,
                     self.project_name)
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
            name=self.project_name,
            description=self.project_description,
            status='',
            expiry_next_step='',
            expiry_status='',
            expiry_ticket_id=0,
            expiry_updated_at=''
        )
        self.k_client.projects.update(new_pt, name=old_pt.name)
        self.update(project_id=project.id)

        nova_archiver = archiver.NovaArchiver(project, self.ks_session)
        nova_archiver.enable_resources()

        return project

    def get_quota(self, service_type):
        if self.service_quotas is None:
            service_types = {}
            for quota in self.quotas:
                st, resource = quota.resource.split('.')
                if st in service_types:
                    service_types[st].append(quota)
                else:
                    service_types[st] = [quota]
            self.service_quotas = service_types

        try:
            return self.service_quotas[service_type]
        except KeyError:
            return []

    def set_quota(self):
        self.set_nova_quota()
        self.set_cinder_quota()
        self.set_neutron_quota()
        self.set_swift_quota()
        self.set_trove_quota()
        self.set_manila_quota()

    def quota_report(self, show_current=True, html=False):

        exclude = ['cinder.gigabytes',
                   'neutron.subnet',
                   'manila.gigabytes',
                   'manila.shares',
                   'manila.snapshots',
                   'manila.snapshot_gigabytes',
               ]
        resource_map = {
            'nova.instances': 'Instances',
            'nova.cores': 'VCPUs',
            'nova.ram': 'RAM (MB)',
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
            _prefix_dict(self.get_current_nova_quota(), 'nova', current)
            _prefix_dict(self.get_current_cinder_quota(), 'cinder', current)
            _prefix_dict(self.get_current_swift_quota(), 'swift', current)
            _prefix_dict(self.get_current_neutron_quota(), 'neutron', current)
            _prefix_dict(self.get_current_trove_quota(), 'trove', current)
            _prefix_dict(self.get_current_manila_quota(), 'manila', current)

        _prefix_dict(self.get_allocated_nova_quota(), 'nova', allocated)
        _prefix_dict(self.get_allocated_cinder_quota(), 'cinder', allocated)
        _prefix_dict(self.get_allocated_swift_quota(), 'swift', allocated)
        _prefix_dict(self.get_allocated_neutron_quota(), 'neutron', allocated)
        _prefix_dict(self.get_allocated_trove_quota(), 'trove', allocated)
        _prefix_dict(self.get_allocated_manila_quota(), 'manila', allocated)

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
               not (resource.startswith('cinder.volumes') or
                    resource.startswith('cinder.snapshots')):
                table.add_row([pretty_resource, current_quota, allocated,
                               diff])
        if html:
            return table.get_html_string(
                format=True, attributes={
                    'border': 1,
                    'style': 'border-width: 1px; border-collapse: collapse;'
                })
        print("Quota Report for Project %s" % self.project_id)
        print(table)

    def get_current_nova_quota(self):
        if not self.project_id:
            return {}
        client = auth.get_nova_client(self.ks_session)
        current = client.quotas.get(self.project_id)
        return current._info

    def get_allocated_nova_quota(self):
        return {'ram': self.core_quota * 4096, 'cores': self.core_quota,
                'instances': self.instance_quota}

    def set_nova_quota(self):
        allocated_quota = self.get_allocated_nova_quota()

        if self.noop:
            LOG.info("%s: Would set nova quota to %s", self.id,
                     allocated_quota)
            return

        client = auth.get_nova_client(self.ks_session)
        client.quotas.delete(tenant_id=self.project_id)
        client.quotas.update(tenant_id=self.project_id, **allocated_quota)
        LOG.info("%s: Set Nova Quota %s", self.id, allocated_quota)

    def get_current_cinder_quota(self):
        if not self.project_id:
            return {}
        client = auth.get_cinder_client(self.ks_session)
        current = client.quotas.get(self.project_id)
        return current._info

    def get_allocated_cinder_quota(self):
        kwargs = {}
        total = 0

        quotas = self.get_quota('volume')
        if not quotas:
            return {}
        for quota in quotas:
            kwargs["volumes_%s" % (quota.zone)] = quota.quota
            kwargs["gigabytes_%s" % (quota.zone)] = quota.quota
            kwargs["snapshots_%s" % (quota.zone)] = quota.quota
            total += quota.quota
        kwargs['volumes'] = total
        kwargs['gigabytes'] = total
        kwargs['snapshots'] = total
        return kwargs

    def set_cinder_quota(self):
        allocated_quota = self.get_allocated_cinder_quota()
        if self.noop and allocated_quota:
            LOG.info("%s: Would set cinder quota to %s", self.id,
                     allocated_quota)
            return
        client = auth.get_cinder_client(self.ks_session)
        client.quotas.delete(tenant_id=self.project_id)
        if allocated_quota:
            client.quotas.update(tenant_id=self.project_id, **allocated_quota)
            LOG.info("%s: Set Cinder Quota %s", self.id, allocated_quota)

    def get_current_swift_quota(self):
        if not self.project_id:
            return {}
        SWIFT_QUOTA_KEY = 'x-account-meta-quota-bytes'
        client = auth.get_swift_client(self.ks_session,
                                       project_id=self.project_id)
        account = client.get_account()
        try:
            quota = int(account[0][SWIFT_QUOTA_KEY]) / 1024 / 1024 / 1024
        except KeyError:
            quota = 0
        return {'object': quota}

    def get_allocated_swift_quota(self):
        quotas = self.get_quota('object')
        if len(quotas) > 1:
            raise
        if quotas:
            gigabytes = int(quotas[0].quota)
        else:
            gigabytes = 0
        return {'object': gigabytes}

    def set_swift_quota(self):
        allocated_quota = self.get_allocated_swift_quota()
        quota_bytes = allocated_quota['object'] * 1024 * 1024 * 1024
        SWIFT_QUOTA_KEY = 'x-account-meta-quota-bytes'

        if self.noop:
            LOG.info("%s: Would set Swift Quota: bytes=%s", self.id,
                     quota_bytes)
            return
        client = auth.get_swift_client(self.ks_session,
                                       project_id=self.project_id)
        client.post_account(
            headers={SWIFT_QUOTA_KEY: quota_bytes})
        LOG.info("%s: Set Swift Quota: bytes=%s", self.id, quota_bytes)

    def get_current_trove_quota(self):
        if not self.project_id:
            return {}
        client = auth.get_trove_client(self.ks_session)
        current = client.quota.show(self.project_id)
        data = {}
        for resource in current:
            data[resource.resource] = resource.limit
        return data

    def get_allocated_trove_quota(self):
        quotas = self.get_quota('database')
        if not quotas:
            return {}
        kwargs = {}
        for quota in quotas:
            quota_resource = quota.resource.split('.')[1]
            kwargs[quota_resource] = quota.quota

        if 'volumes' not in kwargs:
            kwargs['volumes'] = int(kwargs['instances']) * 20
        if 'instances' not in kwargs:
            kwargs['instances'] = 2
        return kwargs

    def set_trove_quota(self):
        allocated_quota = self.get_allocated_trove_quota()

        if self.noop:
            LOG.info("%s: Would set Trove Quota: %s", self.id, allocated_quota)
            return
        client = auth.get_trove_client(self.ks_session)
        client.quota.update(self.project_id, allocated_quota)
        LOG.info("%s: Set Trove Quota: %s", self.id, allocated_quota)

    def get_current_manila_quota(self):
        if not self.project_id:
            return {}
        client = auth.get_manila_client(self.ks_session)
        quotas = client.quotas.get(self.project_id)._info
        for share_type in client.share_types.list():
            type_quotas = client.quotas.get(self.project_id,
                                           share_type=share_type.id)
            type_quotas = {k + '_%s' % share_type.name: v
                           for k, v in type_quotas._info.items()}
            quotas.update(type_quotas)
        return quotas

    def get_allocated_manila_quota(self):
        kwargs = {}
        kwargs = {'shares': 0, 'gigabytes': 0,
                  'snapshots': 0, 'snapshot_gigabytes': 0}

        quotas = self.get_quota('share')
        for quota in quotas:
            quota_resource = quota.resource.split('.')[1]
            kwargs["%s_%s" % (quota_resource, quota.zone)] = quota.quota
            kwargs[quota_resource] += quota.quota
        return kwargs

    def set_manila_quota(self):
        allocated_quota = self.get_allocated_manila_quota()
        if self.noop:
            LOG.info("%s: Would set manila quota to %s", self.id,
                     allocated_quota)
            return
        client = auth.get_manila_client(self.ks_session)
        client.quotas.delete(tenant_id=self.project_id)

        global_quota = {
            'shares': allocated_quota.pop('shares'),
            'gigabytes': allocated_quota.pop('gigabytes'),
            'snapshots': allocated_quota.pop('snapshots'),
            'snapshot_gigabytes': allocated_quota.pop('snapshot_gigabytes')}

        client.quotas.update(tenant_id=self.project_id, **global_quota)
        LOG.info("%s: Set Global Manila Quota %s", self.id, allocated_quota)
        for share_type in client.share_types.list():
            client.quotas.delete(tenant_id=self.project_id,
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
                LOG.info("%s: Set Manila Quota for %s to %s", self.id,
                         share_type.name, type_quotas)
                client.quotas.update(tenant_id=self.project_id,
                                     share_type=share_type.id, **type_quotas)

    def get_current_neutron_quota(self):
        if not self.project_id:
            return {}
        client = auth.get_neutron_client(self.ks_session)
        return client.show_quota(self.project_id)['quota']

    def get_allocated_neutron_quota(self):
        quotas = self.get_quota('network')
        if not quotas:
            return {}
        kwargs = {}
        for quota in quotas:
            quota_resource = quota.resource.split('.')[1]
            kwargs[quota_resource] = quota.quota
        if 'network' in kwargs:
            kwargs['subnet'] = kwargs['network']
        return kwargs

    def set_neutron_quota(self):
        allocated_quota = self.get_allocated_neutron_quota()
        if self.noop:
            LOG.info("%s: Would set Neutron Quota: %s", self.id,
                     allocated_quota)
            return

        client = auth.get_neutron_client(self.ks_session)
        try:
            client.delete_quota(self.project_id)
        except neutronclient.common.exceptions.NotFound:
            pass

        if allocated_quota:
            body = {'quota': allocated_quota}
            client.update_quota(self.project_id, body)
            LOG.info("%s: Set Neutron Quota: %s", self.id, allocated_quota)
