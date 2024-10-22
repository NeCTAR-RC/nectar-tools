from unittest import mock

from freezegun import freeze_time

from nectar_tools import exceptions
from nectar_tools.reports import manager
from nectar_tools import test
from nectar_tools.tests import fakes


class ManagerTests(test.TestCase):
    def setUp(self):
        super().setUp()
        self.manager = manager.SUReporter(ks_session=mock.Mock())
        self.allocations = fakes.FakeAllocationManager()

    @mock.patch('nectar_tools.reports.notifier.AllocationNotifier')
    def test_send_over_budget_report(self, mock_notifier):
        allocation = self.allocations.get(id=1)
        notifier = mock_notifier.return_value
        self.manager.send_over_budget_report(allocation)
        mock_notifier.assert_called_once_with(
            allocation=allocation,
            ks_session=self.manager.ks_session,
            noop=self.manager.noop,
        )

        notifier.send_over_budget.assert_called_once_with()

    def test_send_all_reports(self):
        a1 = self.allocations.get(id=1)
        a2 = self.allocations.get(id=2)
        allocations = [a1, a2]

        with test.nested(
            mock.patch.object(self.manager, 'a_client'),
            mock.patch.object(self.manager, 'send_reports'),
        ) as (mock_allocation, mock_send):
            mock_allocation.allocations.list.return_value = allocations

            self.manager.send_all_reports()

            self.assertEqual(2, mock_send.call_count)

    def test_send_all_skip_to(self):
        a1 = self.allocations.get(id=1)
        a2 = self.allocations.get(id=2)
        allocations = [a1, a2]

        with test.nested(
            mock.patch.object(self.manager, 'a_client'),
            mock.patch.object(self.manager, 'send_reports'),
        ) as (mock_allocation, mock_send):
            mock_allocation.allocations.list.return_value = allocations

            self.manager.send_all_reports(skip_to=a2.id)

            self.assertEqual(1, mock_send.call_count)

    def test_send_reports_no_project_id(self):
        allocation = self.allocations.get(id=1)
        allocation.project_id = None
        with self.assertRaisesRegex(
            exceptions.InvalidProjectAllocation, "No project id"
        ):
            self.manager.send_reports(allocation)

    def test_send_reports_project_disabled(self):
        allocation = self.allocations.get(id=1)
        allocation.project_id = '123'
        with mock.patch.object(self.manager, 'k_client') as mock_keystone:
            mock_keystone.projects.get.return_value = fakes.FakeProject(
                enabled=False
            )

            with self.assertRaisesRegex(
                exceptions.InvalidProjectAllocation, "Project dummy disabled"
            ):
                self.manager.send_reports(allocation)

    @mock.patch('nectar_tools.common.service_units.SUinfo')
    def test_send_reports_under_budget(self, mock_su_info):
        mock_su_info.return_value = fakes.FakeSUinfo(tracking_over=False)
        allocation = self.allocations.get(id=1)
        allocation.project_id = '123'
        with test.nested(
            mock.patch.object(self.manager, 'k_client'),
            mock.patch.object(self.manager, 'send_over_budget_report'),
        ) as (mock_keystone, mock_send):
            mock_keystone.projects.get.return_value = fakes.FakeProject()

            self.manager.send_reports(allocation)
            mock_su_info.assert_called_once_with(
                self.manager.ks_session, allocation
            )
            mock_send.assert_not_called()

    @mock.patch('nectar_tools.common.service_units.SUinfo')
    def test_send_reports_over_budget(self, mock_su_info):
        mock_su_info.return_value = fakes.FakeSUinfo(tracking_over=True)
        allocation = self.allocations.get(id=1)
        allocation.project_id = '123'
        with test.nested(
            mock.patch.object(self.manager, 'k_client'),
            mock.patch.object(self.manager, 'send_over_budget_report'),
        ) as (mock_keystone, mock_send):
            mock_keystone.projects.get.return_value = fakes.FakeProject()

            self.manager.send_reports(allocation)
            mock_su_info.assert_called_once_with(
                self.manager.ks_session, allocation
            )
            mock_send.assert_called_once_with(allocation)

    @freeze_time('2022-01-08')
    @mock.patch('nectar_tools.common.service_units.SUinfo')
    def test_send_reports_over_budget_not_ready(self, mock_su_info):
        allocation = self.allocations.get(id=1)
        allocation.start_date = '2022-01-01'
        allocation.end_date = '2022-02-01'
        mock_su_info.return_value = fakes.FakeSUinfo(
            allocation=allocation, tracking_over=True
        )
        allocation.project_id = '123'
        with test.nested(
            mock.patch.object(self.manager, 'k_client'),
            mock.patch.object(self.manager, 'send_over_budget_report'),
        ) as (mock_keystone, mock_send):
            mock_keystone.projects.get.return_value = fakes.FakeProject()

            self.manager.send_reports(allocation)
            mock_su_info.assert_called_once_with(
                self.manager.ks_session, allocation
            )
            mock_send.assert_not_called()
