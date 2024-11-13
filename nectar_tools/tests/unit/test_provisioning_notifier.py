from unittest import mock

from nectar_tools import config
from nectar_tools import test

from nectar_tools.provisioning import notifier

from nectar_tools.tests import fakes


CONF = config.CONFIG
PROJECT = fakes.FakeProject('active')


class ProvisioningNotifierTests(test.TestCase):
    def _test_send_provisioning(self, stage, template):
        mock_session = mock.Mock()
        n = notifier.ProvisioningNotifier(PROJECT, mock_session)
        self.assertEqual('provisioning', n.template_dir)
        notification_prefix = "Nectar Allocation Provisioned:"
        expected_subject = f"{notification_prefix} {PROJECT.name}"
        self.assertEqual(expected_subject, n.subject)
        allocation = mock.Mock()
        allocation.contact_email = 'owner@fake.org'
        with mock.patch.object(n, 'send_message') as mock_send:
            n.send_provisioning(
                stage,
                allocation,
                extra_context={'allocation': allocation},
                extra_recipients=['manager1@fake.org', 'manager2@fake.org'],
            )
            mock_send.assert_called_with(
                stage=template,
                owner='owner@fake.org',
                extra_recipients=['manager1@fake.org', 'manager2@fake.org'],
                extra_context={'allocation': allocation},
                tags=['allocations', f'allocation-{allocation.id}'],
            )

    def test_send_message_new(self):
        self._test_send_provisioning('new', 'allocation-new')

    def test_send_message_update(self):
        self._test_send_provisioning('update', 'allocation-update')
