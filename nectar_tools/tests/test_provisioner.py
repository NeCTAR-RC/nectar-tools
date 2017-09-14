import testfixtures
from unittest import mock

from keystoneauth1 import exceptions as keystone_exc

from nectar_tools import allocations
from nectar_tools import config
from nectar_tools import exceptions
from nectar_tools import test

from nectar_tools.tests import fakes


PROJECT = fakes.FakeProject('active')
CONF = config.CONFIG


@mock.patch('nectar_tools.auth.get_session', new=mock.Mock())
class ProvisionerTests(test.TestCase):

    def test_init(self):
        manager = fakes.FakeAllocationManager()
        data = fakes.FAKE_ALLOCATION
        allocation = allocations.Allocation(manager, data, None)

        self.assertEqual(allocation.project_id, data['project_id'])
        self.assertEqual(len(allocation.quotas), len(data['quotas']))
        self.assertIsInstance(allocation.quotas[0], allocations.Quota)

    def test_provision(self):
        manager = fakes.FakeAllocationManager()
        data = fakes.FAKE_ALLOCATION
        allocation = allocations.Allocation(manager, data, None)

        with test.nested(
            mock.patch.object(allocation, 'k_client'),
            mock.patch.object(allocation, 'update_project'),
            mock.patch.object(allocation, 'set_quota'),
            mock.patch.object(allocation, 'notify'),
        ) as (mock_keystone, mock_update, mock_quota, mock_notify):
            allocation.provision()
            mock_update.assert_called_once_with()
            mock_quota.assert_called_once_with()
            mock_notify.assert_called_once_with()

    def test_provision_project_not_found(self):
        manager = fakes.FakeAllocationManager()
        data = fakes.FAKE_ALLOCATION
        allocation = allocations.Allocation(manager, data, None)

        with test.nested(
            mock.patch.object(allocation, 'k_client'),
            mock.patch.object(allocation, 'set_quota'),
            mock.patch.object(allocation, 'notify'),
        ) as (mock_keystone, mock_quota, mock_notify):
            mock_keystone.projects.get.side_effect = \
             keystone_exc.http.NotFound()
            with testfixtures.ShouldRaise(exceptions.InvalidProjectAllocation):
                allocation.provision()
            mock_quota.assert_not_called()
            mock_notify.assert_not_called()

    def test_provision_new(self):
        manager = fakes.FakeAllocationManager()
        data = fakes.FAKE_ALLOCATION
        allocation = allocations.Allocation(manager, data, None)
        allocation.project_id = None
        allocation.tenant_name = None
        allocation.convert_trial_project = False
        allocation.project_name = 'My Project.is__great'

        with test.nested(
            mock.patch.object(allocation, 'k_client'),
            mock.patch.object(allocation, 'create_project'),
            mock.patch.object(allocation, 'set_quota'),
            mock.patch.object(allocation, 'notify'),
        ) as (mock_keystone, mock_create, mock_quota,
              mock_notify):
            mock_keystone.projects.find.side_effect = keystone_exc.NotFound()
            allocation.provision()
            mock_create.assert_called_once_with()
            mock_quota.assert_called_once_with()
            mock_notify.assert_called_once_with()

    def test_provision_new_duplicate_name(self):
        manager = fakes.FakeAllocationManager()
        data = fakes.FAKE_ALLOCATION
        allocation = allocations.Allocation(manager, data, None)
        allocation.project_id = None
        allocation.tenant_name = None
        allocation.convert_trial_project = False
        allocation.project_name = 'My Project.is__great'

        with test.nested(
            mock.patch.object(allocation, 'k_client'),
            mock.patch.object(allocation, 'create_project'),
            mock.patch.object(allocation, 'set_quota'),
            mock.patch.object(allocation, 'notify'),
        ) as (mock_keystone, mock_create, mock_quota,
              mock_notify):
            with testfixtures.ShouldRaise(exceptions.InvalidProjectAllocation):
                allocation.provision()

            mock_create.assert_not_called()
            mock_quota.assert_not_called()
            mock_notify.assert_not_called()

    def test_provision_convert_pt(self):
        manager = fakes.FakeAllocationManager()
        data = fakes.FAKE_ALLOCATION
        allocation = allocations.Allocation(manager, data, None)
        allocation.project_id = None
        allocation.tenant_name = None
        allocation.convert_trial_project = True

        with test.nested(
            mock.patch.object(allocation, 'k_client'),
            mock.patch.object(allocation, 'convert_trial'),
            mock.patch.object(allocation, 'set_quota'),
            mock.patch.object(allocation, 'notify'),
        ) as (mock_keystone, mock_convert, mock_quota,
              mock_notify):
            mock_keystone.projects.find.side_effect = keystone_exc.NotFound()
            allocation.provision()
            mock_convert.assert_called_once_with()
            mock_quota.assert_called_once_with()
            mock_notify.assert_called_once_with()

    def test_create_project(self):
        manager = fakes.FakeAllocationManager()
        data = fakes.FAKE_ALLOCATION
        allocation = allocations.Allocation(manager, data, None)

        with test.nested(
            mock.patch.object(allocation, 'k_client'),
            mock.patch.object(allocation, 'update')
        ) as (mock_keystone, mock_update):
            mock_keystone.projects.create.return_value = fakes.FakeProject()

            project = allocation.create_project()

            mock_keystone.projects.create.assert_called_once_with(
                name=allocation.tenant_name,
                domain='default',
                description=allocation.project_name,
                allocation_id=allocation.id,
                expires=allocation.end_date
            )
            mock_update.assert_called_once_with(project_id=project.id)

    def test_update_project(self):
        manager = fakes.FakeAllocationManager()
        data = fakes.FAKE_ALLOCATION
        allocation = allocations.Allocation(manager, data, None)

        with mock.patch.object(allocation, 'k_client') as mock_keystone:
            allocation.update_project()

            mock_keystone.projects.update.assert_called_once_with(
                allocation.project_id,
                allocation_id=allocation.id,
                expires=allocation.end_date)

    def test_grant_owner_roles(self):
        manager = fakes.FakeAllocationManager()
        data = fakes.FAKE_ALLOCATION
        allocation = allocations.Allocation(manager, data, None)
        project = fakes.FakeProject()

        with mock.patch.object(allocation, 'k_client') as mock_keystone:
            manager = mock.Mock()
            mock_keystone.users.find.return_value = manager
            allocation._grant_owner_roles(project)

            role_calls = [mock.call(CONF.keystone.manager_role_id,
                                    project=project, user=manager),
                          mock.call(CONF.keystone.member_role_id,
                                    project=project, user=manager)]
            mock_keystone.roles.grant.assert_has_calls(role_calls)

    def test_update(self):
        manager = fakes.FakeAllocationManager()
        data = fakes.FAKE_ALLOCATION
        allocation = allocations.Allocation(manager, data, None)

        with mock.patch.object(allocation, 'manager') as mock_manager:
            allocation.update(foo='bar')
            mock_manager.update_allocation.assert_called_once_with(
                allocation, foo='bar')

    def test_get_quotas(self):
        manager = fakes.FakeAllocationManager()
        data = fakes.FAKE_ALLOCATION
        allocation = allocations.Allocation(manager, data, None)

        quotas = allocation.get_quota('object')
        self.assertEqual(100, quotas[0].quota)

        quotas = allocation.get_quota('volume')
        self.assertEqual(2, len(quotas))

    @mock.patch('nectar_tools.auth.get_nova_client')
    def test_set_nova_quota(self, mock_nova):
        nova_client = mock.Mock()
        mock_nova.return_value = nova_client
        manager = fakes.FakeAllocationManager()
        data = fakes.FAKE_ALLOCATION
        allocation = allocations.Allocation(manager, data, None)

        allocation.set_nova_quota()
        nova_client.quotas.update.assert_called_once_with(
            tenant_id=allocation.project_id,
            cores=allocation.core_quota,
            instances=allocation.instance_quota,
            ram=allocation.core_quota * 4096)

    @mock.patch('nectar_tools.auth.get_cinder_client')
    def test_set_cinder_quota(self, mock_cinder):
        cinder_client = mock.Mock()
        mock_cinder.return_value = cinder_client
        manager = fakes.FakeAllocationManager()
        data = fakes.FAKE_ALLOCATION
        allocation = allocations.Allocation(manager, data, None)
        allocation.set_cinder_quota()
        cinder_client.quotas.delete.assert_called_once_with(
            tenant_id=allocation.project_id)
        cinder_client.quotas.update.assert_called_once_with(
            tenant_id=allocation.project_id,
            gigabytes=130,
            volumes=130,
            gigabytes_melbourne=30,
            gigabytes_monash=100,
            volumes_melbourne=30,
            volumes_monash=100)

    @mock.patch('nectar_tools.auth.get_swift_client')
    def test_set_swift_quota(self, mock_swift):
        swift_client = mock.Mock()
        mock_swift.return_value = swift_client
        manager = fakes.FakeAllocationManager()
        data = fakes.FAKE_ALLOCATION
        allocation = allocations.Allocation(manager, data, None)
        allocation.set_swift_quota()
        quota = 100 * 1024 * 1024 * 1024
        swift_client.post_account.assert_called_once_with(
            headers={'x-account-meta-quota-bytes': quota})

    @mock.patch('nectar_tools.auth.get_trove_client')
    def test_set_trove_quota(self, mock_trove):
        trove_client = mock.Mock()
        mock_trove.return_value = trove_client
        manager = fakes.FakeAllocationManager()
        data = fakes.FAKE_ALLOCATION
        allocation = allocations.Allocation(manager, data, None)
        allocation.set_trove_quota()

        trove_client.quota.update.assert_called_once_with(
            allocation.project_id, {'instances': 2,
                                    'volumes': 100})

    def test_convert_trial(self):
        manager = fakes.FakeAllocationManager()
        data = fakes.FAKE_ALLOCATION
        allocation = allocations.Allocation(manager, data, None)

        with test.nested(
            mock.patch.object(allocation, 'k_client'),
            mock.patch.object(allocation, 'update'),
            mock.patch('nectar_tools.expiry.archiver.NovaArchiver')
        ) as (mock_keystone, mock_update, mock_archiver):
            old_pt = fakes.FakeProject(name='pt-123', description='abc')
            project = fakes.FakeProject(id='123')
            manager = mock.Mock()
            mock_keystone.users.find.return_value = manager
            mock_keystone.projects.get.return_value = old_pt
            mock_keystone.projects.update.return_value = project
            archiver = mock.Mock()
            mock_archiver.return_value = archiver
            allocation.convert_trial()

            mock_keystone.projects.create.assert_called_once_with(
                name=old_pt.name,
                domain=old_pt.domain_id,
                description=old_pt.description)

            mock_keystone.projects.update.assert_called_once_with(
                old_pt.id,
                name=allocation.tenant_name,
                description=allocation.project_name,
                status='',
                expiry_next_step='',
                expiry_status='',
                expiry_ticket_id=0,
                expiry_updated_at=''
            )

            archiver.enable_resources.assert_called_once_with()

    def test_convert_trial_no_user(self):
        manager = fakes.FakeAllocationManager()
        data = fakes.FAKE_ALLOCATION
        allocation = allocations.Allocation(manager, data, None)

        with mock.patch.object(allocation, 'k_client') as mock_keystone:
            mock_keystone.users.find.side_effect = keystone_exc.NotFound()
            with testfixtures.ShouldRaise(exceptions.InvalidProjectAllocation):
                allocation.convert_trial()

    def test_convert_trial_non_pt(self):
        manager = fakes.FakeAllocationManager()
        data = fakes.FAKE_ALLOCATION
        allocation = allocations.Allocation(manager, data, None)

        with test.nested(
            mock.patch.object(allocation, 'k_client'),
            mock.patch.object(allocation, 'update')
        ) as (mock_keystone, mock_update):
            old_pt = fakes.FakeProject(name='notpt')
            mock_keystone.projects.get.return_value = old_pt
            with testfixtures.ShouldRaise(exceptions.InvalidProjectAllocation):
                allocation.convert_trial()
