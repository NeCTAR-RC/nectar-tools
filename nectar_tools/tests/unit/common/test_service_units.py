from freezegun import freeze_time
from unittest import mock

from nectar_tools.common import service_units
from nectar_tools import test
from nectar_tools.tests import fakes


class ServiceUnitsTests(test.TestCase):

    @mock.patch('nectar_tools.auth.get_cloudkitty_client')
    def test_get_allocation_usage(self, mock_get_cc):
        client = mock_get_cc.return_value
        session = mock.Mock()
        allocation = fakes.get_allocation()

        fake_results = [{'begin': 'date1', 'rate': 21}]

        client.summary.get_summary.return_value = {'results': fake_results}

        usage = service_units.get_allocation_usage(
            session, allocation)

        client.summary.get_summary.assert_called_once_with(
            begin=allocation.start_date, end=allocation.end_date,
            filters={'type': 'instance', 'project_id': allocation.project_id},
            response_format='object')

        self.assertEqual(21, usage)

    @mock.patch('nectar_tools.common.service_units.get_allocation_usage')
    def test_allocation_over_budget_no_budget(self, mock_get_usage):

        allocation = fakes.get_allocation()
        with mock.patch.object(allocation,
                               'get_allocated_cloudkitty_quota') as quota:
            quota.return_value = {'budget': 0}
            session = mock.Mock()

            self.assertFalse(service_units.allocation_over_budget(
                session, allocation))
            mock_get_usage.assert_not_called()

    @mock.patch('nectar_tools.common.service_units.get_allocation_usage')
    def test_allocation_over_budget(self, mock_get_usage):
        mock_get_usage.return_value = 4
        allocation = fakes.get_allocation()
        session = mock.Mock()

        with mock.patch.object(allocation,
                               'get_allocated_cloudkitty_quota') as quota:
            quota.return_value = {'budget': 10}

            allocation.start_date = '2017-01-01'
            allocation.end_date = '2017-01-10'

            # Should be over budget if date < 2017-01-05
            with freeze_time('2017-01-01'):
                self.assertTrue(service_units.allocation_over_budget(
                    session, allocation))
            with freeze_time('2017-01-03'):
                self.assertTrue(service_units.allocation_over_budget(
                    session, allocation))
            with freeze_time('2017-01-04'):
                self.assertTrue(service_units.allocation_over_budget(
                    session, allocation))
            with freeze_time('2017-01-05'):
                self.assertFalse(service_units.allocation_over_budget(
                    session, allocation))
            with freeze_time('2017-01-10'):
                self.assertFalse(service_units.allocation_over_budget(
                    session, allocation))
