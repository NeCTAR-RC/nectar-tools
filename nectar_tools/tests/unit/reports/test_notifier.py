from unittest import mock

from nectar_tools.reports import notifier
from nectar_tools import test
from nectar_tools.tests import fakes


@mock.patch('freshdesk.v2.api.API')
class AllocationNotifierTests(test.TestCase):

    @mock.patch('nectar_tools.common.service_units.SUinfo')
    def test_send_over_budget(self, mock_su_info, mock_api):
        mock_su_info.return_value = mock.Mock(usage=10, budget=20, expected=9)
        allocation = fakes.get_allocation()
        n = notifier.AllocationNotifier(
            allocation=allocation, ks_session=mock.Mock())

        with mock.patch.object(n, 'send_message') as mock_send:
            n.send_over_budget()
            mock_send.assert_called_once_with(
                mock.ANY, {'su_used': '10.00',
                           'su_budget': '20.00',
                           'su_expected': '9.00'})

    @mock.patch('nectar_tools.utils.get_allocation_recipients')
    def test_send_message(self, mock_get_recipients, mock_api):
        email = 'x@y.org'
        cc = ['a@b.org', 'c@d.org']
        mock_get_recipients.return_value = email, cc

        allocation = fakes.get_allocation()
        n = notifier.AllocationNotifier(
            allocation=allocation, ks_session=mock.Mock())

        extra_context = mock.Mock()
        with mock.patch.object(n, '_create_ticket') as mock_create:
            n.send_message('this is the text', extra_context)
            mock_get_recipients.assert_called_once_with(n.k_client,
                                                        n.allocation)

            mock_create.assert_called_with(
                email=email,
                cc_emails=cc,
                description='this is the text',
                extra_context=extra_context,
                tags=['allocations', f'allocation-{allocation.id}'])
