from unittest import mock

from nectar_tools import config
from nectar_tools import test

from nectar_tools.expiry import notifier

from nectar_tools.tests import fakes


CONF = config.CONFIG
PROJECT = fakes.FakeProject('active')


@mock.patch('freshdesk.v2.api.API')
@mock.patch('nectar_tools.auth.get_session', new=mock.Mock())
class ExpiryNotifierTests(test.TestCase):

    def _test_send_message(self, stage, template):
        n = notifier.ExpiryNotifier(
            project=PROJECT, template_dir='allocations',
            group_id=1, subject='Ticket-Subject %s' % PROJECT.name)

        with test.nested(
            mock.patch.object(n, '_create_ticket'),
            mock.patch.object(n, '_update_ticket'),
            mock.patch.object(n, '_set_ticket_id'),
            mock.patch.object(n, '_add_note_to_ticket')
        ) as (mock_create, mock_update, mock_id, mock_note):
            mock_create.return_value = 32
            n.send_message(stage, 'owner@fake.org',
                           extra_context={'foo': 'bar'},
                           extra_recipients=['manager1@fake.org',
                                             'manager2@fake.org'])
            mock_create.assert_called_with(
                email='owner@fake.org',
                cc_emails=['manager1@fake.org', 'manager2@fake.org'],
                description=n.render_template(template, {'foo': 'bar'}),
                extra_context={'foo': 'bar'},
                tags=['expiry'])
            mock_note.assert_called_with(
                32, n.render_template('project-details.tmpl', {'foo': 'bar'}))
            mock_id.assert_called_with(32)

    def test_send_message_first(self, mock_api):
        self._test_send_message('first', 'first-warning.tmpl')

    def test_send_message_second(self, mock_api):
        self._test_send_message('second', 'second-warning.tmpl')

    def test_send_message_final(self, mock_api):
        self._test_send_message('final', 'final-warning.tmpl')

    def test_send_message_update(self, mock_api):
        project = PROJECT
        project.expiry_ticket_id = 45
        n = notifier.ExpiryNotifier(
            project=project, template_dir='allocations',
            group_id=1, subject='Ticket-Subject %s' % PROJECT.name)

        with test.nested(
            mock.patch.object(n, '_create_ticket'),
            mock.patch.object(n, '_update_ticket_requester'),
            mock.patch.object(n, '_update_ticket'),
            mock.patch.object(n, '_set_ticket_id'),
            mock.patch.object(n, '_add_note_to_ticket')
        ) as (mock_create, mock_update_requester, mock_update, mock_id,
              mock_note):
            n.send_message('second', 'owner@fake.org',
                           extra_recipients=['manager1@fake.org'])
            mock_create.assert_not_called()
            mock_note.assert_not_called()
            mock_id.assert_not_called()
            mock_update_requester.assert_called_with(45, 'owner@fake.org')
            mock_update.assert_called_with(
                45, n.render_template('second-warning.tmpl'),
                cc_emails=['manager1@fake.org'])

    def test_finish(self, mock_api):
        project = fakes.FakeProject(expiry_ticket_id=22)
        n = notifier.ExpiryNotifier(
            project=project, template_dir='allocations',
            group_id=1, subject='subject')
        with mock.patch.object(n, '_add_note_to_ticket') as mock_note:
            n.finish()
            mock_note.assert_not_called()
            mock_api.return_value.tickets.update_ticket.assert_called_with(
                22, status=4)

    def test_finish_message(self, mock_api):
        project = fakes.FakeProject(expiry_ticket_id=22)
        n = notifier.ExpiryNotifier(
            project=project, template_dir='allocations',
            group_id=1, subject='subject')
        with mock.patch.object(n, '_add_note_to_ticket') as mock_note:
            n.finish(message='note-message')
            mock_note.assert_called_with(22, 'note-message')
            mock_api.return_value.tickets.update_ticket.assert_called_with(
                22, status=4)

    def test_set_ticket_id(self, mock_api):
        n = notifier.ExpiryNotifier(
            project=PROJECT, template_dir='allocations',
            group_id=1, subject='Ticket-Subject %s' % PROJECT.name)

        with mock.patch.object(n, 'k_client') as mock_keystone:
            n._set_ticket_id(34)
            mock_keystone.projects.update.assert_called_with(
                PROJECT.id, expiry_ticket_id='34')

    def test_get_ticket_id(self, mock_api):
        project = fakes.FakeProject(expiry_ticket_id=34)
        n = notifier.ExpiryNotifier(
            project=project, template_dir='allocations',
            group_id=1, subject='subject')
        self.assertEqual(34, n._get_ticket_id())

    def test_get_ticket_id_none(self, mock_api):
        project = fakes.FakeProject()
        n = notifier.ExpiryNotifier(
            project=project, template_dir='allocations',
            group_id=1, subject='subject')
        self.assertEqual(0, n._get_ticket_id())

    def test_get_ticket_id_invalid(self, mock_api):
        project = fakes.FakeProject(expiry_ticket_id='not-a-number')
        n = notifier.ExpiryNotifier(
            project=project, template_dir='allocations',
            group_id=1, subject='subject')
        self.assertEqual(0, n._get_ticket_id())
