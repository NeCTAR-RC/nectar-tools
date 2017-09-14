from keystoneauth1 import exceptions as keystone_exc
import logging

from nectar_tools import allocations
from nectar_tools import auth
from nectar_tools import config
from nectar_tools import exceptions
from nectar_tools.expiry import archiver


CONF = config.CONFIG
LOG = logging.getLogger(__name__)


class Quota(object):

    def __init__(self, manager, data):
        for key, value in data.items():
            setattr(self, key, value)

    def __repr__(self):
        return "<Quota %s %s %s>" % (self.zone, self.resource, self.quota)


class Allocation(object):

    def __init__(self, manager, data, ks_session):
        self.ks_session = ks_session
        self.k_client = auth.get_keystone_client(ks_session)
        self.quotas = []
        self.service_quotas = None
        self.manager = manager
        for key, value in data.items():
            if key == 'quotas':
                for quota in value:
                    self.quotas.append(allocations.Quota(manager, quota))
            else:
                setattr(self, key, value)

    def __repr__(self):
        return "<Allocation %s>" % self.id

    def provision(self):
        project = None
        if self.project_id:
            try:
                project = self.k_client.projects.get(self.project_id)
            except keystone_exc.NotFound as exc:
                raise exceptions.InvalidProjectAllocation(
                    "Existing project not found") from exc

        if not project:
            # New allocation
            try:
                self.k_client.projects.find(name=self.tenant_name)
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
            self.update_project()

        self.set_quota()
        self.notify()

    def create_project(self):
        # TODO(sorrison) Support other domains
        domain = 'default'
        project = self.k_client.projects.create(name=self.tenant_name,
                                                domain=domain,
                                                description=self.project_name,
                                                allocation_id=self.id,
                                                expires=self.end_date)
        LOG.info("%s: Created new keystone project %s", self.id, project.id)
        self.update(project_id=project.id)
        return project

    def _grant_owner_roles(self, project):
        try:
            manager = self.k_client.users.find(name=self.contact_email)
        except keystone_exc.NotFound as exc:
            raise exceptions.InvalidProjectAllocation() from exc

        self.k_client.roles.grant(CONF.keystone.manager_role_id,
                                  project=project,
                                  user=manager)
        LOG.info("%s: Add manager role to %s", self.id, manager.name)
        self.k_client.roles.grant(CONF.keystone.member_role_id,
                                  project=project,
                                  user=manager)
        LOG.info("%s: Add member role to %s", self.id, manager.name)

    def update_project(self):
        LOG.info("%s: Updating keystone project %s", self.id, self.project_id)
        project = self.k_client.projects.update(self.project_id,
                                                allocation_id=self.id,
                                                expires=self.end_date)
        return project

    def update(self, **kwargs):
        self.manager.update_allocation(self, **kwargs)
        for k, v in kwargs.items():
            setattr(self, k, v)

    def get_quota(self, service_type):
        mappings = {'volume': 'volume',
                    'object': 'object',
                    'database_instances': 'database',
                    'database_volumes': 'database'}

        if self.service_quotas is None:
            service_types = {}
            for quota in self.quotas:
                if mappings[quota.resource] in service_types:
                    service_types[mappings[quota.resource]].append(quota)
                else:
                    service_types[mappings[quota.resource]] = [quota]
            self.service_quotas = service_types

        try:
            return self.service_quotas[service_type]
        except KeyError:
            return []

    def set_quota(self):
        self.set_nova_quota()
        self.set_cinder_quota()
        self.set_swift_quota()
        self.set_trove_quota()

    def set_nova_quota(self):
        client = auth.get_nova_client(self.ks_session)
        ram = self.core_quota * 4096
        client.quotas.update(tenant_id=self.project_id,
                             cores=self.core_quota,
                             instances=self.instance_quota,
                             ram=ram)
        LOG.info("%s: Set Nova Quota instances=%s, cores=%s, ram=%s",
                 self.id, self.instance_quota, self.core_quota, ram)

    def set_cinder_quota(self):
        kwargs = {}
        total = 0
        quotas = self.get_quota('volume')
        client = auth.get_cinder_client(self.ks_session)
        client.quotas.delete(tenant_id=self.project_id)
        if quotas:
            for quota in quotas:
                kwargs["volumes_%s" % (quota.zone)] = quota.quota
                kwargs["gigabytes_%s" % (quota.zone)] = quota.quota
                total += quota.quota
            kwargs['volumes'] = total
            kwargs['gigabytes'] = total
            client.quotas.update(tenant_id=self.project_id, **kwargs)
            LOG.info("%s: Set Cinder Quota %s", self.id, kwargs)

    def set_swift_quota(self):
        quotas = self.get_quota('object')
        if len(quotas) > 1:
            raise
        if quotas:
            gigabytes = quotas[0].quota
        else:
            gigabytes = 0

        SWIFT_QUOTA_KEY = 'x-account-meta-quota-bytes'
        quota_bytes = int(gigabytes) * 1024 * 1024 * 1024
        client = auth.get_swift_client(self.ks_session,
                                       project_id=self.project_id)
        client.post_account(
            headers={SWIFT_QUOTA_KEY: quota_bytes})
        LOG.info("%s: Set Swift Quota: bytes=%s", self.id, quota_bytes)

    def set_trove_quota(self):
        quotas = self.get_quota('database')
        if not quotas:
            return
        client = auth.get_trove_client(self.ks_session)
        kwargs = {}
        for quota in quotas:
            quota_resource = quota.resource.split('_')[1]
            kwargs[quota_resource] = quota.quota

        if 'volumes' not in kwargs:
            kwargs['volumes'] = int(kwargs['instances']) * 20
        if 'instances' not in kwargs:
            kwargs['instances'] = 2

        client.quota.update(self.project_id, kwargs)
        LOG.info("%s: Set Trove Quota: %s", self.id, kwargs)

    def notify(self):
        pass

    def convert_trial(self):
        try:
            manager = self.k_client.users.find(name=self.contact_email)
        except keystone_exc.NotFound as exc:
            raise exceptions.InvalidProjectAllocation(
                "User for manager not found") from exc

        old_pt = self.k_client.projects.get(manager.default_project_id)
        if not old_pt.name.startswith('pt-'):
            raise exceptions.InvalidProjectAllocation(
                "User's default project is not a pt- project")

        self.k_client.projects.create(name=old_pt.name,
                                      domain=old_pt.domain_id,
                                      description=old_pt.description)

        # Rename existing pt to new project name/desc.
        # Reset status in case their pt- is pending suspension.
        project = self.k_client.projects.update(
            old_pt.id,
            name=self.tenant_name,
            description=self.project_name,
            status='',
            expiry_next_step='',
            expiry_status='',
            expiry_ticket_id=0,
            expiry_updated_at=''
        )

        self.update(project_id=project.id)

        nova_archiver = archiver.NovaArchiver(project, self.ks_session)
        nova_archiver.enable_resources()

        return project
