import datetime
from dateutil import relativedelta
from freezegun import freeze_time
from unittest import mock

from nectar_tools import config
from nectar_tools import exceptions
from nectar_tools.expiry import expirer
from nectar_tools.expiry import expiry_states
from nectar_tools import test
from nectar_tools.tests import fakes
from nectar_tools.tests.functional import fake_clients


CONF = config.CONFIG
FAKE_ALLOCATION_CLIENT = mock.MagicMock()
FAKE_NOVA = mock.MagicMock()
FAKE_NEUTRON = mock.MagicMock()
FAKE_SWIFT = mock.MagicMock()
FAKE_GLANCE = mock.MagicMock()
TODAY = "2017-07-01"
TODAY_DATE = datetime.datetime(2017, 7, 1)
FUTURE = "2017-07-02"
PAST = "2017-06-30"


def get_nova(session):
    return FAKE_NOVA


def get_neutron(session):
    return FAKE_NEUTRON


def get_swift(session, project_id):
    return FAKE_SWIFT


def get_glance(session):
    return FAKE_GLANCE


def get_allocation_client(session):
    return FAKE_ALLOCATION_CLIENT


@freeze_time(TODAY)
@mock.patch('nectar_tools.auth.get_session', new=fake_clients.FAKE_GET_SESSION)
@mock.patch('freshdesk.v2.api.API', new=fake_clients.FAKE_FD_API_CLASS)
@mock.patch('nectar_tools.auth.get_swift_client', new=get_swift)
@mock.patch('nectar_tools.auth.get_glance_client', new=get_glance)
@mock.patch('nectar_tools.auth.get_neutron_client', new=get_neutron)
@mock.patch('nectar_tools.auth.get_keystone_client',
            new=fake_clients.get_keystone)
@mock.patch('nectar_tools.auth.get_nova_client', new=get_nova)
@mock.patch('nectar_tools.auth.get_manuka_client', new=fake_clients.get_manuka)
@mock.patch('nectar_tools.auth.get_allocation_client',
            new=get_allocation_client)
class PTExpiryTests(test.TestCase):

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        # reset all mocks explicitly since we're defining them
        # outside of the test class (prevents leakage)
        fake_clients.FAKE_FD_API.reset_mock()
        fake_clients.FAKE_KEYSTONE.reset_mock()
        FAKE_NOVA.reset_mock()
        FAKE_NEUTRON.reset_mock()
        FAKE_SWIFT.reset_mock()
        FAKE_GLANCE.reset_mock()
        # Set up a fake PT with an owner
        project = fakes.FakeProjectWithOwner(id='q12w', name='pt-123',
                                             description='abc',
                                             domain_id='my-domain-id')
        self.project = project

    def _test_process(self, invalid=False, usage=0,
                      registered_at=datetime.datetime(2017, 1, 1),
                      pending_allocations=[],
                      keystone_calls=[], fd_calls=[],
                      nova_calls=[], neutron_calls=[],
                      swift_calls=[], glance_calls=[]):
        """Runs the actual expiry process

        :param invalid: If true expect process to raise InvalidProject
        :param usage: CPU usage reported by nova
        :param registered_at: Registered at date of manuka user
        :param keystone_calls: Expected calls for keystone client
        :param fd_calls: Expected calls for freshdesk client
        :param nova_calls: Expected calls for nova client
        :param neutron_calls: Expected calls for neutron client
        :param swift_calls: Expected calls for swift client
        :param glance_calls: Expected calls for glance client
        """

        keystone_client = fake_clients.FAKE_KEYSTONE
        manuka_client = fake_clients.FAKE_MANUKA
        nova_client = FAKE_NOVA
        neutron_client = FAKE_NEUTRON
        swift_client = FAKE_SWIFT
        glance_client = FAKE_GLANCE
        fd_client = fake_clients.FAKE_FD_API
        allocation_client = FAKE_ALLOCATION_CLIENT

        fake_account = mock.Mock(registered_at=registered_at)
        manuka_client.users.get.return_value = fake_account

        allocation_client.allocations.list.return_value = pending_allocations

        usage = mock.Mock(total_vcpus_usage=usage)
        nova_client.usage.get.return_value = usage

        manager = expirer.PTExpirer(self.project)
        if invalid:
            self.assertRaises(exceptions.InvalidProject, manager.process)
        else:
            manager.process()

        self.assertEqual(fd_calls, fd_client.method_calls)

        # Assert that email content isn't None
        # This catches templates not existing etc.
        for call in fd_client.method_calls:
            name, args, kwargs = call
            if name == 'tickets.create_outbound_email':
                self.assertIsNotNone(kwargs.get('description'))
            elif name == 'comments.create_reply':
                self.assertIsNotNone(kwargs.get('body'))
        self.assertEqual(keystone_calls, keystone_client.method_calls)
        self.assertEqual(nova_calls, nova_client.method_calls)
        self.assertEqual(neutron_calls, neutron_client.method_calls)
        self.assertEqual(swift_calls, swift_client.method_calls)
        self.assertEqual(glance_calls, glance_client.method_calls)

    def get_fd_calls(self):
        """Helper method to get expected calls for freshdesk"""
        if not getattr(self.project, 'expiry_ticket_id', 0):
            subject = "Nectar Project Trial Expiry - %s" % self.project.name
            calls = [
                mock.call.tickets.create_outbound_email(
                    cc_emails=[],
                    description=mock.ANY,
                    email=self.project.owner.email,
                    email_config_id=int(CONF.freshdesk.email_config_id),
                    group_id=int(CONF.freshdesk.pt_group),
                    subject=subject,
                    tags=['expiry']),
                mock.call.comments.create_note(mock.ANY, mock.ANY)
            ]
        else:
            calls = [
                mock.call.tickets.update_ticket(
                    int(self.project.expiry_ticket_id),
                    email=self.project.owner.email),
                mock.call.comments.create_reply(
                    int(self.project.expiry_ticket_id),
                    body=mock.ANY, cc_emails=[])
            ]
        return calls

    def get_keystone_calls(self, state, next_step_days=14):
        """Helper method to get expected keystone calls

        :param state: Expected state to update project to
        :param next_step_days: Expected next_step value in days in the future
        """

        next_step = TODAY_DATE + relativedelta.relativedelta(
            days=next_step_days)
        next_step = next_step.strftime('%Y-%m-%d')
        if state == expiry_states.ARCHIVED:
            keystone_calls = [
                mock.call.projects.update(
                    self.project.id,
                    expiry_status=state,
                    expiry_updated_at=TODAY),
            ]
        elif state == expiry_states.DELETED:
            keystone_calls = [
                mock.call.projects.update(
                    self.project.id,
                    expiry_deleted_at=TODAY,
                    expiry_next_step='',
                    expiry_status=state,
                    expiry_updated_at=TODAY),
            ]
        else:
            keystone_calls = [
                mock.call.projects.update(
                    self.project.id,
                    expiry_next_step=next_step,
                    expiry_status=state,
                    expiry_updated_at=TODAY),
            ]

        if not getattr(self.project, 'expiry_ticket_id', None):
            keystone_calls.append(
                mock.call.projects.update(
                    self.project.id,
                    expiry_ticket_id=mock.ANY))

        return keystone_calls

    def test_active_ok(self):
        """New PT with usage under limit

        Environment: New project with usage under 80%

        Expected: Nothing
        """

        nova_calls = [mock.call.usage.get(
            self.project.id,
            datetime.datetime(2011, 1, 1),
            TODAY_DATE + relativedelta.relativedelta(days=1))
        ]

        self._test_process(nova_calls=nova_calls)

    def test_active_usage_over_limit(self):
        """Active PT with usage over limit

        Enviroment: Project with usage above 80%

        Expected: FD outbound email sent, status -> WARNING
        """

        next_step = TODAY_DATE + relativedelta.relativedelta(days=30)
        next_step = next_step.strftime('%Y-%m-%d')

        keystone_calls = self.get_keystone_calls(expiry_states.WARNING, 30)

        nova_calls = [mock.call.usage.get(
            self.project.id,
            datetime.datetime(2011, 1, 1),
            TODAY_DATE + relativedelta.relativedelta(days=1))
        ]

        fd_calls = self.get_fd_calls()

        self._test_process(usage=13507,
                           keystone_calls=keystone_calls,
                           fd_calls=fd_calls,
                           nova_calls=nova_calls)

    def test_active_old(self):
        """Active PT that is older than 1 year

        Enviroment: Project older that 1 year

        Expected: FD outbound email sent, status -> WARNING
        """

        registered_at = TODAY_DATE - relativedelta.relativedelta(months=13)

        keystone_calls = self.get_keystone_calls(expiry_states.WARNING, 30)

        nova_calls = [mock.call.usage.get(
            self.project.id,
            datetime.datetime(2011, 1, 1),
            TODAY_DATE + relativedelta.relativedelta(days=1))
        ]

        fd_calls = self.get_fd_calls()

        self._test_process(registered_at=registered_at,
                           keystone_calls=keystone_calls,
                           fd_calls=fd_calls,
                           nova_calls=nova_calls)

    def test_warning_ok(self):
        """Project in warning state not ready for next step

        Expected: Nothing
        """

        self.project.expiry_status = expiry_states.WARNING
        self.project.expiry_next_step = FUTURE

        self._test_process()

    def test_warning_ready(self):
        """Project in warning state ready for next step

        Expected: quotas set to zero, freshdesk ticket created
        """

        self.project.expiry_status = expiry_states.WARNING
        self.project.expiry_next_step = PAST

        keystone_calls = self.get_keystone_calls(expiry_states.RESTRICTED)

        nova_calls = [
            mock.call.quotas.update(cores=0, instances=0, ram=0,
                                    tenant_id=self.project.id, force=True)
        ]
        neutron_quota = {'quota': {'port': 0,
                                   'security_group': 0,
                                   'security_group_rule': 0,
                                   'floatingip': 0,
                                   'router': 0,
                                   'network': 0,
                                   'subnet': 0}}
        neutron_calls = [
            mock.call.update_quota(self.project.id, neutron_quota)
        ]

        swift_calls = [
            mock.call.post_account(headers={'x-account-meta-quota-bytes': 0})
        ]

        fd_calls = self.get_fd_calls()

        self._test_process(keystone_calls=keystone_calls,
                           fd_calls=fd_calls,
                           nova_calls=nova_calls,
                           neutron_calls=neutron_calls,
                           swift_calls=swift_calls)

    def test_warning_pending_allocation(self):
        """Project in warning state not ready for next step

        Expected: Nothing
        """

        self.project.expiry_status = expiry_states.WARNING
        self.project.expiry_next_step = PAST

        self._test_process(pending_allocations=[mock.Mock()], invalid=True)

    def test_restricted_ok(self):
        """Project in restricted state not ready

        Expected: Nothing

        """
        self.project.expiry_status = expiry_states.RESTRICTED
        self.project.expiry_next_step = FUTURE

        self._test_process()

    def test_restricted_ready(self):
        """Project in restricted state ready

        Environment: One running instance

        Expected: Quotas set to zero, instance stopped, freshdesk notification,
                  status -> STOPPED

        """
        self.project.expiry_status = expiry_states.RESTRICTED
        self.project.expiry_next_step = PAST
        self.project.expiry_ticket_id = '2'

        nova_client = FAKE_NOVA
        fake_instance = fakes.FakeInstance()

        def fake_list(search_opts):
            if 'marker' in search_opts:
                return []
            else:
                return [fake_instance]

        nova_client.servers.list.side_effect = fake_list

        keystone_calls = self.get_keystone_calls(expiry_states.STOPPED)

        nova_calls = [
            mock.call.servers.list(search_opts={'all_tenants': True,
                                                'tenant_id': self.project.id,
                                                'marker': 'fake'}),
            mock.call.servers.list(search_opts={'all_tenants': True,
                                                'tenant_id': self.project.id,
                                                'marker': 'fake'}),
            mock.call.servers.lock(fake_instance.id),
            mock.call.servers.set_meta(fake_instance.id,
                                       {'expiry_locked': 'True'}),
            mock.call.servers.stop(fake_instance.id),
        ]

        fd_calls = self.get_fd_calls()

        self._test_process(keystone_calls=keystone_calls,
                           nova_calls=nova_calls,
                           fd_calls=fd_calls)

    def test_stopped_ok(self):
        """Project in stopped state not ready

        Expected: no change
        """
        self.project.expiry_status = expiry_states.STOPPED
        self.project.expiry_next_step = FUTURE
        self.project.expiry_ticket_id = '2'

        self._test_process()

    def test_stopped_ready(self):
        """Project in stopped state ready

        One instance in stopped state

        Expected: Snapshot image, state -> ARCHIVING
        """
        self.project.expiry_status = expiry_states.STOPPED
        self.project.expiry_next_step = PAST
        self.project.expiry_ticket_id = '2'

        nova_client = FAKE_NOVA
        glance_client = FAKE_GLANCE
        fake_instance = fakes.FakeInstance(status="STOPPED",
                                           vm_state='stopped')

        def fake_list(search_opts):
            if 'marker' in search_opts:
                return []
            else:
                return [fake_instance]

        nova_client.servers.list.side_effect = fake_list
        glance_client.images.list.return_value = []

        keystone_calls = self.get_keystone_calls(expiry_states.ARCHIVING, 90)
        nova_calls = [
            mock.call.servers.list(search_opts={'all_tenants': True,
                                                'tenant_id': self.project.id,
                                                'marker': 'fake'}),
            mock.call.servers.list(search_opts={'all_tenants': True,
                                                'tenant_id': self.project.id,
                                                'marker': 'fake'}),
            mock.call.servers.set_meta(fake_instance.id,
                                       {'archive_attempts': '1'}),
            mock.call.servers.create_image(
                fake_instance.id, 'fake_archive',
                metadata={'nectar_archive': 'True'}),
        ]

        glance_calls = [
            mock.call.images.list(filters={'owner_id': self.project.id,
                                           'nectar_archive': 'True'}),
        ]

        self._test_process(keystone_calls=keystone_calls,
                           nova_calls=nova_calls,
                           glance_calls=glance_calls)

    def test_archiving_ok(self):
        """Project in archiving state not ready

        Environment: One instance and one successful snapshot

        Expected: status -> ARCHIVED
        """
        self.project.expiry_status = expiry_states.ARCHIVING
        self.project.expiry_next_step = FUTURE
        self.project.expiry_ticket_id = '2'

        nova_client = FAKE_NOVA
        glance_client = FAKE_GLANCE
        fake_instance = fakes.FakeInstance(status="STOPPED",
                                           vm_state='stopped')

        def fake_list(search_opts):
            if 'marker' in search_opts:
                return []
            else:
                return [fake_instance]

        nova_client.servers.list.side_effect = fake_list
        glance_client.images.list.return_value = [fakes.FakeImage()]

        keystone_calls = self.get_keystone_calls(expiry_states.ARCHIVED)
        nova_calls = [
            mock.call.servers.list(search_opts={'all_tenants': True,
                                                'tenant_id': self.project.id,
                                                'marker': 'fake'}),
            mock.call.servers.list(search_opts={'all_tenants': True,
                                                'tenant_id': self.project.id,
                                                'marker': 'fake'}),
        ]
        glance_calls = [
            mock.call.images.list(filters={'owner_id': self.project.id,
                                           'nectar_archive': 'True'}),
        ]

        self._test_process(keystone_calls=keystone_calls,
                           nova_calls=nova_calls,
                           glance_calls=glance_calls)

    def test_archiving_ready(self):
        """Project in archiving state and hasn't completed in time frame

        Environment: One instance

        Expected: status -> ARCHIVED

        """
        self.project.expiry_status = expiry_states.ARCHIVING
        self.project.expiry_next_step = PAST
        self.project.expiry_ticket_id = '2'

        keystone_calls = self.get_keystone_calls(expiry_states.ARCHIVED)

        self._test_process(keystone_calls=keystone_calls)

    def test_archived_ok(self):
        """Project in archived state not ready

        Environment:  One instance and one successful snapshot

        Expected: Instance deleted
        """

        self.project.expiry_status = expiry_states.ARCHIVED
        self.project.expiry_next_step = FUTURE
        self.project.expiry_ticket_id = '2'

        nova_client = FAKE_NOVA
        glance_client = FAKE_GLANCE
        fake_instance = fakes.FakeInstance(status="STOPPED",
                                           vm_state='stopped')

        def fake_list(search_opts):
            if 'marker' in search_opts:
                return []
            else:
                return [fake_instance]

        nova_client.servers.list.side_effect = fake_list
        glance_client.images.list.return_value = [fakes.FakeImage()]

        nova_calls = [
            mock.call.servers.list(search_opts={'all_tenants': True,
                                                'tenant_id': self.project.id,
                                                'marker': 'fake'}),
            mock.call.servers.list(search_opts={'all_tenants': True,
                                                'tenant_id': self.project.id,
                                                'marker': 'fake'}),
            mock.call.servers.delete(fake_instance.id),
        ]
        glance_calls = [
            mock.call.images.list(filters={'owner_id': self.project.id,
                                           'nectar_archive': 'True'}),
        ]
        self._test_process(nova_calls=nova_calls, glance_calls=glance_calls)

    def test_archived_ready(self):
        """Project in archived state ready

        Environment: 1 instance archive,
                     1 private swift container with 1 object
                     1 port
                     2 security groups
                     2 security group rules

        Expected: Delete instance archive, status -> DELETED

        """
        self.project.expiry_status = expiry_states.ARCHIVED
        self.project.expiry_next_step = PAST
        self.project.expiry_ticket_id = '2'

        nova_client = FAKE_NOVA
        glance_client = FAKE_GLANCE
        swift_client = FAKE_SWIFT
        neutron_client = FAKE_NEUTRON

        def fake_list(search_opts):
            if 'marker' in search_opts:
                return []
            else:
                return []

        nova_client.servers.list.side_effect = fake_list
        image = fakes.FakeImage()
        glance_client.images.list.return_value = [image]
        c1 = {'name': 'c1'}
        o1 = {'name': 'o1'}

        swift_client.get_account.return_value = ('fake-account', [c1])
        swift_client.get_container.return_value = ('fake-container',
                                                   [o1])
        port_response = {'ports': [
            {'id': 'fakeport1'}]}
        neutron_client.list_ports.return_value = port_response
        secgroup_response = {'security_groups': [
            {'id': 'fake', 'name': 'fake'},
            {'id': 'fake2', 'name': 'default'}]}
        secgroup_rules_response = {'security_group_rules': [
            {'id': 'rule1', 'security_group_id': 'secgrp1'},
            {'id': 'rule2', 'security_group_id': 'secgrp2'}]}
        neutron_client.list_security_groups.return_value = secgroup_response
        neutron_client.list_security_group_rules.return_value = \
                secgroup_rules_response

        nova_calls = [
            mock.call.servers.list(search_opts={'all_tenants': True,
                                                'tenant_id': self.project.id}),
        ]
        glance_calls = [
            mock.call.images.list(filters={'owner_id': self.project.id,
                                           'nectar_archive': 'True'}),
            mock.call.images.delete(image.id),
        ]

        neutron_calls = [
            mock.call.list_ports(tenant_id=self.project.id),
            mock.call.delete_port('fakeport1'),
            mock.call.list_security_groups(tenant_id=self.project.id),
            mock.call.delete_security_group('fake'),
            mock.call.list_security_group_rules(tenant_id=self.project.id),
            mock.call.delete_security_group_rule('rule1'),
            mock.call.delete_security_group_rule('rule2'),
        ]

        fd_calls = [
            mock.call.comments.create_note(int(self.project.expiry_ticket_id),
                                           'Project deleted'),
            mock.call.tickets.update_ticket(int(self.project.expiry_ticket_id),
                                            status=4)
        ]

        swift_calls = [
            mock.call.get_account(),
            mock.call.get_container(c1['name']),
            mock.call.delete_object(c1['name'], o1['name']),
            mock.call.delete_container(c1['name']),
        ]

        keystone_calls = self.get_keystone_calls(expiry_states.DELETED)
        self._test_process(nova_calls=nova_calls, glance_calls=glance_calls,
                           fd_calls=fd_calls, keystone_calls=keystone_calls,
                           neutron_calls=neutron_calls,
                           swift_calls=swift_calls)

    def test_deleted(self):
        """Project in deleted state

        Expected: Nothing
        """
        self.project.expiry_status = expiry_states.DELETED
        self.project.expiry_next_step = PAST
        self.project.expiry_ticket_id = '2'

        self._test_process(invalid=True)

    def test_admin(self):
        """Project in admin state

        Expected: Nothing
        """
        self.project.expiry_status = expiry_states.ADMIN
        self.project.expiry_next_step = PAST
        self.project.expiry_ticket_id = '2'
        self._test_process(invalid=True)

    def test_ticket_status(self):
        """Project in deleted state

        Expected: Nothing
        """
        self.project.expiry_status = 'ticket-01'
        self.project.expiry_next_step = PAST
        self.project.expiry_ticket_id = '2'

        self._test_process(invalid=True)
