from freezegun import freeze_time
from unittest import mock

from nectar_tools import auth
from nectar_tools import config
from nectar_tools import exceptions
from nectar_tools import test
from nectar_tools import utils

from nectar_tools.tests import fakes

from nectarallocationclient import exceptions as allocation_exceptions

PROJECT = fakes.FakeProject('active')
CONF = config.CONFIG


@freeze_time("2017-01-01")
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
                fakes.FakeInstance(availability_zone='nova')]

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

    def test_get_allocation_active(self):
        project = fakes.FakeProject()
        mock_allocations = fakes.FakeAllocationManager()
        active = mock_allocations.get_current('active')
        with mock.patch.object(auth, 'get_allocation_client') as mock_a_client:
            mock_a_client.return_value.allocations.get_current.return_value \
                    = active
            output = utils.get_allocation(None, project.id)
            mock_a_client.return_value.allocations.get_current\
                    .assert_called_once_with(project_id=project.id)
            self.assertEqual(active, output)

    def test_get_allocation_no_allocation(self):
        project = fakes.FakeProject()

        with mock.patch.object(auth, 'get_allocation_client') as mock_a_client:
            mock_a_client.return_value.allocations.get_current.side_effect = \
                allocation_exceptions.AllocationDoesNotExist()

            self.assertRaises(exceptions.AllocationDoesNotExist,
                              utils.get_allocation, None, project.id)

    def test_get_allocation_no_allocation_force(self):
        project = fakes.FakeProject()

        with mock.patch.object(auth, 'get_allocation_client') as mock_a_client:
            mock_a_client.return_value.allocations.get_current.side_effect = \
                allocation_exceptions.AllocationDoesNotExist()

            output = utils.get_allocation(
                None, project.id, force_no_allocation=True)
            self.assertEqual('NO-ALLOCATION', output.id)

    def test_get_allocation_active_pending(self):
        project = fakes.FakeProject()

        mock_allocations = fakes.FakeAllocationManager()
        pending2 = mock_allocations.get_current('pending2')
        active = mock_allocations.get_current('active')

        with mock.patch.object(auth, 'get_allocation_client') as mock_a_client:
            mock_a_client.return_value.allocations.get_current.return_value \
                    = pending2
            mock_a_client.return_value.allocations.get_last_approved.\
                    return_value = active
            output = utils.get_allocation(None, project.id)
            mock_a_client.return_value.allocations.get_current.\
                    assert_called_once_with(project_id=project.id)
            self.assertEqual(pending2, output)

    def test_get_allocation_active_pending_expired(self):
        project = fakes.FakeProject()

        mock_allocations = fakes.FakeAllocationManager()
        pending1 = mock_allocations.get_current('pending1')
        active = mock_allocations.get_current('active')

        with mock.patch.object(auth, 'get_allocation_client') as mock_a_client:
            mock_a_client.return_value.allocations.get_current.return_value \
                    = pending1
            mock_a_client.return_value.allocations.get_last_approved.\
                    return_value = active
            output = utils.get_allocation(None, project.id)
            mock_a_client.return_value.allocations.get_current.\
                    assert_called_once_with(project_id=project.id)
            self.assertEqual(active, output)
