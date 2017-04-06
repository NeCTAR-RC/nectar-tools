from unittest import mock

from nectar_tools import config
from nectar_tools import test

from nectar_tools.expiry import notifier

from nectar_tools.tests import fakes


CONF = config.CONFIG
PROJECT = fakes.FakeProject('active')


@mock.patch('nectar_tools.auth.get_session', new=mock.Mock())
class NotifierTests(test.TestCase):

    def test_render_template(self):
        n = notifier.Notifier(project=PROJECT, template_dir='allocations',
                              subject='fake')
        template = n.render_template('first-warning.tmpl')
        self.assertIn(PROJECT.name, template)

    def test_render_template_extra_context(self):
        n = notifier.Notifier(project=PROJECT, template_dir='allocations',
                              subject='fake')
        extra = {'expiry_date': 'some-fake-date'}
        template = n.render_template('first-warning.tmpl',
                                     extra_context=extra)
        self.assertIn(PROJECT.name, template)
        self.assertIn('some-fake-date', template)


@mock.patch('nectar_tools.auth.get_session', new=mock.Mock())
class EmailNotifierTests(test.TestCase):

    @mock.patch('email.mime.text.MIMEText', autospec=True)
    @mock.patch('smtplib.SMTP', autospec=True)
    def test_send_messagel(self, mock_smtp, mock_mime):
        n = notifier.EmailNotifier(project=PROJECT, template_dir='allocations',
                                   subject='My-Subject')

        n.send_message('first', 'owner@fake.org', {'foo': 'bar'},
                       ['manager1@fake.org', 'manager2@fake.org'])

        mock_smtp.return_value.sendmail.assert_called_with(
            mock_mime.return_value['From'],
            ['manager1@fake.org', 'manager2@fake.org', 'owner@fake.org'],
            mock_mime.return_value.as_string()
        )
        mime_calls = [
            mock.call('From', CONF.expiry.email_from),
            mock.call('To', 'owner@fake.org'),
            mock.call('Subject', 'My-Subject'),
            mock.call('cc', 'manager1@fake.org, manager2@fake.org'),
        ]
        mock_mime.return_value.__setitem__.assert_has_calls(mime_calls)
        mock_smtp.return_value.quit.assert_called_with()


@mock.patch('freshdesk.v2.api.API')
@mock.patch('nectar_tools.auth.get_session', new=mock.Mock())
class FreshDeskNotifierTests(test.TestCase):

    def _test_send_message(self, stage, template):
        n = notifier.FreshDeskNotifier(
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
                extra_context={'foo': 'bar'})
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
        n = notifier.FreshDeskNotifier(
            project=project, template_dir='allocations',
            group_id=1, subject='Ticket-Subject %s' % PROJECT.name)

        with test.nested(
            mock.patch.object(n, '_create_ticket'),
            mock.patch.object(n, '_update_ticket'),
            mock.patch.object(n, '_set_ticket_id'),
            mock.patch.object(n, '_add_note_to_ticket')
        ) as (mock_create, mock_update, mock_id, mock_note):
            n.send_message('second', 'owner@fake.org',
                           extra_recipients=['manager1@fake.org'])
            mock_create.assert_not_called()
            mock_note.assert_not_called()
            mock_id.assert_not_called()
            mock_update.assert_called_with(
                45, n.render_template('second-warning.tmpl'),
                cc_emails=['manager1@fake.org'])

    def test_finish(self, mock_api):
        project = fakes.FakeProject(expiry_ticket_id=22)
        n = notifier.FreshDeskNotifier(
            project=project, template_dir='allocations',
            group_id=1, subject='subject')
        with mock.patch.object(n, '_add_note_to_ticket') as mock_note:
            n.finish()
            mock_note.assert_not_called()
            mock_api.return_value.tickets.update_ticket.assert_called_with(
                22, status=4)

    def test_finish_message(self, mock_api):
        project = fakes.FakeProject(expiry_ticket_id=22)
        n = notifier.FreshDeskNotifier(
            project=project, template_dir='allocations',
            group_id=1, subject='subject')
        with mock.patch.object(n, '_add_note_to_ticket') as mock_note:
            n.finish(message='note-message')
            mock_note.assert_called_with(22, 'note-message')
            mock_api.return_value.tickets.update_ticket.assert_called_with(
                22, status=4)

    def test_set_ticket_id(self, mock_api):
        n = notifier.FreshDeskNotifier(
            project=PROJECT, template_dir='allocations',
            group_id=1, subject='Ticket-Subject %s' % PROJECT.name)

        with mock.patch.object(n, 'k_client') as mock_keystone:
            n._set_ticket_id(34)
            mock_keystone.projects.update.assert_called_with(
                PROJECT.id, expiry_ticket_id='34')

    def test_get_ticket_id(self, mock_api):
        project = fakes.FakeProject(expiry_ticket_id=34)
        n = notifier.FreshDeskNotifier(
            project=project, template_dir='allocations',
            group_id=1, subject='subject')
        self.assertEqual(34, n._get_ticket_id())

    def test_get_ticket_id_none(self, mock_api):
        project = fakes.FakeProject()
        n = notifier.FreshDeskNotifier(
            project=project, template_dir='allocations',
            group_id=1, subject='subject')
        self.assertEqual(0, n._get_ticket_id())

    def test_get_ticket_id_invalid(self, mock_api):
        project = fakes.FakeProject(expiry_ticket_id='not-a-number')
        n = notifier.FreshDeskNotifier(
            project=project, template_dir='allocations',
            group_id=1, subject='subject')
        self.assertEqual(0, n._get_ticket_id())

    def test_create_ticket(self, mock_api):
        n = notifier.FreshDeskNotifier(
            project=PROJECT, template_dir='allocations',
            group_id=1, subject='Ticket-Subject %s' % PROJECT.name)
        mock_api.return_value.tickets.create_outbound_email.return_value = \
            mock.Mock(id=3)
        ticket_id = n._create_ticket('owner@fake.org', ['manager1@fake.org'],
                            'description-text', extra_context={'foo': 'bar'})

        mock_api.return_value.tickets.create_outbound_email.assert_called_with(
            subject='Ticket-Subject %s' % PROJECT.name,
            description='description-text',
            email='owner@fake.org',
            email_config_id=int(CONF.freshdesk.email_config_id),
            group_id=1,
            cc_emails=['manager1@fake.org'],
            tags=['expiry']
        )
        self.assertEqual(3, ticket_id)

    def test_update_ticket(self, mock_api):
        n = notifier.FreshDeskNotifier(
            project=PROJECT, template_dir='allocations',
            group_id=1, subject='Ticket-Subject %s' % PROJECT.name)

        n._update_ticket(44, 'some text', cc_emails=['manager1@fake.org'])
        mock_api.return_value.comments.create_reply.assert_called_with(
            44, 'some text', cc_emails=['manager1@fake.org']
        )

    def test_add_note_to_ticket(self, mock_api):
        n = notifier.FreshDeskNotifier(
            project=PROJECT, template_dir='allocations',
            group_id=1, subject='Ticket-Subject %s' % PROJECT.name)

        n._add_note_to_ticket(1, 'note-update')
        mock_api.return_value.comments.create_note.assert_called_with(
            1, 'note-update')
