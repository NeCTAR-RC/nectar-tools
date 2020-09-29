import datetime
from dateutil import relativedelta
from unittest import mock

from designateclient import exceptions as designate_exc
from keystoneauth1 import exceptions as keystone_exc

from nectar_tools import config
from nectar_tools.provisioning import manager
from nectar_tools import test
from nectar_tools.tests import fakes
from nectar_tools.tests.functional import fake_clients


CONF = config.CONFIG


@mock.patch('freshdesk.v2.api.API', new=fake_clients.FAKE_FD_API_CLASS)
@mock.patch('nectar_tools.auth.get_session', new=fake_clients.FAKE_GET_SESSION)
@mock.patch('nectar_tools.auth.get_designate_client',
            new=fake_clients.get_designate)
@mock.patch('nectar_tools.auth.get_nova_client', new=fake_clients.get_nova)
@mock.patch('nectar_tools.auth.get_cinder_client', new=fake_clients.get_cinder)
@mock.patch('nectar_tools.auth.get_swift_client', new=fake_clients.get_swift)
@mock.patch('nectar_tools.auth.get_neutron_client',
            new=fake_clients.get_neutron)
@mock.patch('nectar_tools.auth.get_trove_client', new=fake_clients.get_trove)
@mock.patch('nectar_tools.auth.get_magnum_client', new=fake_clients.get_magnum)
@mock.patch('nectar_tools.auth.get_manila_client', new=fake_clients.get_manila)
@mock.patch('nectar_tools.auth.get_keystone_client',
            new=fake_clients.get_keystone)
@mock.patch('nectar_tools.auth.get_openstacksdk',
            new=fake_clients.get_openstacksdk)
@mock.patch('nectar_tools.auth.get_allocation_client')
class ProvisionerTests(test.TestCase):

    def setUp(self, *args, **kwargs):
        super(ProvisionerTests, self).setUp(*args, **kwargs)
        self.allocation = fakes.get_allocation()

    def test_provision_convert_pt(self, mock_get_a_client):

        def fake_update(obj, **kwargs):
            for key, value in kwargs.items():
                setattr(obj, key, value)
            return obj

        keystone_client = fake_clients.FAKE_KEYSTONE
        designate_client = fake_clients.FAKE_DESIGNATE
        manager_user = mock.Mock()

        old_pt = fakes.FakeProject(id='q12w', name='pt-123', description='abc',
                                   domain_id='my-domain-id')
        new_pt = fakes.FakeProject(id='fr45tg', name='pt-123_copy',
                                   description='abc', domain_id='my-domain-id')

        keystone_client.projects.find.side_effect = keystone_exc.NotFound()
        keystone_client.users.find.return_value = manager_user
        keystone_client.projects.get.return_value = old_pt
        keystone_client.projects.create.return_value = new_pt
        keystone_client.projects.update.side_effect = fake_update

        mock_a_client = mock.Mock()
        mock_a_client.zones.compute_homes.return_value = {'uom': {'my-az'}}
        mock_a_client.allocations.get_current.return_value = self.allocation
        mock_get_a_client.return_value = mock_a_client

        self.allocation.project_id = None
        self.allocation.convert_trial_project = True
        self.allocation.allocation_home = 'uom'

        provisioning_manager = manager.ProvisioningManager(
            ks_session=mock.Mock())

        # Mock out update_allocation do reduce some complexity and allow easier
        # checking that updated values work their way through the code
        with mock.patch.object(provisioning_manager, 'update_allocation') \
                as mock_allocation_update:

            mock_allocation_update.side_effect = fake_update

            designate_client.zones.get.side_effect = designate_exc.NotFound

            allocation = provisioning_manager.provision(self.allocation)

            # Ensure old pt project is now the allocation
            self.assertEqual(old_pt.id, allocation.project_id)

            # Ensure allocation is provisioned and dates set correctly
            self.assertTrue(allocation.provisioned)
            start_date = datetime.date.today()
            duration_months = allocation.estimated_project_duration
            end_date = start_date + relativedelta.relativedelta(
                     months=+duration_months)
            end_date = end_date.strftime('%Y-%m-%d')
            self.assertEqual(start_date.strftime('%Y-%m-%d'),
                             allocation.start_date)
            self.assertEqual(end_date, allocation.end_date)

            # Ensure the new PT has same name/domain as old PT
            self.assertEqual(old_pt.name, new_pt.name)
            self.assertEqual(old_pt.domain_id, new_pt.domain_id)

            # We pass a session to the manager so we shouldn't be asking for
            # another one.
            fake_clients.FAKE_GET_SESSION.assert_not_called()

            # Ensure DNS setup
            dns_name = 'samtest2.example.com.'
            designate_client.zones.create.assert_called_once_with(
                dns_name, email=CONF.designate.zone_email)
            mock_zt = designate_client.zone_transfers
            mock_zt.create_request.assert_called_once_with(dns_name, old_pt.id)
            mock_zt.accept_request.assert_called_once_with(mock.ANY, mock.ANY)

            # Ensure the template contains what we think it should
            fd_api = fake_clients.FAKE_FD_API
            create_ticket_call = fd_api.tickets.create_outbound_email.call_args
            args, kwargs = create_ticket_call
            email_body = kwargs['description']
            self.assertIn('Thanks for your continued use', email_body)
            self.assertIn('approved as a National allocation.', email_body)
            self.assertIn('Project Name: %s' % allocation.project_name,
                          email_body)
            self.assertIn('Expires: %s' % end_date, email_body)
            # Count <tr> tags to determine amount of quotas
            self.assertEqual(len(allocation.quotas),
                             email_body.count('<tr>') - 1)
