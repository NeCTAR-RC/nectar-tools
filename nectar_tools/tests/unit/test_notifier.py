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
        n = notifier.Notifier(
            resource_type='project',
            resource=PROJECT,
            template_dir='expiry/tests',
            subject='fake',
        )
        template = n.render_template('first-warning.tmpl')
        self.assertIn(PROJECT.name, template)

    def test_render_template_extra_context(self):
        n = notifier.Notifier(
            resource_type='project',
            resource=PROJECT,
            template_dir='expiry/tests',
            subject='fake',
        )
        extra = {'expiry_date': 'some-fake-date'}
        template = n.render_template('first-warning.tmpl', extra_context=extra)
        self.assertIn(PROJECT.name, template)
        self.assertIn('some-fake-date', template)


@mock.patch('nectar_tools.auth.get_session', new=mock.Mock())
class TaynacNotifierTests(test.TestCase):
    def test_send_message(self):
        n = notifier.TaynacNotifier(
            session=None,
            resource_type='project',
            resource=PROJECT,
            template_dir='expiry/tests',
            subject='My-Subject',
        )
        with mock.patch.object(n, 't_client') as mock_taynac:
            n.send_message(
                'first-warning',
                'owner@fake.org',
                {'foo': 'bar'},
                ['manager1@fake.org', 'manager2@fake.org'],
                tags=['red rover', 'all over'],
            )
            mock_taynac.messages.send.assert_called_once_with(
                subject='My-Subject',
                body=mock.ANY,
                recipient='owner@fake.org',
                cc=['manager1@fake.org', 'manager2@fake.org'],
                tags=['red rover', 'all over'],
            )


@mock.patch('freshdesk.v2.api.API')
class FreshDeskNotifierTests(test.TestCase):
    def test_create_ticket(self, mock_api):
        n = notifier.FreshDeskNotifier(
            resource_type='project',
            resource=PROJECT,
            template_dir='expiry/tests',
            group_id=1,
            subject=f'Ticket-Subject {PROJECT.name}',
        )
        mock_api.return_value.tickets.create_outbound_email.return_value = (
            mock.Mock(id=3)
        )
        ticket_id = n._create_ticket(
            'owner@fake.org',
            ['manager1@fake.org'],
            'description-text',
            extra_context={'foo': 'bar'},
            tags=['foo', 'bar'],
        )

        mock_api.return_value.tickets.create_outbound_email.assert_called_with(
            subject=f'Ticket-Subject {PROJECT.name}',
            description='description-text',
            email='owner@fake.org',
            email_config_id=int(CONF.freshdesk.email_config_id),
            group_id=1,
            cc_emails=['manager1@fake.org'],
            tags=['foo', 'bar'],
        )
        self.assertEqual(3, ticket_id)

    def test_update_ticket_requester(self, mock_api):
        n = notifier.FreshDeskNotifier(
            resource_type='project',
            resource=PROJECT,
            template_dir='expiry/allocations',
            group_id=1,
            subject=f'Ticket-Subject {PROJECT.name}',
        )

        n._update_ticket_requester(43, 'owner@fake.org')
        mock_api.return_value.tickets.update_ticket.assert_called_with(
            43, email='owner@fake.org'
        )

    def test_update_ticket(self, mock_api):
        n = notifier.FreshDeskNotifier(
            resource_type='project',
            resource=PROJECT,
            template_dir='expiry/tests',
            group_id=1,
            subject=f'Ticket-Subject {PROJECT.name}',
        )

        n._update_ticket(44, 'some text', cc_emails=['manager1@fake.org'])
        mock_api.return_value.comments.create_reply.assert_called_with(
            44, body='some text', cc_emails=['manager1@fake.org']
        )

    def test_add_note_to_ticket(self, mock_api):
        n = notifier.FreshDeskNotifier(
            resource_type='project',
            resource=PROJECT,
            template_dir='expiry/allocations',
            group_id=1,
            subject=f'Ticket-Subject {PROJECT.name}',
        )

        n._add_note_to_ticket(1, 'note-update')
        mock_api.return_value.comments.create_note.assert_called_with(
            1, 'note-update'
        )
