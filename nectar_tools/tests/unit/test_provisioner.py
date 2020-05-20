import datetime
import testfixtures
from unittest import mock

from dateutil import relativedelta
from keystoneauth1 import exceptions as keystone_exc
import novaclient

from nectar_tools import config
from nectar_tools import exceptions
from nectar_tools import test
from nectar_tools import utils

from nectar_tools.provisioning import manager

from nectar_tools.tests import fakes


PROJECT = fakes.FakeProject('active')
CONF = config.CONFIG


@mock.patch('nectar_tools.auth.get_session', new=mock.Mock())
class ProvisionerTests(test.TestCase):

    def setUp(self, *args, **kwargs):
        super(ProvisionerTests, self).setUp(*args, **kwargs)
        self.allocation = fakes.get_allocation()
        self.manager = manager.ProvisioningManager(ks_session=mock.Mock())

    def test_provision(self):
        """Test provisioning an existing allocation"""
        self.allocation.project_id = PROJECT.id

        with test.nested(
            mock.patch.object(self.manager, 'k_client'),
            mock.patch.object(self.manager, 'update_project'),
            mock.patch.object(self.manager, 'set_quota'),
            mock.patch.object(self.manager, 'quota_report'),
            mock.patch.object(self.manager, 'notify_provisioned'),
            mock.patch.object(self.manager, 'update_allocation'),
            mock.patch.object(self.manager, 'set_allocation_start_end'),
            mock.patch.object(self.manager, 'revert_expiry'),
            mock.patch.object(self.manager, 'send_event'),
            mock.patch('nectar_tools.expiry.archiver.DesignateArchiver'),
        ) as (mock_keystone, mock_update_project, mock_quota, mock_report,
              mock_notify, mock_update, mock_set_dates, mock_revert,
              mock_send_event, mock_designate):
            mock_update.return_value = self.allocation
            mock_set_dates.return_value = self.allocation
            project = fakes.FakeProject()
            mock_update_project.return_value = project
            mock_designate.return_value = mock.Mock()

            self.manager.provision(self.allocation)
            mock_update_project.assert_called_once_with(self.allocation)
            mock_designate.assert_called_with(
                project,
                self.manager.ks_session,
                dry_run=self.manager.noop)
            mock_designate.create_resources.called_once_with()
            mock_quota.assert_called_once_with(self.allocation)
            mock_report.assert_called_once_with(self.allocation, html=True,
                                                show_current=True)
            mock_notify.assert_called_once_with(self.allocation, False,
                                                project,
                                                mock_report.return_value)
            mock_send_event.assert_called_once_with(self.allocation, 'renewed')
            mock_update.assert_called_once_with(self.allocation,
                                                provisioned=True)
            mock_revert.assert_called_once_with(project=project)

    def test_provision_already_provisioned(self):
        self.allocation.provisioned = True
        self.allocation.project_id = PROJECT.id

        with test.nested(
            mock.patch.object(self.manager, 'k_client'),
            mock.patch.object(self.manager, 'set_quota'),
            mock.patch.object(self.manager, 'notify_provisioned'),
            mock.patch.object(self.manager, 'send_event'),
        ) as (mock_keystone, mock_quota, mock_notify, mock_send_event):
            mock_keystone.projects.get.side_effect = \
             keystone_exc.http.NotFound()
            with testfixtures.ShouldRaise(
                exceptions.InvalidProjectAllocation(
                    "Allocation already provisioned")):
                self.manager.provision(self.allocation)
            mock_quota.assert_not_called()
            mock_notify.assert_not_called()
            mock_send_event.assert_not_called()

    def test_provision_historical(self):
        self.allocation.parent_request = 123
        self.allocation.project_id = PROJECT.id

        with test.nested(
            mock.patch.object(self.manager, 'k_client'),
            mock.patch.object(self.manager, 'set_quota'),
            mock.patch.object(self.manager, 'notify_provisioned'),
            mock.patch.object(self.manager, 'send_event'),
        ) as (mock_keystone, mock_quota, mock_notify, mock_send_event):
            mock_keystone.projects.get.side_effect = \
             keystone_exc.http.NotFound()
            with testfixtures.ShouldRaise(
                exceptions.InvalidProjectAllocation(
                    "Allocation is historical")):
                self.manager.provision(self.allocation)
            mock_quota.assert_not_called()
            mock_notify.assert_not_called()
            mock_send_event.assert_not_called()

    def test_provision_force(self):
        self.manager.force = True
        self.allocation.provisioned = True
        self.allocation.project_id = PROJECT.id

        with test.nested(
            mock.patch.object(self.manager, 'k_client'),
            mock.patch.object(self.manager, 'update_project'),
            mock.patch.object(self.manager, 'set_quota'),
            mock.patch.object(self.manager, 'quota_report'),
            mock.patch.object(self.manager, 'notify_provisioned'),
            mock.patch.object(self.manager, 'send_event'),
            mock.patch.object(self.manager, 'update_allocation'),
            mock.patch.object(self.manager, 'revert_expiry'),
            mock.patch('nectar_tools.expiry.archiver.DesignateArchiver'),
        ) as (mock_keystone, mock_update_project, mock_quota, mock_report,
              mock_notify, mock_send_event, mock_update, mock_revert,
              mock_designate):
            mock_update.return_value = self.allocation
            project = fakes.FakeProject()
            mock_update_project.return_value = project
            mock_designate.return_value = mock.Mock()
            self.manager.provision(self.allocation)
            mock_update_project.assert_called_once_with(self.allocation)
            mock_send_event.assert_called_once_with(self.allocation, 'renewed')

    def test_provision_project_not_found(self):
        self.allocation.project_id = PROJECT.id

        with test.nested(
            mock.patch.object(self.manager, 'k_client'),
            mock.patch.object(self.manager, 'set_quota'),
            mock.patch.object(self.manager, 'notify_provisioned'),
            mock.patch.object(self.manager, 'send_event'),
        ) as (mock_keystone, mock_quota, mock_notify, mock_send_event):
            mock_keystone.projects.get.side_effect = \
             keystone_exc.http.NotFound()
            with testfixtures.ShouldRaise(
                exceptions.InvalidProjectAllocation(
                    "Existing project not found")):
                self.manager.provision(self.allocation)
            mock_quota.assert_not_called()
            mock_notify.assert_not_called()
            mock_send_event.assert_not_called()

    def test_provision_new(self):
        """Test provisioning a new allocation"""
        self.allocation.project_id = None
        self.allocation.project_name = None
        self.allocation.convert_trial_project = False
        self.allocation.project_description = 'My Project.is__great'

        with test.nested(
            mock.patch.object(self.manager, 'k_client'),
            mock.patch.object(self.manager, 'create_project'),
            mock.patch.object(self.manager, 'set_quota'),
            mock.patch.object(self.manager, 'quota_report'),
            mock.patch.object(self.manager, 'notify_provisioned'),
            mock.patch.object(self.manager, 'send_event'),
            mock.patch.object(self.manager, 'update_allocation'),
            mock.patch.object(self.manager, 'set_allocation_start_end'),
            mock.patch.object(self.manager, 'revert_expiry'),
            mock.patch('nectar_tools.expiry.archiver.DesignateArchiver'),
        ) as (mock_keystone, mock_create, mock_quota, mock_report,
              mock_notify, mock_send_event, mock_update, mock_set_dates,
              mock_revert, mock_designate):
            mock_update.return_value = self.allocation
            mock_set_dates.return_value = self.allocation
            project = fakes.FakeProject()
            mock_create.return_value = project
            mock_keystone.projects.find.side_effect = keystone_exc.NotFound()
            mock_designate.return_value = mock.Mock()
            self.manager.provision(self.allocation)
            mock_create.assert_called_once_with(self.allocation)
            mock_designate.create_resources.called_once_with()
            mock_quota.assert_called_once_with(self.allocation)
            mock_report.assert_called_once_with(self.allocation, html=True,
                                                show_current=False)
            mock_notify.assert_called_once_with(self.allocation, True, project,
                                                mock_report.return_value)
            mock_send_event.assert_called_once_with(self.allocation, 'new')
            update_calls = [mock.call(self.allocation, project_id=project.id),
                            mock.call(self.allocation, provisioned=True)]
            mock_update.assert_has_calls(update_calls)
            mock_revert.assert_not_called()

    def test_provision_new_duplicate_name(self):
        self.allocation.project_id = None
        self.allocation.project_name = None
        self.allocation.convert_trial_project = False
        self.allocation.project_description = 'My Project.is__great'

        with test.nested(
            mock.patch.object(self.manager, 'k_client'),
            mock.patch.object(self.manager, 'create_project'),
            mock.patch.object(self.manager, 'set_quota'),
            mock.patch.object(self.manager, 'notify_provisioned'),
            mock.patch.object(self.manager, 'send_event'),
        ) as (mock_keystone, mock_create, mock_quota,
              mock_notify, mock_send_event):
            with testfixtures.ShouldRaise(
                exceptions.InvalidProjectAllocation(
                "Project already exists")):
                self.manager.provision(self.allocation)

            mock_create.assert_not_called()
            mock_quota.assert_not_called()
            mock_notify.assert_not_called()
            mock_send_event.assert_not_called()

    def test_provision_convert_pt(self):
        self.allocation.project_id = None
        self.allocation.project_name = None
        self.allocation.convert_trial_project = True

        with test.nested(
            mock.patch.object(self.manager, 'k_client'),
            mock.patch.object(self.manager, 'convert_trial'),
            mock.patch.object(self.manager, 'set_quota'),
            mock.patch.object(self.manager, 'quota_report'),
            mock.patch.object(self.manager, 'notify_provisioned'),
            mock.patch.object(self.manager, 'send_event'),
            mock.patch.object(self.manager, 'update_allocation'),
            mock.patch.object(self.manager, 'set_allocation_start_end'),
            mock.patch.object(self.manager, 'revert_expiry'),
            mock.patch('nectar_tools.expiry.archiver.DesignateArchiver'),
        ) as (mock_keystone, mock_convert, mock_quota, mock_report,
              mock_notify, mock_send_event, mock_update, mock_set_dates,
              mock_revert, mock_designate):
            mock_update.return_value = self.allocation
            mock_set_dates.return_value = self.allocation
            project = fakes.FakeProject()
            mock_convert.return_value = project
            mock_keystone.projects.find.side_effect = keystone_exc.NotFound()
            mock_designate.return_value = mock.Mock()
            self.manager.provision(self.allocation)
            mock_convert.assert_called_once_with(self.allocation)
            mock_designate.create_resources.called_once_with()
            mock_quota.assert_called_once_with(self.allocation)
            mock_report.assert_called_once_with(self.allocation, html=True,
                                                show_current=True)
            mock_notify.assert_called_once_with(self.allocation, False,
                                                project,
                                                mock_report.return_value)
            mock_send_event.assert_called_once_with(self.allocation,
                                                    'pt-conversion')
            update_calls = [mock.call(self.allocation, project_id=project.id),
                            mock.call(self.allocation, provisioned=True)]
            mock_update.assert_has_calls(update_calls)
            mock_revert.assert_called_once_with(project=project)

    @mock.patch('nectar_tools.expiry.expirer.AllocationExpirer')
    def test_revert_expiry(self, mock_expirer):
        project = fakes.FakeProject()
        self.manager.revert_expiry(project)
        mock_expirer.assert_called_once_with(project, self.manager.ks_session,
                                             dry_run=False)
        mock_expirer.return_value.revert_expiry.assert_called_once_with()

    def test_update_allocation(self):
        new_allocation = 'foo'
        with test.nested(
                mock.patch.object(self.allocation, 'update'),
                mock.patch.object(self.allocation, 'manager')
        ) as (mock_update, mock_manager):
            mock_manager.get.return_value = new_allocation
            allocation = self.manager.update_allocation(
                self.allocation, provisioned=True)
            mock_update.assert_called_once_with(provisioned=True)
            self.assertEqual(new_allocation, allocation)

    def test_set_allocation_start_end(self):
        with mock.patch.object(
                self.manager, 'update_allocation') as mock_update:
            allocation = self.manager.set_allocation_start_end(self.allocation)
            start = datetime.date.today()
            duration = self.allocation.estimated_project_duration
            end = start + relativedelta.relativedelta(months=+duration)
            mock_update.assert_called_once_with(
                self.allocation,
                start_date=start.strftime('%Y-%m-%d'),
                end_date=end.strftime('%Y-%m-%d'))
            self.assertEqual(mock_update.return_value, allocation)

    def test_create_project(self):
        with test.nested(
            mock.patch.object(self.manager, 'k_client'),
            mock.patch.object(utils, 'get_compute_zones')
         ) as (mock_keystone, mock_get_zones):
            mock_get_zones.return_value = []
            fake_project = fakes.FakeProject()
            mock_keystone.projects.create.return_value = fake_project

            project = self.manager.create_project(self.allocation)

            mock_get_zones.assert_called_once_with(self.manager.ks_session,
                                                   self.allocation)
            mock_keystone.projects.create.assert_called_once_with(
                name=self.allocation.project_name,
                domain='default',
                description=self.allocation.project_description,
                allocation_id=self.allocation.id,
                compute_zones=""
            )
            self.assertEqual(fake_project, project)

    def test_create_project_local(self):
        with test.nested(
            mock.patch.object(self.manager, 'k_client'),
            mock.patch.object(utils, 'get_compute_zones')
         ) as (mock_keystone, mock_get_zones):
            mock_get_zones.return_value = ['melbourne-qh2-uom']
            fake_project = fakes.FakeProject()
            mock_keystone.projects.create.return_value = fake_project

            project = self.manager.create_project(self.allocation)

            mock_get_zones.assert_called_once_with(self.manager.ks_session,
                                                   self.allocation)
            mock_keystone.projects.create.assert_called_once_with(
                name=self.allocation.project_name,
                domain='default',
                description=self.allocation.project_description,
                allocation_id=self.allocation.id,
                compute_zones='melbourne-qh2-uom',
            )
            self.assertEqual(fake_project, project)

    def test_update_project(self):
        with test.nested(
            mock.patch.object(self.manager, 'k_client'),
            mock.patch.object(utils, 'get_compute_zones')
         ) as (mock_keystone, mock_get_zones):
            mock_get_zones.return_value = []

            self.manager.update_project(self.allocation)

            mock_keystone.projects.update.assert_called_once_with(
                self.allocation.project_id,
                name=self.allocation.project_name,
                description=self.allocation.project_description,
                allocation_id=self.allocation.id,
                compute_zones="")

    def test_update_project_local(self):
        with test.nested(
            mock.patch.object(self.manager, 'k_client'),
            mock.patch.object(utils, 'get_compute_zones')
         ) as (mock_keystone, mock_get_zones):
            mock_get_zones.return_value = ['tasmania', 'tasmania-s']

            self.manager.update_project(self.allocation)

            mock_keystone.projects.update.assert_called_once_with(
                self.allocation.project_id,
                name=self.allocation.project_name,
                description=self.allocation.project_description,
                allocation_id=self.allocation.id,
                compute_zones='tasmania,tasmania-s',
                )

    def test_grant_owner_roles(self):
        project = fakes.FakeProject()

        with mock.patch.object(self.manager, 'k_client') as mock_keystone:
            manager = mock.Mock()
            mock_keystone.users.find.return_value = manager
            self.manager._grant_owner_roles(self.allocation, project)

            role_calls = [mock.call(CONF.keystone.manager_role_id,
                                    project=project, user=manager),
                          mock.call(CONF.keystone.member_role_id,
                                    project=project, user=manager)]
            mock_keystone.roles.grant.assert_has_calls(role_calls)

    @mock.patch("nectar_tools.provisioning.notifier.ProvisioningNotifier")
    def test_notify_provisioned_new(self, mock_notifier_class):
        mock_notifier = mock.Mock()
        mock_notifier_class.return_value = mock_notifier
        with mock.patch.object(utils, 'get_compute_zones') as mock_get_zones:
            mock_get_zones.return_value = ['melbourne']
            self.manager.notify_provisioned(self.allocation, True, None,
                                            report='bar')
            mock_notifier.send_message.assert_called_once_with(
                'new', self.allocation.contact_email,
                extra_context={'allocation': self.allocation, 'report': 'bar',
                               'out_of_zone_instances': [],
                               'compute_zones': ['melbourne']})

    @mock.patch("nectar_tools.provisioning.notifier.ProvisioningNotifier")
    def test_notify_provisioned_update(self, mock_notifier_class):
        mock_notifier = mock.Mock()
        mock_notifier_class.return_value = mock_notifier
        with test.nested(
                mock.patch.object(utils, 'get_out_of_zone_instances'),
                mock.patch.object(utils, 'get_compute_zones'),
        ) as (mock_out_of_zone, mock_get_zones):
            fake_instances = [fakes.FakeInstance(), fakes.FakeInstance]
            mock_out_of_zone.return_value = fake_instances
            mock_get_zones.return_value = ['nova', 'nova2']

            self.manager.notify_provisioned(self.allocation, False, None,
                                            report='bar')
            mock_notifier.send_message.assert_called_once_with(
                'update', self.allocation.contact_email,
                extra_context={'allocation': self.allocation, 'report': 'bar',
                               'out_of_zone_instances': fake_instances,
                               'compute_zones': ['nova', 'nova2']})

    @mock.patch("nectar_tools.provisioning.notifier.ProvisioningNotifier")
    def test_notify_provisioned_disabled_allocation(self, mock_notifier_class):
        mock_notifier = mock.Mock()
        mock_notifier_class.return_value = mock_notifier
        self.allocation.notifications = False
        self.manager.notify_provisioned(self.allocation, True, None,
                                        report='bar')
        mock_notifier.send_message.assert_not_called()

    @mock.patch("nectar_tools.provisioning.notifier.ProvisioningNotifier")
    def test_notify_provisioned_disabled_setting(self, mock_notifier_class):
        mock_notifier = mock.Mock()
        mock_notifier_class.return_value = mock_notifier
        self.manager.no_notify = True
        self.manager.notify_provisioned(self.allocation, True, None,
                                        report='bar')
        mock_notifier.send_message.assert_not_called()

    @mock.patch('nectar_tools.provisioning.manager.oslo_messaging')
    def test_send_event(self, mock_oslo_messaging):
        mock_notifier = mock.Mock()
        mock_oslo_messaging.Notifier.return_value = mock_notifier
        m = manager.ProvisioningManager(ks_session=mock.Mock())
        m.send_event(self.allocation, 'new')
        mock_notifier.audit.assert_called_once_with(
            mock.ANY, 'provisioning.new',
            dict(allocation=self.allocation.to_dict()))

    def test_convert_trial(self):
        with test.nested(
            mock.patch.object(self.manager, 'k_client'),
            mock.patch.object(self.manager, 'get_project_metadata')
        ) as (mock_keystone, mock_metadata):
            old_pt = fakes.FakeProject(name='pt-123', description='abc')
            project = fakes.FakeProject(id='123')
            manager = mock.Mock()
            mock_keystone.users.find.return_value = manager
            mock_keystone.projects.get.return_value = old_pt
            mock_keystone.projects.create.return_value = project
            mock_keystone.projects.update.return_value = project
            fake_metadata = {'name': 'test', 'desc': 'foo'}
            mock_metadata.return_value = fake_metadata
            self.manager.convert_trial(self.allocation)

            new_pt_tmp_name = "%s_copy" % old_pt.name
            mock_keystone.projects.create.assert_called_once_with(
                name=new_pt_tmp_name,
                domain=old_pt.domain_id,
                description=old_pt.description)

            mock_keystone.users.update(
                manager,
                default_project=mock_keystone.projects.create.return_value)

            calls = [
                mock.call(old_pt, **fake_metadata),
                mock.call(mock_keystone.projects.create.return_value,
                          name=old_pt.name
                      )
            ]
            mock_keystone.projects.update.assert_has_calls(calls)
            mock_keystone.roles.grant.assert_called_once_with(
                CONF.keystone.member_role_id,
                project=project,
                user=manager)

    def test_convert_trial_no_user(self):
        with mock.patch.object(self.manager, 'k_client') as mock_keystone:
            mock_keystone.users.find.side_effect = keystone_exc.NotFound()
            with testfixtures.ShouldRaise(exceptions.InvalidProjectAllocation):
                self.manager.convert_trial(self.allocation)

    def test_convert_trial_non_pt(self):
        with test.nested(
            mock.patch.object(self.manager, 'k_client'),
            mock.patch.object(self.manager, 'update_allocation')
        ) as (mock_keystone, mock_update):
            old_pt = fakes.FakeProject(name='notpt')
            mock_keystone.projects.get.return_value = old_pt
            with testfixtures.ShouldRaise(exceptions.InvalidProjectAllocation):
                self.manager.convert_trial(self.allocation)

    @mock.patch('nectar_tools.auth.get_nova_client')
    def test_get_current_nova_quota(self, mock_get_nova):
        self.allocation.project_id = PROJECT.id
        nova_client = mock.Mock()
        mock_get_nova.return_value = nova_client
        quota = {'instance': 30, 'ram': 1, 'cores': 33}
        quota_response = mock.Mock(_info=quota)
        nova_client.quotas.get.return_value = quota_response

        current = self.manager.get_current_nova_quota(self.allocation)
        self.assertEqual(quota, current)

    def test_set_nova_quota_no_ram(self):
        with test.nested(
            mock.patch.object(self.allocation, 'get_allocated_nova_quota'),
            mock.patch('nectar_tools.auth.get_nova_client')
        ) as (mock_alloc_nova_quota, mock_get_nova):
            nova_client = mock.Mock()
            mock_get_nova.return_value = nova_client
            quota = {'instances': 2, 'ram': 16, 'cores': 4}
            mock_alloc_nova_quota.return_value = quota
            self.manager.set_nova_quota(self.allocation)
            nova_client.quotas.delete.assert_called_once_with(
                tenant_id=self.allocation.project_id)
            nova_client.quotas.update.assert_called_once_with(
                tenant_id=self.allocation.project_id,
                force=True,
                cores=quota['cores'],
                instances=quota['instances'],
                ram=quota['ram'])

    @mock.patch('nectar_tools.auth.get_nova_client')
    def test_set_nova_quota_ram_set(self, mock_get_nova):
        nova_client = mock.Mock()
        mock_get_nova.return_value = nova_client
        # override and set ram quota to 2
        self.allocation.quotas[2].quota = 2

        self.manager.set_nova_quota(self.allocation)
        nova_client.quotas.delete.assert_called_once_with(
            tenant_id=self.allocation.project_id)
        nova_client.quotas.update.assert_called_once_with(
            tenant_id=self.allocation.project_id,
            force=True,
            cores=4,
            instances=2,
            ram=2048)

    def test_set_nova_quota_with_flavors(self):
        with test.nested(
                mock.patch.object(self.allocation, 'get_allocated_nova_quota'),
                mock.patch('nectar_tools.auth.get_nova_client'),
                mock.patch.object(self.manager, 'flavor_grant'),
        ) as (mock_get_allocated, mock_get_nova, mock_flavor_grant):
            nova_client = mock.Mock()
            mock_get_nova.return_value = nova_client
            quota = {'instances': 2, 'ram': 16, 'cores': 4,
                     'flavor:compute': 1, 'flavor:m2': 1}
            mock_get_allocated.return_value = quota
            self.manager.set_nova_quota(self.allocation)
            flavor_calls = [mock.call(self.allocation, 'compute'),
                            mock.call(self.allocation, 'm2')]

            mock_flavor_grant.assert_has_calls(flavor_calls, any_order=True)
            nova_client.quotas.delete.assert_called_once_with(
                tenant_id=self.allocation.project_id)
            nova_client.quotas.update.assert_called_once_with(
                tenant_id=self.allocation.project_id,
                force=True,
                cores=quota['cores'],
                instances=quota['instances'],
                ram=quota['ram'])

    @mock.patch('nectar_tools.auth.get_nova_client')
    def test_flavor_grant(self, mock_get_nova):
        nova_client = mock.Mock()
        mock_get_nova.return_value = nova_client

        def good_get_keys():
            return {'flavor_class:name': 'compute'}

        def bad_get_keys():
            return {'flavor_class:name': 'standard'}

        def none_get_keys():
            return {'foo': 'bar'}

        small = mock.Mock(get_keys=good_get_keys)
        small.name = 'c3.small'
        medium = mock.Mock(get_keys=good_get_keys)
        medium.name = 'c3.medium'
        large = mock.Mock(get_keys=good_get_keys)
        large.name = 'c3.large'
        other = mock.Mock(get_keys=bad_get_keys)
        other.name = 'c1.small'
        no_prefix = mock.Mock(get_keys=none_get_keys)
        no_prefix.name = 'custom-flavor'
        all_flavors = [small, medium, large, other, no_prefix]

        nova_client.flavors.list.return_value = all_flavors

        self.manager.flavor_grant(self.allocation, 'compute')
        calls = [mock.call(small, self.allocation.project_id),
                 mock.call(medium, self.allocation.project_id),
                 mock.call(large, self.allocation.project_id),
        ]
        nova_client.flavor_access.add_tenant_access.assert_has_calls(
            calls)

    @mock.patch('nectar_tools.auth.get_nova_client')
    def test_flavor_grant_exists(self, mock_get_nova):
        nova_client = mock.Mock()
        mock_get_nova.return_value = nova_client

        def good_get_keys():
            return {'flavor_class:name': 'compute'}

        small = mock.Mock(get_keys=good_get_keys)
        small.name = 'c3.small'
        all_flavors = [small]

        nova_client.flavors.list.return_value = all_flavors
        nova_client.flavor_access.add_tenant_access.side_effect = \
                                novaclient.exceptions.Conflict(code=409)
        self.manager.flavor_grant(self.allocation, 'compute')

    @mock.patch('nectar_tools.auth.get_cinder_client')
    def test_set_cinder_quota(self, mock_cinder):
        cinder_client = mock.Mock()
        mock_cinder.return_value = cinder_client

        self.manager.set_cinder_quota(self.allocation)
        cinder_client.quotas.delete.assert_called_once_with(
            tenant_id=self.allocation.project_id)
        cinder_client.quotas.update.assert_called_once_with(
            tenant_id=self.allocation.project_id,
            gigabytes=130,
            volumes=130,
            snapshots=130,
            gigabytes_melbourne=30,
            gigabytes_monash=100,
            volumes_melbourne=30,
            volumes_monash=100,
            snapshots_melbourne=30,
            snapshots_monash=100)

    @mock.patch('nectar_tools.auth.get_swift_client')
    def test_set_swift_quota(self, mock_swift):
        swift_client = mock.Mock()
        mock_swift.return_value = swift_client

        self.manager.set_swift_quota(self.allocation)
        quota = 100 * 1024 * 1024 * 1024
        swift_client.post_account.assert_called_once_with(
            headers={'x-account-meta-quota-bytes': quota})

    @mock.patch('nectar_tools.auth.get_trove_client')
    def test_set_trove_quota(self, mock_trove):
        trove_client = mock.Mock()
        mock_trove.return_value = trove_client

        self.manager.set_trove_quota(self.allocation)

        trove_client.quota.update.assert_called_once_with(
            self.allocation.project_id, {'instances': 2,
                                    'volumes': 100})

    @mock.patch('nectar_tools.auth.get_manila_client')
    def test_set_manila_quota(self, mock_manila):
        manila_client = mock.Mock()
        mock_manila.return_value = manila_client
        monash = mock.Mock(id='id-monash')
        monash.name = 'monash'
        qld = mock.Mock(id='id-qld')
        qld.name = 'qld'
        manila_client.share_types.list.return_value = [monash, qld]

        self.manager.set_manila_quota(self.allocation)

        delete_calls = [
            mock.call(tenant_id=self.allocation.project_id),
            mock.call(tenant_id=self.allocation.project_id,
                      share_type=monash.id),
            mock.call(tenant_id=self.allocation.project_id, share_type=qld.id),
        ]
        update_calls = [
            mock.call(tenant_id=self.allocation.project_id,
                      shares=11, gigabytes=150,
                      snapshots=5, snapshot_gigabytes=100),
            mock.call(tenant_id=self.allocation.project_id,
                      share_type=monash.id,
                      shares=6, gigabytes=50),
            mock.call(tenant_id=self.allocation.project_id, share_type=qld.id,
                      shares=5, gigabytes=100,
                      snapshots=5, snapshot_gigabytes=100),
        ]
        manila_client.quotas.delete.assert_has_calls(delete_calls)
        manila_client.quotas.update.assert_has_calls(update_calls)

    @mock.patch('nectar_tools.auth.get_neutron_client')
    def test_set_neutron_quota(self, mock_neutron):
        neutron_client = mock.Mock()
        mock_neutron.return_value = neutron_client
        current_quota = {'quota': {
            'security_group': 10, 'security_group_rule': 50}}
        neutron_client.show_quota = mock.Mock()
        neutron_client.show_quota.return_value = current_quota
        def_quota = {'quota': {
            'security_group': 5, 'security_group_rule': 10}}
        neutron_client.show_quota_default = mock.Mock()
        neutron_client.show_quota_default.return_value = def_quota
        self.manager.set_neutron_quota(self.allocation)
        neutron_client.delete_quota.assert_called_once_with(
            self.allocation.project_id)
        body = {
            'quota': {
                'floatingip': 1, 'network': 2, 'subnet': 2,
                'router': 2, 'loadbalancer': 2,
                'security_group': 10, 'security_group_rule': 50
            }
        }
        neutron_client.update_quota.assert_called_once_with(
            self.allocation.project_id, body)

    @mock.patch('nectar_tools.auth.get_neutron_client')
    def test_set_neutron_quota_default_secgroup_increase(self, mock_neutron):
        neutron_client = mock.Mock()
        mock_neutron.return_value = neutron_client
        current_quota = {'quota': {
            'security_group': 10, 'security_group_rule': 50}}
        neutron_client.show_quota = mock.Mock()
        neutron_client.show_quota.return_value = current_quota
        def_quota = {'quota': {
            'security_group': 20, 'security_group_rule': 100}}
        neutron_client.show_quota_default = mock.Mock()
        neutron_client.show_quota_default.return_value = def_quota
        self.manager.set_neutron_quota(self.allocation)
        neutron_client.delete_quota.assert_called_once_with(
            self.allocation.project_id)
        body = {
            'quota': {
                'floatingip': 1, 'network': 2, 'subnet': 2,
                'router': 2, 'loadbalancer': 2,
            }
        }
        neutron_client.update_quota.assert_called_once_with(
            self.allocation.project_id, body)
