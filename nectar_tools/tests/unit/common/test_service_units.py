import datetime
from freezegun import freeze_time
from unittest import mock

from nectar_tools.common import service_units
from nectar_tools import test
from nectar_tools.tests import fakes


class SUinfoTests(test.TestCase):

    def setUp(self):
        super().setUp()
        self.session = mock.Mock()
        self.allocation = fakes.get_allocation()

    def test_init(self):
        si = service_units.SUinfo(self.session, self.allocation)
        self.assertEqual(self.session, si.session)
        self.assertEqual(self.allocation, si.allocation)
        self.assertEqual(datetime.datetime(2015, 2, 26, 0, 0),
                         si.allocation_start)
        self.assertEqual(datetime.datetime(2015, 8, 25, 0, 0),
                         si.allocation_end)
        self.assertEqual(180, si.allocation_total_days)

    def test_over_budget(self):
        si = fakes.FakeSUinfo(usage=9.7, budget=10)
        self.assertFalse(si.over_budget())

        si = fakes.FakeSUinfo(usage=10, budget=10)
        self.assertTrue(si.over_budget())

        si = fakes.FakeSUinfo(usage=11.2, budget=10)
        self.assertTrue(si.over_budget())

    def test_over_80_percent(self):
        si = fakes.FakeSUinfo(usage=7.5, budget=10)
        self.assertFalse(si.over_80_percent())

        si = fakes.FakeSUinfo(usage=8, budget=10)
        self.assertTrue(si.over_80_percent())

        si = fakes.FakeSUinfo(usage=9, budget=10)
        self.assertTrue(si.over_80_percent())

    @mock.patch('nectar_tools.auth.get_cloudkitty_client')
    def test_usage(self, mock_get_cc):
        client = mock_get_cc.return_value

        si = service_units.SUinfo(self.session, self.allocation)

        fake_results = [{'begin': 'date1', 'rate': 21}]

        client.summary.get_summary.return_value = {'results': fake_results}

        # Call twice to ensure only 1 cloudkitty call
        usage = si.usage
        usage = si.usage

        client.summary.get_summary.assert_called_once_with(
            begin=self.allocation.start_date, end=self.allocation.end_date,
            filters={'project_id': self.allocation.project_id},
            response_format='object')

        self.assertEqual(21, usage)

    def test_budget(self):
        with mock.patch.object(self.allocation,
                               'get_allocated_cloudkitty_quota') as quota:
            quota.return_value = {'budget': 23}

            si = service_units.SUinfo(self.session, self.allocation)
            self.assertEqual(23, si.budget)
            # call again to ensure only one call
            si.budget
            quota.assert_called_once_with()

    def test_daily_average_budget(self):
        with mock.patch.object(self.allocation,
                               'get_allocated_cloudkitty_quota') as quota:
            quota.return_value = {'budget': 3600}

            si = service_units.SUinfo(self.session, self.allocation)
            # 3600 / 180 days
            self.assertEqual(20.0, si.daily_average_budget)

    @freeze_time("2015-04-01")
    def test_expected(self):
        with mock.patch.object(self.allocation,
                               'get_allocated_cloudkitty_quota') as quota:
            quota.return_value = {'budget': 3600}

            si = service_units.SUinfo(self.session, self.allocation)
            # 2015-02-26 -> 2015-04-01 == 34 days * 20su per day
            self.assertEqual(680.0, si.expected)

    def test_is_tracking_over(self):
        with mock.patch.object(self.allocation,
                               'get_allocated_cloudkitty_quota') as quota:
            quota.return_value = {'budget': 10}

            self.allocation.start_date = '2017-01-01'
            self.allocation.end_date = '2017-01-10'

            si = service_units.SUinfo(self.session, self.allocation)
            si._usage = 4

            # Should be over budget if date < 2017-01-05
            with freeze_time('2017-01-01'):
                self.assertTrue(si.is_tracking_over())
            with freeze_time('2017-01-03'):
                self.assertTrue(si.is_tracking_over())
            with freeze_time('2017-01-04'):
                self.assertTrue(si.is_tracking_over())
            with freeze_time('2017-01-05'):
                self.assertFalse(si.is_tracking_over())
            with freeze_time('2017-01-10'):
                self.assertFalse(si.is_tracking_over())
            with freeze_time('2017-01-11'):
                self.assertFalse(si.is_tracking_over())
            with freeze_time('2016-12-31'):
                self.assertFalse(si.is_tracking_over())

    def test_is_tracking_over_no_budget(self):
        with mock.patch.object(self.allocation,
                               'get_allocated_cloudkitty_quota') as quota:
            quota.return_value = {'budget': None}

            self.allocation.start_date = '2017-01-01'
            self.allocation.end_date = '2017-01-10'

            si = service_units.SUinfo(self.session, self.allocation)

            with freeze_time('2017-01-01'):
                self.assertFalse(si.is_tracking_over())
