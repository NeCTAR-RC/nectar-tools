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
        n = notifier.ProvisioningNotifier(project=PROJECT)

        self.assertEqual(int(CONF.freshdesk.provisioning_group), n.group_id)
        self.assertEqual('provisioning', n.template_dir)
        self.assertEqual("Nectar Allocation Provisioned", n.subject)
        manager = fakes.FakeAllocationManager()
        allocation = manager.get_current_allocation()
        with mock.patch.object(n, '_create_ticket') as mock_create:
            n.send_message(stage, 'owner@fake.org',
                           extra_context={'allocation': allocation},
                           extra_recipients=['manager1@fake.org',
                                             'manager2@fake.org'])
            mock_create.assert_called_with(
                email='owner@fake.org',
                cc_emails=['manager1@fake.org', 'manager2@fake.org'],
                description=n.render_template(template,
                                              {'allocation': allocation}),
                extra_context={'allocation': allocation},
                tags=['allocations'])

    def test_send_message_new(self, mock_api):
        self._test_send_message('new', 'allocation-new.tmpl')

    def test_send_message_update(self, mock_api):
        self._test_send_message('update', 'allocation-update.tmpl')
