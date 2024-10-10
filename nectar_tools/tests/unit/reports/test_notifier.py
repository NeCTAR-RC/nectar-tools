from unittest import mock

from nectar_tools.reports import notifier
from nectar_tools import test
from nectar_tools.tests import fakes


class AllocationNotifierTests(test.TestCase):
    @mock.patch('nectar_tools.common.service_units.SUinfo')
    @mock.patch('nectar_tools.utils.get_allocation_recipients')
    def test_send_over_budget(self, mock_get_recipients, mock_su_info):
        email = 'x@y.org'
        cc = ['a@b.org', 'c@d.org']
        mock_get_recipients.return_value = email, cc
        mock_su_info.return_value = mock.Mock(usage=10, budget=20, expected=9)
        allocation = fakes.get_allocation()
        n = notifier.AllocationNotifier(
            allocation=allocation, ks_session=mock.Mock()
        )
        with mock.patch.object(n, 'send_message') as mock_send:
            n.send_over_budget()
            mock_get_recipients.assert_called_once_with(
                n.k_client, n.allocation
            )
            mock_send.assert_called_once_with(
                stage='over-budget',
                extra_context={
                    'su_used': '10.00',
                    'su_budget': '20.00',
                    'su_expected': '9.00',
                },
                owner=email,
                extra_recipients=cc,
                tags=['allocations', f'allocation-{allocation.id}'],
            )
