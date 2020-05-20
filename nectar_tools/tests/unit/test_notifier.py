from unittest import mock

from nectar_tools import config
from nectar_tools import test

from nectar_tools import notifier

from nectar_tools.tests import fakes


CONF = config.CONFIG
PROJECT = fakes.FakeProject('active')


@mock.patch('nectar_tools.auth.get_session', new=mock.Mock())
class NotifierTests(test.TestCase):

    def test_render_template(self):
        n = notifier.Notifier(resource_type='project', resource=PROJECT,
            template_dir='allocations', subject='fake')
        template = n.render_template('first-warning.tmpl')
        self.assertIn(PROJECT.name, template)

    def test_render_template_extra_context(self):
        n = notifier.Notifier(resource_type='project', resource=PROJECT,
                              template_dir='allocations', subject='fake')
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
        n = notifier.EmailNotifier(resource_type='project', resource=PROJECT,
            template_dir='allocations', subject='My-Subject')

        n.send_message('first', 'owner@fake.org', {'foo': 'bar'},
                       ['manager1@fake.org', 'manager2@fake.org'])

        mock_smtp.return_value.sendmail.assert_called_with(
            mock_mime.return_value['From'],
            ['manager1@fake.org', 'manager2@fake.org', 'owner@fake.org'],
            mock_mime.return_value.as_string()
        )
        mime_calls = [
            mock.call('From', CONF.notifier.email_from),
            mock.call('To', 'owner@fake.org'),
            mock.call('Subject', 'My-Subject'),
            mock.call('cc', 'manager1@fake.org, manager2@fake.org'),
        ]
        mock_mime.return_value.__setitem__.assert_has_calls(mime_calls)
        mock_smtp.return_value.quit.assert_called_with()


@mock.patch('freshdesk.v2.api.API')
class FreshDeskNotifierTests(test.TestCase):

    def test_create_ticket(self, mock_api):
        n = notifier.FreshDeskNotifier(
            resource_type='project', resource=PROJECT,
            template_dir='allocations', group_id=1,
            subject='Ticket-Subject %s' % PROJECT.name)
        mock_api.return_value.tickets.create_outbound_email.return_value = \
            mock.Mock(id=3)
        ticket_id = n._create_ticket('owner@fake.org',
                                     ['manager1@fake.org'],
                                     'description-text',
                                     extra_context={'foo': 'bar'},
                                     tags=['foo', 'bar'])

        mock_api.return_value.tickets.create_outbound_email.assert_called_with(
            subject='Ticket-Subject %s' % PROJECT.name,
            description='description-text',
            email='owner@fake.org',
            email_config_id=int(CONF.freshdesk.email_config_id),
            group_id=1,
            cc_emails=['manager1@fake.org'],
            tags=['foo', 'bar']
        )
        self.assertEqual(3, ticket_id)

    def test_update_ticket_requester(self, mock_api):
        n = notifier.FreshDeskNotifier(
            resource_type='project', resource=PROJECT,
            template_dir='allocations', group_id=1,
            subject='Ticket-Subject %s' % PROJECT.name)

        n._update_ticket_requester(43, 'owner@fake.org')
        mock_api.return_value.tickets.update_ticket.assert_called_with(
            43, email='owner@fake.org')

    def test_update_ticket(self, mock_api):
        n = notifier.FreshDeskNotifier(
            resource_type='project', resource=PROJECT,
            template_dir='allocations', group_id=1,
            subject='Ticket-Subject %s' % PROJECT.name)

        n._update_ticket(44, 'some text', cc_emails=['manager1@fake.org'])
        mock_api.return_value.comments.create_reply.assert_called_with(
            44, body='some text', cc_emails=['manager1@fake.org']
        )

    def test_add_note_to_ticket(self, mock_api):
        n = notifier.FreshDeskNotifier(
            resource_type='project', resource=PROJECT,
            template_dir='allocations', group_id=1,
            subject='Ticket-Subject %s' % PROJECT.name)

        n._add_note_to_ticket(1, 'note-update')
        mock_api.return_value.comments.create_note.assert_called_with(
            1, 'note-update')
