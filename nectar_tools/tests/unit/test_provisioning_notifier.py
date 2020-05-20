from unittest import mock

from nectar_tools import config
from nectar_tools import test

from nectar_tools.provisioning import notifier

from nectar_tools.tests import fakes


CONF = config.CONFIG
PROJECT = fakes.FakeProject('active')


@mock.patch('freshdesk.v2.api.API')
@mock.patch('nectar_tools.auth.get_session', new=mock.Mock())
class ProvisioningNotifierTests(test.TestCase):

    def _test_send_message(self, stage, template):
        n = notifier.ProvisioningNotifier(PROJECT)

        self.assertEqual(int(CONF.freshdesk.provisioning_group), n.group_id)
        self.assertEqual('provisioning', n.template_dir)
        notification_prefix = "Nectar Allocation Provisioned:"
        expected_subject = "{} {}".format(notification_prefix, PROJECT.name)
        self.assertEqual(expected_subject, n.subject)
        allocation = mock.Mock()

        with test.nested(
                mock.patch.object(n, 'render_template'),
                mock.patch.object(n, '_create_ticket'),
        ) as (mock_render, mock_create):
            mock_render.return_value = 'text'
            n.send_message(stage, 'owner@fake.org',
                           extra_context={'allocation': allocation},
                           extra_recipients=['manager1@fake.org',
                                             'manager2@fake.org'])
            mock_render.assert_called_once_with(template,
                                                {'allocation': allocation})
            mock_create.assert_called_with(
                email='owner@fake.org',
                cc_emails=['manager1@fake.org', 'manager2@fake.org'],
                description='text',
                extra_context={'allocation': allocation},
                tags=['allocations'])

    def test_send_message_new(self, mock_api):
        self._test_send_message('new', 'allocation-new.tmpl')

    def test_send_message_update(self, mock_api):
        self._test_send_message('update', 'allocation-update.tmpl')
