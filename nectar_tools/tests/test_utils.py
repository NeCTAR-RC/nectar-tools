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

    def test_get_compute_zones(self):
        with mock.patch.object(auth, 'get_allocation_client') \
             as mock_get_client:
            a_client = mock_get_client.return_value
            a_client.zones.compute_homes.return_value = fakes.COMPUTE_HOMES
            zones = utils.get_compute_zones(None, self.allocation)
            self.assertEqual([], zones)

    def test_get_compute_zones_multiple(self):
        self.allocation.allocation_home = 'monash'
        with mock.patch.object(auth, 'get_allocation_client') \
             as mock_get_client:
            a_client = mock_get_client.return_value
            a_client.zones.compute_homes.return_value = fakes.COMPUTE_HOMES
            zones = utils.get_compute_zones(None, self.allocation)
            self.assertEqual(['monash-01', 'monash-02', 'monash-03'], zones)

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
