from unittest import mock

from nectar_tools import config
from nectar_tools import test

from nectar_tools.expiry import notifier

from nectar_tools.tests import fakes


CONF = config.CONFIG
PROJECT = fakes.FakeProject('active')


@mock.patch('nectar_tools.auth.get_session', new=mock.Mock())
class NotifierTests(test.TestCase):

    def setUp(self):
        super(NotifierTests, self).setUp()
        self.managers = [mock.Mock(id='manager1',
                                   enabled=True,
                                   email='manager1@example.org'),
                         mock.Mock(id='manager2',
                                   enabled=True,
                                   email='manager2@example.org')
                     ]
        self.members = [mock.Mock(id='member1',
                                  enabled=True,
                                  email='member1@example.org'),
                        mock.Mock(id='member2',
                                  enabled=False,
                                  email='member2@example.org'),
                        mock.Mock(id='manager1',
                                  enabled=True,
                                  email='manager1@example.org')
                    ]

    def test_get_project_managers(self):
        n = notifier.Notifier(project=PROJECT, template_dir='allocations')
        self.assertIsNone(n.managers)
        with mock.patch.object(n, '_get_users_by_role',
                          return_value=self.managers):
            managers = n._get_project_managers()
            self.assertEqual(self.managers, n.managers)
            self.assertEqual(self.managers, managers)

    def test_get_project_members(self):
        n = notifier.Notifier(project=PROJECT, template_dir='allocations')
        self.assertIsNone(n.members)
        with mock.patch.object(n, '_get_users_by_role',
                          return_value=self.members):
            members = n._get_project_members()
            self.assertEqual(self.members, n.members)
            self.assertEqual(self.members, members)

    def test_get_users_by_role(self):
        n = notifier.Notifier(project=PROJECT, template_dir='allocations')
        role = 'fakerole'
        role_assignments = [mock.Mock(), mock.Mock()]
        role_assignments[0].user = {}
        role_assignments[1].user = {}
        role_assignments[0].user['id'] = 'fakeuser1'
        role_assignments[1].user['id'] = 'fakeuser2'

        def user_side_effect(value):
            mock_user = mock.Mock()
            mock_user.id = value
            return mock_user

        with mock.patch.object(n, 'k_client') as mock_keystone:
            mock_keystone.role_assignments.list.return_value = role_assignments
            mock_keystone.users.get.side_effect = user_side_effect
            users = n._get_users_by_role('fakerole')
            mock_keystone.role_assignments.list.assert_called_with(
                project=PROJECT, role=role)
            mock_keystone.users.get.assert_has_calls([mock.call('fakeuser1'),
                                                     mock.call('fakeuser2')])
            self.assertEqual(['fakeuser1', 'fakeuser2'], [x.id for x in users])

    def test_get_recipients(self):
        n = notifier.Notifier(project=PROJECT, template_dir='allocations')
        with test.nested(
            mock.patch.object(n, '_get_project_managers',
                         return_value=self.managers),
            mock.patch.object(n, '_get_project_members',
                         return_value=self.members)):
            recipients, ccs = n.get_recipients()
            self.assertEqual(['manager1@example.org', 'manager2@example.org'],
                             recipients)
            self.assertEqual(['member1@example.org'], ccs)

    def test_get_recipients_no_managers(self):
        n = notifier.Notifier(project=PROJECT, template_dir='allocations')
        with test.nested(
            mock.patch.object(n, '_get_project_managers',
                         return_value=[]),
            mock.patch.object(n, '_get_project_members',
                         return_value=self.members)):
            recipients, ccs = n.get_recipients()
            self.assertEqual(['member1@example.org', 'manager1@example.org'],
                             recipients)
            self.assertEqual([], ccs)

    @mock.patch('email.mime.text.MIMEText', autospec=True)
    @mock.patch('smtplib.SMTP', autospec=True)
    def test_send_email(self, mock_smtp, mock_mime):
        n = notifier.Notifier(project=PROJECT, template_dir='allocations')

        with mock.patch.object(n, 'get_recipients',
                               return_value=(['bob@foo.com'],
                                             ['john@bar.com',
                                              'greg@boo.com'])):
            n.send_email('my subject', 'my text')

            mock_smtp.return_value.sendmail.assert_called_with(
                mock_mime.return_value['From'],
                ['bob@foo.com', 'john@bar.com', 'greg@boo.com'],
                mock_mime.return_value.as_string()
            )
            mime_calls = [
                mock.call('From', CONF.expiry.email_from),
                mock.call('To', 'bob@foo.com'),
                mock.call('Subject', 'my subject'),
                mock.call('cc', 'john@bar.com, greg@boo.com'),
            ]
            mock_mime.return_value.__setitem__.assert_has_calls(mime_calls)
            mock_smtp.return_value.quit.assert_called_with()

    @mock.patch('email.mime.text.MIMEText', autospec=True)
    @mock.patch('smtplib.SMTP', autospec=True)
    def test_send_email_users(self, mock_smtp, mock_mime):
        n = notifier.Notifier(project=PROJECT, template_dir='allocations')
        user1 = mock.Mock(enabled=True, email='user1@foo.com')
        user2 = mock.Mock(enabled=False, email='user2@foo.com')
        users = [user1, user2]
        n.send_email('my subject', 'my text', users)

        mock_smtp.return_value.sendmail.assert_called_with(
            mock_mime.return_value['From'],
            ['user1@foo.com'],
            mock_mime.return_value.as_string()
        )
        mime_calls = [
            mock.call('From', CONF.expiry.email_from),
            mock.call('To', 'user1@foo.com'),
            mock.call('Subject', 'my subject'),
        ]
        mock_mime.return_value.__setitem__.assert_has_calls(mime_calls)
        mock_smtp.return_value.quit.assert_called_with()

    def test_render_template(self):
        n = notifier.Notifier(project=PROJECT, template_dir='allocations')
        template = n.render_template('first-warning.tmpl')
        self.assertIn(PROJECT.name, template)

    def test_render_template_extra_context(self):
        n = notifier.Notifier(project=PROJECT, template_dir='allocations')
        extra = {'expiry_date': 'some-fake-date'}
        template = n.render_template('first-warning.tmpl',
                                     extra_context=extra)
        self.assertIn(PROJECT.name, template)
        self.assertIn('some-fake-date', template)


@mock.patch('freshdesk.v2.api.API')
@mock.patch('nectar_tools.auth.get_session', new=mock.Mock())
class FreshDeskNotifierTests(test.TestCase):

    def _test_send_message(self, status, template):
        n = notifier.FreshDeskNotifier(
            project=PROJECT, template_dir='allocations',
            group_id=1, subject='Ticket-Subject %s' % PROJECT.name)

        with test.nested(
            mock.patch.object(n, '_create_ticket'),
            mock.patch.object(n, '_update_ticket'),
            mock.patch.object(n, '_set_ticket_meta')
        ) as (mock_create, mock_update, mock_meta):
            mock_create.return_value = 32
            n.send_message(status)
            mock_create.assert_called_with({})
            mock_update.assert_called_with(
                32, n.render_template(template))
            mock_meta.assert_called_with(32)

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
            mock.patch.object(n, '_set_ticket_meta')
        ) as (mock_create, mock_update, mock_meta):
            n.send_message('second')
            mock_create.assert_not_called()
            mock_meta.assert_not_called()
            mock_update.assert_called_with(
                45, n.render_template('second-warning.tmpl'))

    def test_send_message_extra(self, mock_api):
        n = notifier.FreshDeskNotifier(
            project=PROJECT, template_dir='allocations',
            group_id=1, subject='Ticket-Subject %s' % PROJECT.name)

        with test.nested(
            mock.patch.object(n, '_create_ticket'),
            mock.patch.object(n, '_update_ticket'),
            mock.patch.object(n, '_set_ticket_meta')
        ) as (mock_create, mock_update, mock_meta):
            mock_create.return_value = 47
            extra = {'allocation': 'fakeallocation'}
            n.send_message('first', extra_context=extra)
            mock_create.assert_called_with(extra)
            mock_update.assert_called_with(
                47, n.render_template('first-warning.tmpl'))

    def test_set_ticket_meta(self, mock_api):
        n = notifier.FreshDeskNotifier(
            project=PROJECT, template_dir='allocations',
            group_id=1, subject='Ticket-Subject %s' % PROJECT.name)

        with mock.patch.object(n, 'k_client') as mock_keystone:
            n._set_ticket_meta(34)
            mock_keystone.projects.update.assert_called_with(
                PROJECT.id, expiry_ticket_id='34')

    def test_create_ticket(self, mock_api):
        n = notifier.FreshDeskNotifier(
            project=PROJECT, template_dir='allocations',
            group_id=1, subject='Ticket-Subject %s' % PROJECT.name)

        with test.nested(
            mock.patch.object(n, 'get_recipients',
                              return_value=(['s@b.com'], ['b@g.com'])),
            mock.patch.object(n, '_get_project_managers',
                              return_value=[mock.Mock()]),
            mock.patch.object(n, '_get_project_members'),
            mock.patch.object(n, 'render_template'),
        ) as (mock_recipients, mock_managers, mock_members, mock_render):
            n._create_ticket()
            extra = {'members': mock_members.return_value,
                     'managers': mock_managers.return_value}
            mock_render.assert_called_with(
                'ticket-description.tmpl', extra_context=extra)
            mock_api.return_value.tickets.create_ticket.assert_called_with(
                description=mock_render.return_value,
                email=CONF.freshdesk.agent_email,
                subject='Ticket-Subject %s' % PROJECT.name,
                group_id=1,
                tags=['expiry']
            )

    def test_create_ticket_extra_context(self, mock_api):
        n = notifier.FreshDeskNotifier(
            project=PROJECT, template_dir='allocations',
            group_id=1, subject='Ticket-Subject %s' % PROJECT.name)

        with test.nested(
            mock.patch.object(n, 'get_recipients',
                              return_value=(['s@b.com'], ['b@g.com'])),
            mock.patch.object(n, '_get_project_managers',
                              return_value=[mock.Mock()]),
            mock.patch.object(n, '_get_project_members'),
            mock.patch.object(n, 'render_template'),
        ) as (mock_recipients, mock_managers, mock_members, mock_render):
            extra = {'allocation': 'fakeallocation'}
            n._create_ticket(extra_context=extra)
            extra.update({'members': mock_members.return_value,
                          'managers': mock_managers.return_value})
            mock_render.assert_called_with(
                'ticket-description.tmpl', extra_context=extra)
            mock_api.return_value.tickets.create_ticket.assert_called_with(
                description=n.render_template(
                    'ticket-description.tmpl'),
                email=CONF.freshdesk.agent_email,
                subject='Ticket-Subject %s' % PROJECT.name,
                group_id=1,
                tags=['expiry']
            )

    def test_update_ticket(self, mock_api):
        n = notifier.FreshDeskNotifier(
            project=PROJECT, template_dir='allocations',
            group_id=1, subject='Ticket-Subject %s' % PROJECT.name)

        with mock.patch.object(n, 'get_recipients',
                               return_value=(['s@b.com'], ['b@g.com'])):
            n._update_ticket(44, 'some text')
            mock_api.return_value.comments.create_reply.assert_called_with(
                44, 'some text', cc_emails=['s@b.com', 'b@g.com']
            )
