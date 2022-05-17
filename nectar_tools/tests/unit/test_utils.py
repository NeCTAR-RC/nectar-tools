from unittest import mock

from nectar_tools import auth
from nectar_tools import config
from nectar_tools import test
from nectar_tools import utils

from nectar_tools.tests import fakes


PROJECT = fakes.FakeProject('active')
CONF = config.CONFIG


class UtilsTests(test.TestCase):

    def setUp(self, *args, **kwargs):
        super(UtilsTests, self).setUp(*args, **kwargs)
        self.allocation = fakes.get_allocation()

    def test_get_compute_zones_national(self):
        self.allocation.associated_site = 'monash'
        self.allocation.national = True
        with mock.patch.object(auth, 'get_allocation_client') \
             as mock_get_client:
            a_client = mock_get_client.return_value
            a_client.zones.compute_homes.return_value = fakes.COMPUTE_HOMES
            zones = utils.get_compute_zones(None, self.allocation)
            self.assertEqual([], zones)

    def test_get_compute_zones_local(self):
        self.allocation.associated_site = 'qcif'
        self.allocation.national = False
        with mock.patch.object(auth, 'get_allocation_client') \
             as mock_get_client:
            a_client = mock_get_client.return_value
            a_client.zones.compute_homes.return_value = fakes.COMPUTE_HOMES
            zones = utils.get_compute_zones(None, self.allocation)
            self.assertEqual(['QRIScloud'], zones)

    def test_get_compute_zones_multiple(self):
        self.allocation.associated_site = 'monash'
        self.allocation.national = False
        with mock.patch.object(auth, 'get_allocation_client') \
             as mock_get_client:
            a_client = mock_get_client.return_value
            a_client.zones.compute_homes.return_value = fakes.COMPUTE_HOMES
            zones = utils.get_compute_zones(None, self.allocation)
            self.assertEqual(['monash-01', 'monash-02', 'monash-03'], zones)

    def test_get_compute_zones_local_no_site(self):
        # Test for anomalous 'associated_site' setting ...
        self.allocation.associated_site = None
        self.allocation.national = False
        with mock.patch.object(auth, 'get_allocation_client') \
             as mock_get_client:
            a_client = mock_get_client.return_value
            a_client.zones.compute_homes.return_value = fakes.COMPUTE_HOMES
            zones = utils.get_compute_zones(None, self.allocation)
            self.assertEqual([], zones)

    def test_get_out_of_zone_instances_no_instances(self):
        project = fakes.FakeProject()
        with test.nested(
            mock.patch.object(utils, 'get_compute_zones'),
            mock.patch('nectar_tools.expiry.archiver.NovaArchiver')
        ) as (mock_get_zones, mock_archiver):
            mock_get_zones.return_value = ['nova', 'nova-2']
            nova = mock.Mock()
            mock_archiver.return_value = nova
            nova._all_instances.return_value = []

            instances = utils.get_out_of_zone_instances(None, self.allocation,
                                                        project)
            self.assertEqual([], instances)

    def test_get_out_of_zone_instances_out_of_zone(self):
        project = fakes.FakeProject()
        with test.nested(
            mock.patch.object(utils, 'get_compute_zones'),
            mock.patch('nectar_tools.expiry.archiver.NovaArchiver')
        ) as (mock_get_zones, mock_archiver):
            mock_get_zones.return_value = ['nova', 'nova-2']
            nova = mock.Mock()
            mock_archiver.return_value = nova
            instance = fakes.FakeInstance(availability_zone='wrong')
            nova._all_instances.return_value = [
                instance,
                fakes.FakeInstance(availability_zone='nova'),
                fakes.FakeInstance(availability_zone='')]

            instances = utils.get_out_of_zone_instances(None, self.allocation,
                                                        project)
            self.assertEqual([instance], instances)

    def test_get_out_of_zone_instances_instances_in_zone(self):
        project = fakes.FakeProject()
        with test.nested(
            mock.patch.object(utils, 'get_compute_zones'),
            mock.patch('nectar_tools.expiry.archiver.NovaArchiver')
        ) as (mock_get_zones, mock_archiver):
            mock_get_zones.return_value = ['nova', 'nova-2']
            nova = mock.Mock()
            mock_archiver.return_value = nova
            nova._all_instances.return_value = [
                fakes.FakeInstance(availability_zone='nova-2'),
                fakes.FakeInstance(availability_zone='nova-2'),
                fakes.FakeInstance(availability_zone='nova')]

            instances = utils.get_out_of_zone_instances(None, self.allocation,
                                                        project)
            self.assertEqual([], instances)

    def test_is_email_address_valid(self):
        email = "name@fake.org"
        self.assertEqual(True, utils.is_email_address(email))

    def test_is_email_address_invalid(self):
        email1 = "fake@name@fake.org"
        email2 = "@fake.org"
        email3 = "fake"
        self.assertEqual(False, utils.is_email_address(email1))
        self.assertEqual(False, utils.is_email_address(email2))
        self.assertEqual(False, utils.is_email_address(email3))

    def test_get_emails(self):
        user1 = mock.Mock(email='fake1@fake.com', enabled=True)
        user2 = mock.Mock(spec=['email', 'enabled'], email='fake2@fake.com',
                          enabled=False)
        user3 = mock.Mock(email='fake3@fake.com', enabled=False, inactive=True)
        user4 = mock.Mock(email='fake4@fake.com', enabled=False,
                          inactive=False)
        user5 = mock.Mock(spec=['enabled'], enabled=True)
        user6 = mock.Mock(email='fake6-bogus', enabled=True)
        users = [user1, user2, user3, user4, user5, user6]
        emails = utils.get_emails(users)
        self.assertEqual(['fake1@fake.com', 'fake3@fake.com'], emails)

    def test_get_project_users(self):
        project = fakes.FakeProject()
        role = 'fakerole'
        role_assignments = [mock.Mock(), mock.Mock()]
        role_assignments[0].user = {}
        role_assignments[1].user = {}
        role_assignments[0].user['id'] = 'fakeuser1'
        role_assignments[1].user['id'] = 'fakeuser2'

        mock_keystone = mock.Mock()

        def user_side_effect(value):
            mock_user = mock.Mock()
            mock_user.id = value
            return mock_user

        mock_keystone.role_assignments.list.return_value = role_assignments
        mock_keystone.users.get.side_effect = user_side_effect

        users = utils.get_project_users(mock_keystone, project, 'fakerole')

        mock_keystone.role_assignments.list.assert_called_with(
            project=project, role=role)
        mock_keystone.users.get.assert_has_calls([mock.call('fakeuser1'),
                                                  mock.call('fakeuser2')])
        self.assertEqual(['fakeuser1', 'fakeuser2'], [x.id for x in users])
