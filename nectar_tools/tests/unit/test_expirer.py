import datetime
from freezegun import freeze_time
from unittest import mock

from nectarallocationclient import exceptions as allocation_exceptions

from nectar_tools import config
from nectar_tools import exceptions
from nectar_tools import test

from nectar_tools.expiry import expirer
from nectar_tools.expiry import expiry_states

from nectar_tools.tests import fakes


CONF = config.CONFIG
USAGE_LIMIT_HOURS = expirer.USAGE_LIMIT_HOURS
CPULimit = expirer.CPULimit
BEFORE = '2016-01-01'
AFTER = '2018-01-01'


@freeze_time("2017-01-01")
@mock.patch('nectar_tools.auth.get_session', new=mock.Mock())
@mock.patch('nectar_tools.auth.get_openstacksdk', new=mock.Mock())
class ExpiryTests(test.TestCase):
    def test_project_property(self):
        ex = expirer.Expirer('fake_type', 'fake_res', notifier='fake')
        with mock.patch.object(ex, 'get_project') as mock_project:
            mock_project.return_value = 'fake project'
            self.assertEqual('fake project', ex.project)

    @mock.patch('nectar_tools.utils.get_project_users')
    def test_get_project_managers(self, mock_get_project_users):
        project = fakes.FakeProject()
        ex = expirer.Expirer('fake_type', 'fake_res', notifier='fake')
        mock_get_project_users.return_value = fakes.MANAGERS
        self.assertIsNone(ex.managers)
        with mock.patch.object(ex, 'get_project', return_value=project):
            # Call twice to ensure only one call
            managers = ex._get_project_managers()
            managers = ex._get_project_managers()
            mock_get_project_users.assert_called_once_with(
                ex.k_client, project, role=CONF.keystone.manager_role_id
            )
            self.assertEqual(fakes.MANAGERS, ex.managers)
            self.assertEqual(fakes.MANAGERS, managers)

    @mock.patch('nectar_tools.utils.get_project_users')
    def test_get_project_members(self, mock_get_project_users):
        project = fakes.FakeProject()
        ex = expirer.Expirer('fake_type', 'fake_res', notifier='fake')
        mock_get_project_users.return_value = fakes.MEMBERS
        self.assertIsNone(ex.members)
        with mock.patch.object(ex, 'get_project', return_value=project):
            # Call twice to ensure only one call
            members = ex._get_project_members()
            members = ex._get_project_members()
            mock_get_project_users.assert_called_once_with(
                ex.k_client, project, role=CONF.keystone.member_role_id
            )
            self.assertEqual(fakes.MEMBERS, ex.members)
            self.assertEqual(fakes.MEMBERS, members)

    @mock.patch('nectar_tools.utils.get_project_recipients')
    def test_get_recipients(self, mock_recipients):
        project = fakes.FakeProject()
        ex = expirer.Expirer('fake_type', 'fake_res', notifier='fake')

        mock_recipients.return_value = (
            'manager1@example.org',
            ['manager2@example.org', 'member1@example.org'],
        )
        with mock.patch.object(ex, 'get_project', return_value=project):
            to, cc = ex._get_recipients()

        mock_recipients.assert_called_once_with(ex.k_client, ex.project)
        self.assertEqual('manager1@example.org', to)
        cc.sort()
        self.assertEqual(['manager2@example.org', 'member1@example.org'], cc)

    def test_send_notification(self):
        ex = expirer.Expirer('fake_type', 'fake_res', notifier='fake')
        with test.nested(
            mock.patch.object(ex, 'notifier'),
            mock.patch.object(
                ex, 'get_status', return_value=expiry_states.ACTIVE
            ),
            mock.patch.object(
                ex, '_get_notification_context', return_value={'foo': 'bar'}
            ),
            mock.patch.object(
                ex,
                '_get_recipients',
                return_value=('owner@fake.org', ['manager1@fake.org']),
            ),
        ) as (mock_notifier, mock_status, mock_context, mock_recipients):
            expected_context = {'foo': 'bar', 'foo2': 'bar2'}
            ex._send_notification('fakestage', {'foo2': 'bar2'})
            mock_notifier.send_message.assert_called_with(
                'fakestage',
                'owner@fake.org',
                extra_context=expected_context,
                extra_recipients=['manager1@fake.org'],
                tags=[],
            )

    def test_send_notification_invalid_recipient(self):
        fake_res = mock.Mock()
        fake_res.id = 'fake_id'
        ex = expirer.Expirer('fake_type', fake_res, notifier='fake')
        with test.nested(
            mock.patch.object(ex, 'notifier'),
            mock.patch.object(
                ex, '_get_notification_context', return_value={'foo': 'bar'}
            ),
            mock.patch.object(ex, '_get_recipients', return_value=(None, [])),
        ) as (mock_notifier, mock_context, mock_recipients):
            ex._send_notification('fakestage', {'foo2': 'bar2'})
            mock_notifier.send_message.assert_not_called()

    def test_send_notification_deleted_project(self):
        fake_res = mock.Mock()
        fake_res.id = 'fake_id'
        ex = expirer.Expirer('fake_type', fake_res, notifier='fake')
        with test.nested(
            mock.patch.object(ex, 'notifier'),
            mock.patch.object(
                ex, 'get_status', return_value=expiry_states.DELETED
            ),
        ) as (mock_notifier, mock_status):
            ex._send_notification('fakestage', {'foo2': 'bar2'})
            mock_notifier.send_message.assert_not_called()

    @mock.patch('nectar_tools.expiry.expirer.oslo_messaging')
    def test_send_event(self, mock_oslo_messaging):
        mock_notifier = mock.Mock()
        mock_oslo_messaging.Notifier.return_value = mock_notifier
        ex = expirer.Expirer('fake_type', 'fake_res', notifier='fake')
        ex._send_event('foo', 'bar')
        mock_notifier.audit.assert_called_once_with(mock.ANY, 'foo', 'bar')

    def test_get_status(self):
        expected = 'archived'
        resource = mock.Mock()
        resource.expiry_status = expected
        ex = expirer.Expirer('fake_type', resource, notifier='fake')
        actual = ex.get_status()
        self.assertEqual(expected, actual)

    def test_get_status_none(self):
        resource = mock.Mock()
        resource.expiry_status = None
        ex = expirer.Expirer('fake_type', resource, notifier='fake')
        actual = ex.get_status()
        self.assertEqual('active', actual)

    def test_get_next_step_date(self):
        expected = datetime.datetime(2017, 1, 1)
        resource = mock.Mock()
        resource.expiry_next_step = '2017-01-01'
        ex = expirer.Expirer('fake_type', resource, notifier='fake')
        actual = ex.get_next_step_date()
        self.assertEqual(expected, actual)

    def test_get_next_step_date_none(self):
        resource = mock.Mock()
        resource.expiry_next_step = None
        ex = expirer.Expirer('fake_type', resource, notifier='fake')
        actual = ex.get_next_step_date()
        self.assertIsNone(actual)

    def test_at_next_step(self):
        resource = mock.Mock()
        resource.id = 'fake'
        ex = expirer.Expirer('fake_type', resource, notifier='fake')
        with mock.patch.object(ex, 'get_next_step_date') as mock_next:
            mock_next.return_value = datetime.datetime(2016, 1, 1)
            self.assertTrue(ex.at_next_step())

    def test_at_next_step_negative(self):
        resource = mock.Mock()
        resource.id = 'fake'
        ex = expirer.Expirer('fake_type', resource, notifier='fake')
        with mock.patch.object(ex, 'get_next_step_date') as mock_next:
            mock_next.return_value = datetime.datetime(2018, 1, 1)
            self.assertFalse(ex.at_next_step())
            mock_next.reset_mock()
            mock_next.return_value = None
            self.assertTrue(ex.at_next_step())

    def test_make_next_step_date_feb_1(self):
        now = datetime.datetime(2018, 2, 1)
        actual = expirer.Expirer.make_next_step_date(now)
        self.assertEqual('2018-02-15', actual)

    def test_make_next_step_date_feb_1_30_days(self):
        now = datetime.datetime(2018, 2, 1)
        actual = expirer.Expirer.make_next_step_date(now, 30)
        self.assertEqual('2018-03-03', actual)

    def test_make_next_step_date_dec_14(self):
        now = datetime.datetime(2018, 12, 14)
        actual = expirer.Expirer.make_next_step_date(now)
        self.assertEqual('2018-12-28', actual)

    def test_make_next_step_date_dec_15(self):
        now = datetime.datetime(2018, 12, 15)
        actual = expirer.Expirer.make_next_step_date(now)
        self.assertEqual('2019-01-14', actual)

    def test_make_next_step_date_jan_31(self):
        now = datetime.datetime(2019, 1, 31)
        actual = expirer.Expirer.make_next_step_date(now)
        self.assertEqual('2019-03-02', actual)

    @freeze_time('2018-02-01')
    def test_ready_for_warning(self):
        ex = expirer.Expirer('fake_type', 'fake_res', notifier='fake')
        with mock.patch.object(ex, 'get_warning_date') as mock_warning_date:
            mock_warning_date.return_value = datetime.datetime(2018, 1, 1)
            self.assertTrue(ex.ready_for_warning())
            mock_warning_date.reset_mock()
            mock_warning_date.return_value = datetime.datetime(2018, 3, 1)
            self.assertFalse(ex.ready_for_warning())

    def test_update_project(self):
        project = fakes.FakeProject()
        ex = expirer.Expirer('project', project, notifier='fake')
        today = datetime.datetime.now().strftime(expirer.DATE_FORMAT)
        with mock.patch.object(
            ex.k_client.projects, 'update'
        ) as mock_keystone_update:
            ex._update_resource(
                expiry_next_step='2016-02-02', expiry_status='blah'
            )
            mock_keystone_update.assert_called_with(
                project.id,
                expiry_status='blah',
                expiry_next_step='2016-02-02',
                expiry_updated_at=today,
            )

    def test_finish_expiry(self):
        resource = mock.Mock()
        resource.expiry_status = 'status'
        resource.expiry_next_step = 'step'
        resource.expiry_ticket_id = 'id'

        ex = expirer.Expirer('fake_type', resource, notifier='fake')
        message = 'expiry is finished'

        with test.nested(
            mock.patch.object(ex, 'notifier'),
            mock.patch.object(ex, '_update_resource'),
        ) as (mock_notifier, mock_update_resource):
            ex.finish_expiry(message=message)
            mock_notifier.finish.assert_called_once_with(message=message)
            mock_update_resource.assert_called_once_with(
                expiry_status='', expiry_next_step='', expiry_ticket_id='0'
            )

    def test_get_expiry_date(self):
        resource = mock.Mock()
        ex = expirer.Expirer('fake_type', resource, notifier='fake')
        with mock.patch.object(ex, 'make_next_step_date') as mock_make:
            ex.get_expiry_date()
            mock_make.assert_called_with(
                datetime.datetime(2017, 1, 1), days=30
            )


@freeze_time("2017-01-01")
@mock.patch('nectar_tools.auth.get_session', new=mock.Mock())
@mock.patch('nectar_tools.auth.get_openstacksdk', new=mock.Mock())
class ProjectExpirerTests(test.TestCase):
    def test_check_archiving_status_success(self):
        project = fakes.FakeProject()
        ex = expirer.ProjectExpirer(project, archivers='fake', notifier='fake')

        with test.nested(
            mock.patch.object(ex, 'set_project_archived'),
            mock.patch.object(ex, 'archiver'),
        ) as (mock_set_archived, mock_archiver):
            mock_archiver.is_archive_successful.return_value = True
            ex.check_archiving_status()
            mock_archiver.is_archive_successful.assert_called_once_with()
            mock_set_archived.assert_called_with()

    def test_check_archiving_status_negative(self):
        project = fakes.FakeProject()
        ex = expirer.ProjectExpirer(project, archivers='fake', notifier='fake')

        with test.nested(
            mock.patch.object(ex, 'set_project_archived'),
            mock.patch.object(ex, 'archiver'),
            mock.patch.object(ex, 'archive_project'),
        ) as (mock_set_archived, mock_archiver, mock_archive):
            mock_archiver.is_archive_successful.return_value = False
            ex.check_archiving_status()
            mock_archiver.is_archive_successful.assert_called_once_with()
            mock_set_archived.assert_not_called()
            mock_archive.assert_called_with()

    def test_restrict_project(self):
        project = fakes.FakeProject()
        ex = expirer.ProjectExpirer(project, archivers='fake', notifier='fake')
        one_month = (
            datetime.datetime.now() + datetime.timedelta(days=30)
        ).strftime(expirer.DATE_FORMAT)

        with test.nested(
            mock.patch.object(ex, '_send_notification'),
            mock.patch.object(ex, '_update_resource'),
            mock.patch.object(ex, 'archiver'),
            mock.patch.object(ex, 'send_event'),
        ) as (
            mock_notification,
            mock_update_resource,
            mock_archiver,
            mock_event,
        ):
            ex.restrict_project()
            mock_update_resource.assert_called_with(
                expiry_next_step=one_month,
                expiry_status=expiry_states.RESTRICTED,
            )

            mock_archiver.zero_quota.assert_called_once_with()
            mock_notification.assert_called_with('restrict')
            mock_event.assert_called_once_with('restrict')

    def test_restrict_project_notification_exception(self):
        project = fakes.FakeProject(expiry_status='', expiry_next_step='')
        ex = expirer.ProjectExpirer(project, archivers='fake', notifier='fake')
        one_month = (
            datetime.datetime.now() + datetime.timedelta(days=30)
        ).strftime(expirer.DATE_FORMAT)

        with test.nested(
            mock.patch.object(ex, '_send_notification'),
            mock.patch.object(ex, '_update_resource'),
            mock.patch.object(ex, 'archiver'),
            mock.patch.object(ex, 'send_event'),
        ) as (
            mock_notification,
            mock_update_resource,
            mock_archiver,
            mock_event,
        ):
            mock_notification.side_effect = Exception('fake')
            try:
                ex.restrict_project()
            except Exception:
                mock_update_resource.assert_has_calls(
                    [
                        mock.call(
                            expiry_next_step=one_month,
                            expiry_status=expiry_states.RESTRICTED,
                        ),
                        mock.call(expiry_next_step='', expiry_status=''),
                    ]
                )

                mock_archiver.zero_quota.assert_called_once_with()
                mock_event.assert_not_called()

    def test_archive_project(self):
        project = fakes.FakeProject(expiry_status=expiry_states.STOPPED)
        ex = expirer.ProjectExpirer(project, archivers='fake', notifier='fake')

        with test.nested(
            mock.patch.object(ex, '_update_resource'),
            mock.patch.object(ex, 'archiver'),
        ) as (mock_update_resource, mock_archiver):
            ex.archive_project()
            mock_archiver.archive_resources.assert_called_once_with()
            expiry_next_step = (
                datetime.datetime.now() + datetime.timedelta(days=90)
            ).strftime(expirer.DATE_FORMAT)
            mock_update_resource.assert_called_with(
                expiry_status=expiry_states.ARCHIVING,
                expiry_next_step=expiry_next_step,
            )

    def test_archive_project_retry(self):
        project = fakes.FakeProject(expiry_status=expiry_states.ARCHIVING)
        ex = expirer.ProjectExpirer(project, archivers='fake', notifier='fake')

        with test.nested(
            mock.patch.object(ex, '_update_resource'),
            mock.patch.object(ex, 'archiver'),
        ) as (mock_update_resource, mock_archiver):
            ex.archive_project()
            mock_archiver.archive_resources.assert_called_once_with()
            mock_update_resource.assert_not_called()

    def test_is_ignored_project(self):
        project = fakes.FakeProject()
        ex = expirer.ProjectExpirer(project, archivers='fake', notifier='fake')
        self.assertFalse(ex.is_ignored_project())

    def test_is_ignored_project_admin(self):
        project = fakes.FakeProject(expiry_status=expiry_states.ADMIN)
        ex = expirer.ProjectExpirer(project, archivers='fake', notifier='fake')
        self.assertTrue(ex.is_ignored_project())

    def test_is_ignored_project_ticket(self):
        project = fakes.FakeProject(expiry_status='ticket-123')
        ex = expirer.ProjectExpirer(project, archivers='fake', notifier='fake')
        self.assertTrue(ex.is_ignored_project())

    def test_is_ignored_project_none(self):
        project = fakes.FakeProject(expiry_status=None)
        ex = expirer.ProjectExpirer(project, archivers='fake', notifier='fake')
        self.assertFalse(ex.is_ignored_project())

    def test_set_project_archived(self):
        project = fakes.FakeProject()
        ex = expirer.ProjectExpirer(project, archivers='fake', notifier='fake')
        with test.nested(
            mock.patch.object(ex, '_update_resource'),
            mock.patch.object(ex, 'send_event'),
        ) as (mock_update, mock_event):
            ex.set_project_archived()
            mock_update.assert_called_with(
                expiry_status=expiry_states.ARCHIVED
            )
            mock_event.assert_called_once_with('archived')

    def test_delete_project(self):
        project = fakes.FakeProject()
        ex = expirer.ProjectExpirer(project, archivers='fake', notifier='fake')
        today = datetime.datetime.now().strftime(expirer.DATE_FORMAT)
        with test.nested(
            mock.patch.object(ex, '_update_resource'),
            mock.patch.object(ex, 'archiver'),
            mock.patch.object(ex, 'notifier'),
            mock.patch.object(ex, 'send_event'),
        ) as (mock_update_resource, mock_archiver, mock_notifier, mock_event):
            ex.delete_project()
            mock_archiver.delete_resources.assert_called_once_with(force=True)
            mock_archiver.delete_archives.assert_called_once_with()
            mock_notifier.finish.assert_called_with(message='Project deleted')
            mock_update_resource.assert_called_with(
                expiry_status=expiry_states.DELETED,
                expiry_next_step='',
                expiry_deleted_at=today,
            )
            mock_event.assert_called_once_with('delete')

    def test_delete_resources(self):
        project = fakes.FakeProject()
        ex = expirer.ProjectExpirer(project, archivers='fake', notifier='fake')
        with mock.patch.object(ex, 'archiver') as mock_archiver:
            ex.delete_resources()
            mock_archiver.delete_resources.assert_called_with(force=False)

    def test_stop_resource_project(self):
        project = fakes.FakeProject()
        ex = expirer.ProjectExpirer(project, archivers='fake', notifier='fake')
        one_month = (
            datetime.datetime.now() + datetime.timedelta(days=30)
        ).strftime(expirer.DATE_FORMAT)

        with test.nested(
            mock.patch.object(ex, '_update_resource'),
            mock.patch.object(ex, 'archiver'),
            mock.patch.object(ex, 'send_event'),
            mock.patch.object(ex, '_send_notification'),
        ) as (
            mock_update_resource,
            mock_archiver,
            mock_event,
            mock_send_notification,
        ):
            ex.stop_resource()
            mock_update_resource.assert_called_with(
                expiry_next_step=one_month, expiry_status=expiry_states.STOPPED
            )

            mock_archiver.stop_resources.assert_called_once_with()
            mock_send_notification.assert_called_once_with('stop')
            mock_event.assert_called_once_with('stop')

    def test_stop_resource_project_notification_exception(self):
        project = fakes.FakeProject(expiry_status='', expiry_next_step='')
        ex = expirer.ProjectExpirer(project, archivers='fake', notifier='fake')
        one_month = (
            datetime.datetime.now() + datetime.timedelta(days=30)
        ).strftime(expirer.DATE_FORMAT)

        with test.nested(
            mock.patch.object(ex, '_update_resource'),
            mock.patch.object(ex, 'archiver'),
            mock.patch.object(ex, 'send_event'),
            mock.patch.object(ex, '_send_notification'),
        ) as (
            mock_update_resource,
            mock_archiver,
            mock_event,
            mock_send_notification,
        ):
            mock_send_notification.side_effect = Exception('fake')
            try:
                ex.stop_resource()
            except Exception:
                mock_update_resource.assert_has_calls(
                    [
                        mock.call(
                            expiry_next_step=one_month,
                            expiry_status=expiry_states.STOPPED,
                        ),
                        mock.call(expiry_status='', expiry_next_step=''),
                    ]
                )

                mock_archiver.stop_resources.assert_called_once_with()
                mock_event.assert_not_called()


@freeze_time("2017-01-01")
@mock.patch('nectar_tools.expiry.notifier.ExpiryNotifier', new=mock.Mock())
@mock.patch(
    'nectarallocationclient.v1.allocations.AllocationManager',
    new=fakes.FakeAllocationManager,
)
@mock.patch('nectar_tools.auth.get_session', new=mock.Mock())
@mock.patch('nectar_tools.auth.get_manila_client', new=mock.Mock())
@mock.patch('nectar_tools.auth.get_openstacksdk', new=mock.Mock())
class AllocationExpiryTests(test.TestCase):
    def test_init(self):
        project = fakes.FakeProject('dummy')
        ex = expirer.AllocationExpirer(project)
        self.assertEqual(fakes.ALLOCATIONS['dummy']['id'], ex.allocation.id)

    def test_init_no_allocation(self):
        project = fakes.FakeProject('no-allocation')
        self.assertRaises(
            exceptions.AllocationDoesNotExist,
            expirer.AllocationExpirer,
            project,
        )

    def test_init_no_allocation_ignore(self):
        project = fakes.FakeProject('no-allocation')
        ex = expirer.AllocationExpirer(project, force_no_allocation=True)
        self.assertEqual('NO-ALLOCATION', ex.allocation.id)

    def test_get_allocation_active(self):
        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project)
        mock_allocations = fakes.FakeAllocationManager()
        active = mock_allocations.get_current('active')

        with mock.patch.object(ex, 'a_client') as mock_api:
            mock_api.allocations.get_current.return_value = active
            output = ex.get_allocation()
            mock_api.allocations.get_current.assert_called_once_with(
                project_id=project.id
            )
            self.assertEqual(active, output)

    def test_get_allocation_no_allocation(self):
        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project)

        with mock.patch.object(ex, 'a_client') as mock_api:
            mock_api.allocations.get_current.side_effect = (
                allocation_exceptions.AllocationDoesNotExist()
            )

            self.assertRaises(
                exceptions.AllocationDoesNotExist, ex.get_allocation
            )

    def test_get_allocation_no_allocation_force(self):
        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project, force_no_allocation=True)

        with mock.patch.object(ex, 'a_client') as mock_api:
            mock_api.allocations.get_current.side_effect = (
                allocation_exceptions.AllocationDoesNotExist()
            )

            output = ex.get_allocation()
            self.assertEqual('NO-ALLOCATION', output.id)

    def test_get_allocation_active_declined(self):
        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project)

        mock_allocations = fakes.FakeAllocationManager()
        declined1 = mock_allocations.get_current('declined1')
        active = mock_allocations.get_current('active')

        with mock.patch.object(ex, 'a_client') as mock_api:
            mock_api.allocations.get_current.return_value = declined1
            mock_api.allocations.get_last_approved.return_value = active
            output = ex.get_allocation()
            mock_api.allocations.get_current.assert_called_once_with(
                project_id=project.id
            )
            self.assertEqual(declined1, output)

    def test_get_allocation_active_declined_expired(self):
        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project)

        mock_allocations = fakes.FakeAllocationManager()
        declined2 = mock_allocations.get_current('declined2')
        active = mock_allocations.get_current('active')

        with mock.patch.object(ex, 'a_client') as mock_api:
            mock_api.allocations.get_current.return_value = declined2
            mock_api.allocations.get_last_approved.return_value = active
            output = ex.get_allocation()
            mock_api.allocations.get_current.assert_called_once_with(
                project_id=project.id
            )
            self.assertEqual(active, output)

    def test_get_allocation_active_pending(self):
        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project)

        mock_allocations = fakes.FakeAllocationManager()
        pending2 = mock_allocations.get_current('pending2')
        active = mock_allocations.get_current('active')

        with mock.patch.object(ex, 'a_client') as mock_api:
            mock_api.allocations.get_current.return_value = pending2
            mock_api.allocations.get_last_approved.return_value = active
            output = ex.get_allocation()
            mock_api.allocations.get_current.assert_called_once_with(
                project_id=project.id
            )
            self.assertEqual(pending2, output)

    def test_get_allocation_active_pending_expired(self):
        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project)

        mock_allocations = fakes.FakeAllocationManager()
        pending1 = mock_allocations.get_current('pending1')
        active = mock_allocations.get_current('active')

        with mock.patch.object(ex, 'a_client') as mock_api:
            mock_api.allocations.get_current.return_value = pending1
            mock_api.allocations.get_last_approved.return_value = active
            output = ex.get_allocation()
            mock_api.allocations.get_current.assert_called_once_with(
                project_id=project.id
            )
            self.assertEqual(active, output)

    def test_process_allocation_renewed(self):
        project = fakes.FakeProject(expiry_status=expiry_states.RENEWED)
        ex = expirer.AllocationExpirer(project)

        with mock.patch.object(ex, 'revert_expiry') as mock_revert:
            self.assertTrue(ex.process())
            mock_revert.assert_called_once_with()

    def test_process_force_delete(self):
        project = fakes.FakeProject('warning1')
        ex = expirer.AllocationExpirer(project, force_delete=True)

        with mock.patch.object(ex, 'delete_project') as mock_delete:
            self.assertTrue(ex.process())
            mock_delete.assert_called_with()

    def test_process_active(self):
        project = fakes.FakeProject('active')
        ex = expirer.AllocationExpirer(project)
        with mock.patch.object(ex, 'ready_for_warning') as mock_ready:
            mock_ready.return_value = False
            self.assertFalse(ex.process())

    def test_process_send_warning_long(self):
        project = fakes.FakeProject('warning1')
        ex = expirer.AllocationExpirer(project)

        with mock.patch.object(ex, 'send_warning') as mock_send_warning:
            self.assertTrue(ex.process())
            mock_send_warning.assert_called_with()

    def test_process_send_warning_short(self):
        project = fakes.FakeProject('warning2')
        ex = expirer.AllocationExpirer(project)

        with mock.patch.object(ex, 'send_warning') as mock_send_warning:
            self.assertTrue(ex.process())
            mock_send_warning.assert_called_with()
            mock_send_warning.reset_mock()

    def test_process_warning(self):
        project = fakes.FakeProject(
            expiry_status=expiry_states.WARNING, expiry_next_step=BEFORE
        )
        ex = expirer.AllocationExpirer(project)

        with mock.patch.object(ex, 'restrict_project') as mock_restrict:
            self.assertTrue(ex.process())
            mock_restrict.assert_called_with()

    def test_process_restricted(self):
        project = fakes.FakeProject(
            expiry_status=expiry_states.RESTRICTED, expiry_next_step=BEFORE
        )
        ex = expirer.AllocationExpirer(project)

        with mock.patch.object(ex, 'stop_resource') as mock_stop_resource:
            self.assertTrue(ex.process())
            mock_stop_resource.assert_called_with()

    def test_process_stopped(self):
        project = fakes.FakeProject(
            expiry_status=expiry_states.STOPPED, expiry_next_step=BEFORE
        )
        ex = expirer.AllocationExpirer(project)

        with mock.patch.object(ex, 'archive_project') as mock_archive_project:
            self.assertTrue(ex.process())
            mock_archive_project.assert_called_with()

    def test_process_archiving(self):
        project = fakes.FakeProject(
            expiry_status=expiry_states.ARCHIVING, expiry_next_step=AFTER
        )
        ex = expirer.AllocationExpirer(project)

        with mock.patch.object(ex, 'check_archiving_status') as mock_check:
            self.assertTrue(ex.process())
            mock_check.assert_called_with()

    def test_process_archiving_expired(self):
        project = fakes.FakeProject(
            expiry_status=expiry_states.ARCHIVING, expiry_next_step=BEFORE
        )
        ex = expirer.AllocationExpirer(project)

        with mock.patch.object(ex, 'set_project_archived') as mock_proj_arch:
            self.assertTrue(ex.process())
            mock_proj_arch.assert_called_with()

    def test_process_archived(self):
        project = fakes.FakeProject(
            expiry_status=expiry_states.ARCHIVED, expiry_next_step=BEFORE
        )
        ex = expirer.AllocationExpirer(project)

        with mock.patch.object(ex, 'delete_project') as mock_delete:
            self.assertTrue(ex.process())
            mock_delete.assert_called_with()

    def test_process_archived_not_expiry_next_step(self):
        project = fakes.FakeProject(
            expiry_status=expiry_states.ARCHIVED, expiry_next_step=AFTER
        )
        ex = expirer.AllocationExpirer(project)

        with mock.patch.object(ex, 'delete_resources') as mock_delete:
            self.assertTrue(ex.process())
            mock_delete.assert_called_with()

    def test_get_notice_period_days(self):
        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project)
        mock_allocations = fakes.FakeAllocationManager()

        ex.allocation = mock_allocations.get_current('active')
        days = ex.get_notice_period_days()
        self.assertEqual(days, 30)

        ex.allocation = mock_allocations.get_current('expired')
        days = ex.get_notice_period_days()
        self.assertEqual(days, 30)

        ex.allocation = mock_allocations.get_current('warning1')
        days = ex.get_notice_period_days()
        self.assertEqual(days, 30)

        ex.allocation = mock_allocations.get_current('warning2')
        days = ex.get_notice_period_days()
        self.assertEqual(days, 3)

    @freeze_time('2018-01-01')
    def test_get_expiry_date(self):
        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project)
        mock_allocations = fakes.FakeAllocationManager()
        ex.allocation = mock_allocations.get_current('active')
        expected_expiry_date = '2018-01-31'

        with mock.patch.object(
            ex, 'get_notice_period_days'
        ) as mock_notice_days:
            mock_notice_days.return_value = 30
            self.assertEqual(expected_expiry_date, ex.get_expiry_date())

    def test_get_expiry_date_before_allocation_end(self):
        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project)
        mock_allocations = fakes.FakeAllocationManager()
        ex.allocation = mock_allocations.get_current('active')
        expected_expiry_date = '2018-01-01'

        with mock.patch.object(
            ex, 'get_notice_period_days'
        ) as mock_notice_days:
            mock_notice_days.return_value = 30
            self.assertEqual(expected_expiry_date, ex.get_expiry_date())

    def test_get_warning_date(self):
        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project)
        mock_allocations = fakes.FakeAllocationManager()

        ex.allocation = mock_allocations.get_current('active')
        warning_date = ex.get_warning_date().strftime(expirer.DATE_FORMAT)
        self.assertEqual(warning_date, '2017-12-02')

        ex.allocation = mock_allocations.get_current('expired')
        warning_date = ex.get_warning_date().strftime(expirer.DATE_FORMAT)
        self.assertEqual(warning_date, '2016-06-01')

        ex.allocation = mock_allocations.get_current('warning1')
        warning_date = ex.get_warning_date().strftime(expirer.DATE_FORMAT)
        self.assertEqual(warning_date, '2016-12-02')

        ex.allocation = mock_allocations.get_current('warning2')
        warning_date = ex.get_warning_date().strftime(expirer.DATE_FORMAT)
        self.assertEqual(warning_date, '2016-12-29')

    @mock.patch('nectar_tools.common.service_units.SUinfo')
    @freeze_time('2018-02-01')
    def test_ready_for_warning_under_budget(self, mock_su_info):
        project = fakes.FakeProject(name='Allocation')
        mock_su_info.return_value = fakes.FakeSUinfo(usage=100, budget=3400)

        ex = expirer.AllocationExpirer(project)
        ex.allocation = fakes.get_allocation()

        with mock.patch.object(ex, 'get_warning_date') as mock_warning_date:
            mock_warning_date.return_value = datetime.datetime(2018, 1, 1)
            self.assertTrue(ex.ready_for_warning())
            mock_warning_date.reset_mock()
            mock_warning_date.return_value = datetime.datetime(2018, 3, 1)
            self.assertFalse(ex.ready_for_warning())

    @freeze_time('2018-02-01')
    @mock.patch('nectar_tools.common.service_units.SUinfo')
    def test_ready_for_warning_no_budget(self, mock_su_info):
        mock_su_info.return_value = fakes.FakeSUinfo(usage=10, budget=0)
        project = fakes.FakeProject(name='Allocation')

        ex = expirer.AllocationExpirer(project)
        # Default allocation doesn't have rating budget

        with mock.patch.object(ex, 'get_warning_date') as mock_warning_date:
            mock_warning_date.return_value = datetime.datetime(2018, 1, 1)
            self.assertTrue(ex.ready_for_warning())
            mock_warning_date.reset_mock()
            mock_warning_date.return_value = datetime.datetime(2018, 3, 1)
            self.assertFalse(ex.ready_for_warning())

    @freeze_time('2018-02-01')
    @mock.patch('nectar_tools.common.service_units.SUinfo')
    def test_ready_for_warning_over_budget(self, mock_su_info):
        mock_su_info.return_value = fakes.FakeSUinfo(usage=7, budget=10)
        project = fakes.FakeProject(name='Allocation')
        ex = expirer.AllocationExpirer(project)
        with mock.patch.object(ex, 'get_warning_date') as mock_warning_date:
            mock_warning_date.return_value = datetime.datetime(2018, 1, 1)
            self.assertTrue(ex.ready_for_warning())
            mock_warning_date.reset_mock()
            mock_warning_date.return_value = datetime.datetime(2018, 3, 1)
            self.assertFalse(ex.ready_for_warning())

            mock_su_info.return_value = fakes.FakeSUinfo(usage=8, budget=10)
            mock_warning_date.return_value = datetime.datetime(2018, 1, 1)
            self.assertTrue(ex.ready_for_warning())
            mock_warning_date.reset_mock()
            mock_warning_date.return_value = datetime.datetime(2018, 3, 1)
            self.assertTrue(ex.ready_for_warning())

    @mock.patch('nectar_tools.common.service_units.SUinfo')
    def test_ready_for_restricted(self, mock_su_info):
        project = fakes.FakeProject(name='Allocation')
        ex = expirer.AllocationExpirer(project)
        with mock.patch.object(ex, 'at_next_step') as mock_at_next_step:
            mock_su_info.return_value = fakes.FakeSUinfo(usage=7, budget=10)
            mock_at_next_step.return_value = False
            self.assertFalse(ex.ready_for_restricted())

            mock_su_info.return_value = fakes.FakeSUinfo(usage=10, budget=10)
            mock_at_next_step.return_value = False
            self.assertTrue(ex.ready_for_restricted())

            mock_su_info.return_value = fakes.FakeSUinfo(usage=7, budget=0)
            mock_at_next_step.return_value = False
            self.assertFalse(ex.ready_for_restricted())

            mock_su_info.return_value = fakes.FakeSUinfo(usage=7, budget=10)
            mock_at_next_step.return_value = True
            self.assertTrue(ex.ready_for_restricted())

    def test_should_process(self):
        project = fakes.FakeProject(name='Allocation')
        ex = expirer.AllocationExpirer(project)
        self.assertTrue(ex.should_process())

        project = fakes.FakeProject(name='pt-33')
        ex = expirer.AllocationExpirer(project)
        self.assertFalse(ex.should_process())

        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project)
        mock_allocations = fakes.FakeAllocationManager()
        ex.allocation = mock_allocations.get_current('active')
        self.assertTrue(ex.should_process())

        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project)
        ex.allocation = mock_allocations.get_current('pending1')
        self.assertFalse(ex.should_process())

        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project)
        ex.allocation = mock_allocations.get_current('active')

        with mock.patch.object(ex, 'is_ignored_project') as mock_ignore:
            mock_ignore.return_value = True
            self.assertFalse(ex.should_process())
            mock_ignore.reset_mock()
            mock_ignore.return_value = False
            self.assertTrue(ex.should_process())

    def test_revert_expiry_warning(self):
        project = fakes.FakeProject(
            expiry_status=expiry_states.WARNING,
            expiry_next_step=BEFORE,
            expiry_ticket_id='20',
        )
        ex = expirer.AllocationExpirer(project)

        with test.nested(
            mock.patch.object(ex, 'archiver'),
            mock.patch.object(ex, 'finish_expiry'),
        ) as (mock_archiver, mock_finish):
            ex.revert_expiry()
            mock_finish.assert_called_once_with(
                message='Allocation has been renewed'
            )
            mock_archiver.reset_quota.assert_not_called()
            mock_archiver.enable_resources.assert_called_once_with()

    def test_revert_expiry_restricted(self):
        project = fakes.FakeProject(
            expiry_status=expiry_states.RESTRICTED,
            expiry_next_step=BEFORE,
            expiry_ticket_id='20',
        )
        ex = expirer.AllocationExpirer(project)

        with test.nested(
            mock.patch.object(ex, 'archiver'),
            mock.patch.object(ex, 'finish_expiry'),
        ) as (mock_archiver, mock_finish):
            ex.revert_expiry()
            mock_finish.assert_called_once_with(
                message='Allocation has been renewed'
            )
            mock_archiver.reset_quota.assert_called_once_with()
            mock_archiver.enable_resources.assert_called_once_with()

    def test_revert_expiry_stopped(self):
        project = fakes.FakeProject(
            expiry_status=expiry_states.STOPPED,
            expiry_next_step=BEFORE,
            expiry_ticket_id='20',
        )
        ex = expirer.AllocationExpirer(project)

        with test.nested(
            mock.patch.object(ex, 'archiver'),
            mock.patch.object(ex, 'finish_expiry'),
        ) as (mock_archiver, mock_finish):
            ex.revert_expiry()
            mock_finish.assert_called_once_with(
                message='Allocation has been renewed'
            )
            mock_archiver.reset_quota.assert_called_once_with()
            mock_archiver.enable_resources.assert_called_once_with()

    def test_revert_expiry_renewed(self):
        project = fakes.FakeProject(
            expiry_status=expiry_states.RENEWED,
            expiry_next_step=BEFORE,
            expiry_ticket_id='20',
        )
        ex = expirer.AllocationExpirer(project)

        with test.nested(
            mock.patch.object(ex, 'archiver'),
            mock.patch.object(ex, 'finish_expiry'),
        ) as (mock_archiver, mock_finish):
            ex.revert_expiry()
            mock_finish.assert_called_once_with(
                message='Allocation has been renewed'
            )
            mock_archiver.reset_quota.assert_called_once_with()
            mock_archiver.enable_resources.assert_called_once_with()

    def test_send_warning(self):
        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project)
        mock_allocations = fakes.FakeAllocationManager()
        ex.allocation = mock_allocations.get_current('active')
        next_step_date = '2018-01-01'

        self.assertEqual(ex.allocation.end_date, next_step_date)
        with test.nested(
            mock.patch.object(ex, '_send_notification'),
            mock.patch.object(ex, '_update_resource'),
            mock.patch.object(ex, 'send_event'),
            mock.patch.object(ex, 'get_expiry_date'),
        ) as (
            mock_notification,
            mock_update_resource,
            mock_event,
            mock_expiry_date,
        ):
            mock_expiry_date.return_value = next_step_date
            ex.send_warning()
            mock_update_resource.assert_called_with(
                expiry_next_step=next_step_date,
                expiry_status=expiry_states.WARNING,
            )
            extra_context = {'expiry_date': next_step_date}
            mock_expiry_date.assert_called_once_with()
            mock_notification.assert_called_with(
                'first-warning', extra_context=extra_context
            )
            mock_event.assert_called_once_with(
                'first-warning', extra_context=extra_context
            )

    def test_send_warning_notification_exception(self):
        project = fakes.FakeProject(expiry_status='', expiry_next_step='')
        ex = expirer.AllocationExpirer(project)
        mock_allocations = fakes.FakeAllocationManager()
        ex.allocation = mock_allocations.get_current('active')
        next_step_date = '2018-01-01'

        self.assertEqual(ex.allocation.end_date, next_step_date)
        with test.nested(
            mock.patch.object(ex, '_send_notification'),
            mock.patch.object(ex, '_update_resource'),
            mock.patch.object(ex, 'send_event'),
            mock.patch.object(ex, 'get_expiry_date'),
        ) as (
            mock_notification,
            mock_update_resource,
            mock_event,
            mock_expiry_date,
        ):
            mock_expiry_date.return_value = next_step_date
            mock_notification.side_effect = Exception('fake')
            try:
                ex.send_warning()
            except Exception:
                mock_expiry_date.assert_called_once_with()
                mock_update_resource.assert_has_calls(
                    [
                        mock.call(
                            expiry_next_step=next_step_date,
                            expiry_status=expiry_states.WARNING,
                        ),
                        mock.call(expiry_next_step='', expiry_status=''),
                    ]
                )
                mock_event.assert_not_called()

    @freeze_time('2018-02-01')
    def test_send_warning_late(self):
        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project)
        mock_allocations = fakes.FakeAllocationManager()
        ex.allocation = mock_allocations.get_current('active')
        next_step_date = '2018-03-03'

        with test.nested(
            mock.patch.object(ex, '_send_notification'),
            mock.patch.object(ex, '_update_resource'),
            mock.patch.object(ex, 'send_event'),
            mock.patch.object(ex, 'get_expiry_date'),
        ) as (
            mock_notification,
            mock_update_resource,
            mock_event,
            mock_expiry_date,
        ):
            mock_expiry_date.return_value = next_step_date
            ex.send_warning()
            mock_update_resource.assert_called_with(
                expiry_next_step=next_step_date,
                expiry_status=expiry_states.WARNING,
            )
            extra_context = {'expiry_date': next_step_date}
            mock_expiry_date.assert_called_once_with()
            mock_notification.assert_called_with(
                'first-warning', extra_context=extra_context
            )
            mock_event.assert_called_once_with(
                'first-warning', extra_context=extra_context
            )

    def test_send_event(self):
        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project)
        with test.nested(
            mock.patch.object(ex, '_send_event'),
            mock.patch.object(ex, '_get_notification_context'),
        ) as (mock_send, mock_context):
            mock_context.return_value = {
                'foo': 'bar',
                'allocation': ex.allocation.to_dict(),
            }
            ex.send_event('foo', {'uni': 'melb'})
            payload = {
                'allocation': ex.allocation.to_dict(),
                'uni': 'melb',
                'foo': 'bar',
            }
            mock_send.assert_called_once_with('expiry.allocation.foo', payload)

    def test_send_notification(self):
        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project)
        with test.nested(
            mock.patch.object(ex, 'notifier'),
            mock.patch.object(
                ex, '_get_notification_context', return_value={'foo': 'bar'}
            ),
            mock.patch.object(
                ex,
                '_get_recipients',
                return_value=('owner@fake.org', ['manager1@fake.org']),
            ),
        ) as (mock_notifier, mock_context, mock_recipients):
            expected_context = {'foo': 'bar', 'foo2': 'bar2'}
            ex._send_notification('fakestage', {'foo2': 'bar2'})
            mock_notifier.send_message.assert_called_with(
                'fakestage',
                'owner@fake.org',
                extra_context=expected_context,
                extra_recipients=['manager1@fake.org'],
                tags=['allocation-1'],
            )

    def test_send_notification_no_allocation_ignore(self):
        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project, force_no_allocation=True)
        with mock.patch.object(ex, 'notifier') as mock_notifier:
            ex._send_notification('fakestage', {'foo2': 'bar2'})
            mock_notifier.send_message.assert_not_called()

    def test_send_notification_allocation_disabled_notifications(self):
        project = fakes.FakeProject('no-notifications')
        ex = expirer.AllocationExpirer(project)
        with mock.patch.object(ex, 'notifier') as mock_notifier:
            ex._send_notification('fakestage', {'foo2': 'bar2'})
            mock_notifier.send_message.assert_not_called()

    @mock.patch('nectar_tools.utils.get_allocation_recipients')
    def test_get_recipients(self, mock_recipients):
        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project)

        mock_recipients.return_value = (
            'manager1@example.org',
            ['manager2@example.org', 'member1@example.org'],
        )

        to, cc = ex._get_recipients()

        mock_recipients.assert_called_once_with(ex.k_client, ex.allocation)
        self.assertEqual('manager1@example.org', to)
        cc.sort()
        self.assertEqual(['manager2@example.org', 'member1@example.org'], cc)

    def test_delete_project(self):
        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project)
        allocations = fakes.FakeAllocationManager()
        allocation = allocations.get_current('active')

        with test.nested(
            mock.patch(
                'nectar_tools.expiry.expirer.ProjectExpirer.delete_project'
            ),
            mock.patch.object(ex, 'allocation', return_value=allocation),
            mock.patch.object(ex, 'get_current_allocation'),
        ) as (mock_parent_delete, mock_allocation, mock_get_current):
            mock_get_current.return_value = mock_allocation
            ex.delete_project()
            mock_parent_delete.assert_called_once_with()
            mock_get_current.assert_called_once_with()
            mock_allocation.delete.assert_called_once_with()

    @mock.patch('nectar_tools.common.service_units.SUinfo')
    def test_get_notification_context(self, mock_su_info):
        su_info = fakes.FakeSUinfo(usage=20, budget=50)
        mock_su_info.return_value = su_info
        project = fakes.FakeProjectWithOwner()
        ex = expirer.AllocationExpirer(project)

        with test.nested(
            mock.patch.object(ex, '_get_project_managers'),
            mock.patch.object(ex, '_get_project_members'),
        ) as (mock_managers, mock_members):
            mock_managers.return_value = fakes.MANAGERS
            mock_members.return_value = fakes.MEMBERS
            actual = ex._get_notification_context()

        expected = {
            'allocation': {
                'approver_email': 'approver@fake.org',
                'contact_email': 'fake@fake.org',
                'end_date': '2016-01-01',
                'id': 1,
                'modified_time': '2015-01-02T10:10:10Z',
                'notifications': True,
                'project_id': 'dummy',
                'project_name': 'dummy-name',
                'quotas': [],
                'start_date': '2015-01-01',
                'status': 'A',
            },
            'managers': [
                {
                    'email': 'manager1@example.org',
                    'enabled': True,
                    'id': 'manager1',
                    'name': 'manager1@example.org',
                },
                {
                    'email': 'manager2@example.org',
                    'enabled': True,
                    'id': 'manager2',
                    'name': 'manager2@example.org',
                },
            ],
            'members': [
                {
                    'email': 'member1@example.org',
                    'enabled': True,
                    'id': 'member1',
                    'name': 'member1@example.org',
                },
                {
                    'email': 'member2@example.org',
                    'enabled': False,
                    'id': 'member2',
                    'name': 'member2@example.org',
                },
                {
                    'email': 'manager1@example.org',
                    'enabled': True,
                    'id': 'manager1',
                    'name': 'manager1@example.org',
                },
            ],
            'su_info': su_info.to_dict(),
        }

        self.assertEqual(expected, actual)


@freeze_time("2017-01-01")
@mock.patch('nectar_tools.expiry.notifier.ExpiryNotifier', new=mock.Mock())
@mock.patch('nectar_tools.auth.get_session', new=mock.Mock())
class PTExpiryTests(test.TestCase):
    def test_should_process(self):
        project = fakes.FakeProjectWithOwner()
        ex = expirer.PTExpirer(project)
        with mock.patch.object(ex, 'pending_allocations') as allocations:
            allocations.return_value = []
            should = ex.should_process()
        self.assertTrue(should)

    def test_should_process_deleted(self):
        project = fakes.FakeProjectWithOwner(expiry_status='deleted')
        ex = expirer.PTExpirer(project)
        should = ex.should_process()
        self.assertFalse(should)

    def test_should_process_admin(self):
        project = fakes.FakeProjectWithOwner(expiry_status='admin')
        ex = expirer.PTExpirer(project)
        with mock.patch.object(ex, 'pending_allocations') as allocations:
            allocations.return_value = []
            should = ex.should_process()
        self.assertFalse(should)

    def test_should_process_no_owner(self):
        project = fakes.FakeProjectWithOwner(owner=None)
        ex = expirer.PTExpirer(project)
        with mock.patch.object(ex, 'pending_allocations') as allocations:
            allocations.return_value = []
            should = ex.should_process()
        self.assertFalse(should)

    def test_should_process_non_pt(self):
        project = fakes.FakeProjectWithOwner(name='MeritAllocation')
        ex = expirer.PTExpirer(project)
        with mock.patch.object(ex, 'pending_allocations') as allocations:
            allocations.return_value = []
            should = ex.should_process()
        self.assertFalse(should)

    def test_should_process_has_pending_allocations(self):
        project = fakes.FakeProjectWithOwner()
        ex = expirer.PTExpirer(project)
        with mock.patch.object(ex, 'pending_allocations') as allocations:
            allocations.return_value = [mock.Mock(id='123')]
            should = ex.should_process()
        self.assertFalse(should)

    @mock.patch('nectar_tools.auth.get_allocation_client')
    def test_pending_allocation(self, mock_get_allocation):
        mock_client = mock_get_allocation.return_value
        project = fakes.FakeProjectWithOwner()
        ex = expirer.PTExpirer(project)
        allocations = ex.pending_allocations()
        self.assertEqual(
            mock_client.allocations.list.return_value, allocations
        )
        mock_client.allocations.list.assert_called_once_with(
            contact_email=project.owner.name,
            modified_time__lt='2016-10-01T00:00:00',
            parent_request__isnull=True,
            convert_trial_project=True,
            status='E',
        )

    @mock.patch('nectar_tools.auth.get_manuka_client')
    def test_is_pt_too_old_negative(self, mock_get_manuka):
        mock_manuka = mock_get_manuka.return_value
        fake_account = mock_manuka.users.get.return_value
        fake_account.registered_at = datetime.datetime.strptime(
            AFTER, expirer.DATE_FORMAT
        )

        project = fakes.FakeProjectWithOwner()
        ex = expirer.PTExpirer(project)

        self.assertFalse(ex.is_pt_too_old())

    @mock.patch('nectar_tools.auth.get_manuka_client')
    def test_is_pt_too_old(self, mock_get_manuka):
        mock_manuka = mock_get_manuka.return_value
        fake_account = mock_manuka.users.get.return_value
        fake_account.registered_at = datetime.datetime(2015, 1, 1)

        project = fakes.FakeProjectWithOwner()
        ex = expirer.PTExpirer(project)

        self.assertTrue(ex.is_pt_too_old())

    def _test_check_cpu_usage(self, usage, expect):
        project = fakes.FakeProjectWithOwner()
        ex = expirer.PTExpirer(project)
        mock_usage = mock.Mock()
        mock_usage.total_vcpus_usage = usage
        with mock.patch.object(ex, 'n_client') as mock_nova:
            mock_nova.usage.get.return_value = mock_usage
            limit = ex.check_cpu_usage()
            self.assertEqual(expect, limit)

    def test_check_cpu_usage_under(self):
        self._test_check_cpu_usage(0, CPULimit.UNDER_LIMIT)
        self._test_check_cpu_usage(1, CPULimit.UNDER_LIMIT)
        self._test_check_cpu_usage(4383, CPULimit.UNDER_LIMIT)

    def test_check_cpu_usage_over(self):
        self._test_check_cpu_usage(4384, CPULimit.OVER_LIMIT)
        self._test_check_cpu_usage(5260, CPULimit.OVER_LIMIT)
        self._test_check_cpu_usage(15260, CPULimit.OVER_LIMIT)

    def test_check_cpu_usage_none(self):
        project = fakes.FakeProjectWithOwner()
        ex = expirer.PTExpirer(project)
        mock_usage = mock.Mock()
        mock_usage.total_vcpus_usage = None
        with mock.patch.object(ex, 'n_client') as mock_nova:
            mock_nova.usage.get.return_value = mock_usage
            self.assertRaises(exceptions.NoUsageError, ex.check_cpu_usage)

    def test_get_notification_context(self):
        project = fakes.FakeProjectWithOwner()
        ex = expirer.PTExpirer(project)
        actual = ex._get_notification_context()
        expected = {
            'project': {
                'expiry_next_step': '',
                'expiry_status': '',
                'expiry_ticket_id': '0',
                'id': 'dummy',
                'name': 'pt-123',
                'owner': {
                    'email': 'fake@fake.com',
                    'enabled': True,
                    'id': 'dummy',
                    'name': 'fake@fake.com',
                },
            }
        }
        self.assertEqual(expected, actual)


MOCK_A_CLIENT = mock.Mock()


@freeze_time("2017-01-01")
@mock.patch('nectar_tools.expiry.notifier.ExpiryNotifier', new=mock.Mock())
@mock.patch('nectar_tools.auth.get_session', new=mock.Mock())
@mock.patch('nectar_tools.auth.get_allocation_client', new=MOCK_A_CLIENT)
class PTExpiryProcessTests(test.TestCase):
    def setUp(self):
        super().setUp()
        client = MOCK_A_CLIENT.return_value
        client.allocations.list.return_value = []

    def tearDown(self):
        super().tearDown()
        MOCK_A_CLIENT.reset_mock()

    def test_process_invalid(self):
        project = fakes.FakeProjectWithOwner()
        ex = expirer.PTExpirer(project)
        with mock.patch.object(ex, 'should_process') as mock_should:
            mock_should.return_value = False
            self.assertRaises(exceptions.InvalidProject, ex.process)

    @mock.patch('nectar_tools.auth.get_manuka_client')
    def test_process_ok(self, mock_get_manuka):
        mock_manuka = mock_get_manuka.return_value
        fake_account = mock_manuka.users.get.return_value
        fake_account.registered_at = datetime.datetime.strptime(
            AFTER, expirer.DATE_FORMAT
        )
        project = fakes.FakeProjectWithOwner()
        ex = expirer.PTExpirer(project)
        with mock.patch.object(ex, 'check_cpu_usage') as mock_limit:
            mock_limit.return_value = CPULimit.UNDER_LIMIT
            self.assertFalse(ex.process())

    @mock.patch('nectar_tools.auth.get_manuka_client')
    def test_process_project_too_old(self, mock_get_manuka):
        mock_manuka = mock_get_manuka.return_value
        fake_account = mock_manuka.users.get.return_value
        fake_account.registered_at = datetime.datetime(2015, 1, 1)
        project = fakes.FakeProjectWithOwner()
        ex = expirer.PTExpirer(project)
        with test.nested(
            mock.patch.object(ex, 'check_cpu_usage'),
            mock.patch.object(ex, 'send_warning'),
        ) as (mock_limit, mock_send_warning):
            mock_limit.return_value = CPULimit.UNDER_LIMIT
            self.assertTrue(ex.process())
            mock_send_warning.assert_called_once_with()

    def test_process_archiving(self):
        project = fakes.FakeProjectWithOwner(
            expiry_status=expiry_states.ARCHIVING, expiry_next_step=AFTER
        )
        ex = expirer.PTExpirer(project)
        with mock.patch.object(ex, 'check_archiving_status') as mock_status:
            processed = ex.process()
            mock_status.assert_called_with()
            self.assertTrue(processed)

    def test_process_archiving_expired(self):
        project = fakes.FakeProjectWithOwner(
            expiry_status=expiry_states.ARCHIVING, expiry_next_step=BEFORE
        )
        ex = expirer.PTExpirer(project)
        with mock.patch.object(ex, '_update_resource') as mock_update:
            processed = ex.process()
            mock_update.assert_called_with(
                expiry_status=expiry_states.ARCHIVED
            )
            self.assertTrue(processed)

    def test_process_archived(self):
        project = fakes.FakeProjectWithOwner(
            expiry_status=expiry_states.ARCHIVED, expiry_next_step=BEFORE
        )
        ex = expirer.PTExpirer(project)
        with mock.patch.object(ex, 'delete_project') as mock_delete:
            processed = ex.process()
            mock_delete.assert_called_with()
            self.assertTrue(processed)

    def test_process_archived_not_next_step(self):
        project = fakes.FakeProjectWithOwner(
            expiry_status=expiry_states.ARCHIVED, expiry_next_step=AFTER
        )
        ex = expirer.PTExpirer(project)
        with mock.patch.object(ex, 'delete_resources') as mock_delete:
            processed = ex.process()
            mock_delete.assert_called_with()
            self.assertTrue(processed)


@freeze_time('2017-01-01')
@mock.patch('nectar_tools.expiry.notifier.ExpiryNotifier', new=mock.Mock())
@mock.patch(
    'nectarallocationclient.v1.allocations.AllocationManager',
    new=fakes.FakeAllocationManager2,
)
@mock.patch('nectar_tools.auth.get_session', new=mock.Mock())
class AllocationInstanceExpiryTests(test.TestCase):
    def test_init(self):
        project = fakes.FakeProject('dummy', allocation_id=1)
        ex = expirer.AllocationInstanceExpirer(project)
        self.assertEqual(fakes.ALLOCATIONS['dummy']['id'], ex.allocation.id)

    @mock.patch('nectar_tools.utils.get_out_of_zone_instances')
    def test_instances_property(self, mock_instances):
        project = fakes.FakeProject('dummy', allocation_id=1)
        mock_instances.return_value = 'fake instances list'
        ex = expirer.AllocationInstanceExpirer(project)
        self.assertEqual('fake instances list', ex.instances)

    @freeze_time('2017-03-01')
    def test_get_notification_context(self):
        inst1 = fakes.FakeInstance(id='fake1')
        inst2 = fakes.FakeInstance(id='fake2')
        project = fakes.FakeProject(
            'dummy', allocation_id=1, compute_zones='fake'
        )
        ex = expirer.AllocationInstanceExpirer(project)

        with test.nested(
            mock.patch(
                'nectar_tools.expiry.expirer.AllocationExpirer.'
                '_get_notification_context'
            ),
            mock.patch(
                'nectar_tools.expiry.expirer.'
                'AllocationInstanceExpirer.instances',
                new_callable=mock.PropertyMock,
            ),
        ) as (mock_context, mock_instances):
            mock_context.return_value = {'foo': 'bar'}
            mock_instances.return_value = [inst1, inst2]
            result = ex._get_notification_context()
            expected = dict(
                compute_zones='fake',
                out_of_zone_instances=[inst1.__dict__, inst2.__dict__],
                foo='bar',
            )
            self.assertEqual(expected, result)

    def test_get_warning_date(self):
        project = fakes.FakeProject('dummy', allocation_id=1)
        ex = expirer.AllocationInstanceExpirer(project)
        ex.allocation.start_date = '2018-04-01'
        self.assertEqual(datetime.datetime(2018, 5, 31), ex.get_warning_date())

    @mock.patch(
        'nectar_tools.expiry.expirer.AllocationInstanceExpirer.instances',
        new_callable=mock.PropertyMock,
    )
    def test_should_process(self, mock_instances):
        project = fakes.FakeProject(
            allocation_id=1, zone_expiry_status=expiry_states.ACTIVE
        )
        ex = expirer.AllocationInstanceExpirer(project)
        mock_instances.return_value = 'fake instances list'
        self.assertFalse(ex.should_process())

    @mock.patch(
        'nectar_tools.expiry.expirer.AllocationInstanceExpirer.finish_expiry',
        new=mock.Mock(),
    )
    @mock.patch(
        'nectar_tools.expiry.expirer.AllocationInstanceExpirer.instances',
        new_callable=mock.PropertyMock,
    )
    def test_should_process_expiry_warning(self, mock_instances):
        project = fakes.FakeProject(
            allocation_id=1, zone_expiry_status=expiry_states.WARNING
        )
        ex = expirer.AllocationInstanceExpirer(project)
        mock_instances.return_value = 'fake instances list'
        self.assertFalse(ex.should_process())
        ex.finish_expiry.assert_called_once_with(
            message='Out-of-zone instances expiry is complete'
        )

    @mock.patch(
        'nectar_tools.expiry.expirer.AllocationInstanceExpirer.finish_expiry',
        new=mock.Mock(),
    )
    @mock.patch(
        'nectar_tools.expiry.expirer.AllocationInstanceExpirer.instances',
        new_callable=mock.PropertyMock,
    )
    def test_should_process_no_instance_with_status(self, mock_instances):
        mock_instances.return_value = []
        project = fakes.FakeProject(
            allocation_id=1, compute_zones='fake', zone_expiry_status='fake'
        )
        ex = expirer.AllocationInstanceExpirer(project)
        self.assertFalse(ex.should_process())
        ex.finish_expiry.assert_called_once_with(
            message='Out-of-zone instances expiry is complete'
        )

    @mock.patch(
        'nectar_tools.expiry.expirer.AllocationInstanceExpirer.finish_expiry',
        new=mock.Mock(),
    )
    @mock.patch(
        'nectar_tools.expiry.expirer.AllocationInstanceExpirer.instances',
        new_callable=mock.PropertyMock,
    )
    def test_should_process_no_instance_with_next_step(self, mock_instances):
        mock_instances.return_value = []
        project = fakes.FakeProject(
            allocation_id=1,
            compute_zones='fake',
            zone_expiry_next_step='fake step',
        )
        ex = expirer.AllocationInstanceExpirer(project)
        self.assertFalse(ex.should_process())
        ex.finish_expiry.assert_called_once_with(
            message='Out-of-zone instances expiry is complete'
        )

    @mock.patch(
        'nectar_tools.expiry.expirer.AllocationInstanceExpirer.finish_expiry',
        new=mock.Mock(),
    )
    @mock.patch(
        'nectar_tools.expiry.expirer.AllocationInstanceExpirer.instances',
        new_callable=mock.PropertyMock,
    )
    def test_should_process_no_instance_with_ticket_id(self, mock_instances):
        mock_instances.return_value = []
        project = fakes.FakeProject(
            allocation_id=1, compute_zones='fake', zone_expiry_ticket_id='134'
        )
        ex = expirer.AllocationInstanceExpirer(project)
        self.assertFalse(ex.should_process())
        ex.finish_expiry.assert_called_once_with(
            message='Out-of-zone instances expiry is complete'
        )

    @mock.patch(
        'nectar_tools.expiry.expirer.AllocationInstanceExpirer.finish_expiry',
        new=mock.Mock(),
    )
    @mock.patch(
        'nectar_tools.expiry.expirer.AllocationInstanceExpirer.instances',
        new_callable=mock.PropertyMock,
    )
    def test_should_process_no_instance_finished_expiry(self, mock_instances):
        mock_instances.return_value = []
        project = fakes.FakeProject(
            allocation_id=1,
            compute_zones='fake',
            zone_expiry_status=expiry_states.ACTIVE,
            zone_expiry_ticket_id='0',
            zone_expiry_next_step='',
        )
        ex = expirer.AllocationInstanceExpirer(project)
        self.assertFalse(ex.should_process())
        ex.finish_expiry.assert_not_called()

    @mock.patch(
        'nectar_tools.expiry.expirer.AllocationInstanceExpirer.finish_expiry',
        new=mock.Mock(),
    )
    @mock.patch(
        'nectar_tools.expiry.expirer.AllocationInstanceExpirer.instances',
        new_callable=mock.PropertyMock,
    )
    def test_should_process_no_instance_archiving(self, mock_instances):
        mock_instances.return_value = []
        project = fakes.FakeProject(
            allocation_id=1,
            compute_zones='fake',
            zone_expiry_status=expiry_states.ARCHIVING,
        )
        ex = expirer.AllocationInstanceExpirer(project)
        self.assertTrue(ex.should_process())
        ex.finish_expiry.assert_not_called()

    @mock.patch(
        'nectar_tools.expiry.expirer.AllocationInstanceExpirer.finish_expiry',
        new=mock.Mock(),
    )
    @mock.patch(
        'nectar_tools.expiry.expirer.AllocationInstanceExpirer.instances',
        new_callable=mock.PropertyMock,
    )
    def test_should_process_no_instance_archived(self, mock_instances):
        mock_instances.return_value = []
        project = fakes.FakeProject(
            allocation_id=1,
            compute_zones='fake',
            zone_expiry_status=expiry_states.ARCHIVED,
        )
        ex = expirer.AllocationInstanceExpirer(project)
        self.assertTrue(ex.should_process())
        ex.finish_expiry.assert_not_called()

    @mock.patch('nectar_tools.utils.get_out_of_zone_instances')
    def test_process_force_delete(self, mock_instances):
        project = fakes.FakeProject(allocation_id=1, zone_expiry_status='fake')
        ex = expirer.AllocationInstanceExpirer(project, force_delete=True)
        with mock.patch.object(ex, 'delete_resources') as mock_delete:
            self.assertTrue(ex.process())
            mock_delete.assert_called_with(force=True)

    @mock.patch('nectar_tools.utils.get_out_of_zone_instances')
    def test_process_active_not_old(self, mock_instances):
        project = fakes.FakeProject(
            allocation_id=1,
            compute_zones='fake',
            zone_expiry_status=expiry_states.ACTIVE,
        )
        ex = expirer.AllocationInstanceExpirer(project)
        ex.allocation.start_date = AFTER
        mock_instances.return_value = ['fake']
        with mock.patch.object(ex, 'send_warning') as mock_send_warning:
            self.assertFalse(ex.process())
            mock_send_warning.assert_not_called()

    @mock.patch('nectar_tools.utils.get_out_of_zone_instances')
    def test_process_active_old_enough(self, mock_instances):
        project = fakes.FakeProject(
            allocation_id=1,
            compute_zones='fake',
            zone_expiry_status=expiry_states.ACTIVE,
        )
        ex = expirer.AllocationInstanceExpirer(project)
        ex.allocation.start_date = BEFORE
        mock_instances.return_value = ['fake']
        with mock.patch.object(ex, 'send_warning') as mock_send_warning:
            self.assertTrue(ex.process())
            mock_send_warning.assert_called_with()

    @mock.patch('nectar_tools.utils.get_out_of_zone_instances')
    def test_process_warning_not_old(self, mock_instances):
        project = fakes.FakeProject(
            allocation_id=1,
            compute_zones='fake',
            zone_expiry_status=expiry_states.WARNING,
            zone_expiry_next_step=AFTER,
        )
        ex = expirer.AllocationInstanceExpirer(project)
        mock_instances.return_value = ['fake']
        with mock.patch.object(ex, 'stop_resource') as mock_stop:
            self.assertFalse(ex.process())
            mock_stop.assert_not_called()

    @mock.patch('nectar_tools.utils.get_out_of_zone_instances')
    def test_process_warning_old_enough(self, mock_instances):
        project = fakes.FakeProject(
            allocation_id=1,
            compute_zones='fake',
            zone_expiry_status=expiry_states.WARNING,
            zone_expiry_next_step=BEFORE,
        )
        ex = expirer.AllocationInstanceExpirer(project)
        mock_instances.return_value = ['fake']
        with mock.patch.object(ex, 'stop_resource') as mock_stop:
            self.assertTrue(ex.process())
            mock_stop.assert_called_with()

    @mock.patch('nectar_tools.utils.get_out_of_zone_instances')
    def test_process_stopped_not_old(self, mock_instances):
        project = fakes.FakeProject(
            allocation_id=1,
            compute_zones='fake',
            zone_expiry_status=expiry_states.STOPPED,
            zone_expiry_next_step=AFTER,
        )
        ex = expirer.AllocationInstanceExpirer(project)
        mock_instances.return_value = ['fake']
        with mock.patch.object(ex, 'archive_project') as (mock_arch_proj):
            self.assertFalse(ex.process())
            mock_arch_proj.assert_not_called()

    @mock.patch('nectar_tools.utils.get_out_of_zone_instances')
    def test_process_stopped_old_enough(self, mock_instances):
        project = fakes.FakeProject(
            allocation_id=1,
            compute_zones='fake',
            zone_expiry_status=expiry_states.STOPPED,
            zone_expiry_next_step=BEFORE,
        )
        ex = expirer.AllocationInstanceExpirer(project)
        mock_instances.return_value = ['fake']
        with mock.patch.object(ex, 'archive_project') as (mock_arch_proj):
            self.assertTrue(ex.process())
            mock_arch_proj.assert_called_with()

    @mock.patch('nectar_tools.utils.get_out_of_zone_instances')
    def test_process_archiving_not_old_archived_success(self, mock_instances):
        project = fakes.FakeProject(
            allocation_id=1,
            compute_zones='fake',
            zone_expiry_status=expiry_states.ARCHIVING,
            zone_expiry_next_step=AFTER,
        )
        ex = expirer.AllocationInstanceExpirer(project)
        mock_instances.return_value = ['fake']
        with test.nested(
            mock.patch.object(ex, 'set_project_archived'),
            mock.patch.object(ex, 'archive_project'),
            mock.patch.object(ex, 'archiver'),
        ) as (mock_set_arch, mock_arch_proj, mock_archiver):
            mock_archiver.is_archive_successful.return_value = True
            self.assertTrue(ex.process())
            mock_arch_proj.assert_not_called()
            mock_set_arch.assert_called_with()

    @mock.patch('nectar_tools.utils.get_out_of_zone_instances')
    def test_process_archiving_not_old_archived_not_success(
        self, mock_instances
    ):
        project = fakes.FakeProject(
            allocation_id=1,
            compute_zones='fake',
            zone_expiry_status=expiry_states.ARCHIVING,
            zone_expiry_next_step=AFTER,
        )
        ex = expirer.AllocationInstanceExpirer(project)
        mock_instances.return_value = ['fake']
        with test.nested(
            mock.patch.object(ex, 'set_project_archived'),
            mock.patch.object(ex, 'archive_project'),
            mock.patch.object(ex, 'archiver'),
        ) as (mock_set_arch, mock_arch_proj, mock_archiver):
            mock_archiver.is_archive_successful.return_value = False
            self.assertTrue(ex.process())
            mock_arch_proj.assert_called_with()
            mock_set_arch.assert_not_called()

    @mock.patch('nectar_tools.utils.get_out_of_zone_instances')
    def test_process_archiving_old_enough(self, mock_instances):
        project = fakes.FakeProject(
            allocation_id=1,
            compute_zones='fake',
            zone_expiry_status=expiry_states.ARCHIVING,
            zone_expiry_next_step=BEFORE,
        )
        ex = expirer.AllocationInstanceExpirer(project)
        mock_instances.return_value = ['fake']
        with mock.patch.object(ex, 'set_project_archived') as mock_set_arch:
            self.assertTrue(ex.process())
            mock_set_arch.assert_called_with()

    @mock.patch('nectar_tools.utils.get_out_of_zone_instances')
    def test_process_archived_not_old(self, mock_instances):
        project = fakes.FakeProject(
            allocation_id=1,
            compute_zones='fake',
            zone_expiry_status=expiry_states.ARCHIVED,
            zone_expiry_next_step=AFTER,
        )
        ex = expirer.AllocationInstanceExpirer(project)
        mock_instances.return_value = ['fake']
        with test.nested(
            mock.patch.object(ex, 'archiver'),
            mock.patch.object(ex, 'delete_resources'),
            mock.patch.object(ex, 'finish_expiry'),
        ) as (mock_archiver, mock_delete, mock_finish):
            self.assertFalse(ex.process())
            mock_delete.assert_not_called()
            mock_archiver.delete_archives.assert_not_called()
            mock_finish.assert_not_called()

    @mock.patch('nectar_tools.utils.get_out_of_zone_instances')
    def test_process_archived_old_enough(self, mock_instances):
        project = fakes.FakeProject(
            allocation_id=1,
            compute_zones='fake',
            zone_expiry_status=expiry_states.ARCHIVED,
            zone_expiry_next_step=BEFORE,
        )
        ex = expirer.AllocationInstanceExpirer(project)
        mock_instances.return_value = ['fake']
        message = 'Out-of-zone instances expiry is complete'
        with test.nested(
            mock.patch.object(ex, 'archiver'),
            mock.patch.object(ex, 'delete_resources'),
            mock.patch.object(ex, 'finish_expiry'),
        ) as (mock_archiver, mock_delete, mock_finish):
            self.assertTrue(ex.process())
            mock_delete.assert_called_with(force=True)
            mock_archiver.delete_archives.assert_called_with()
            mock_finish.assert_called_with(message=message)


@freeze_time("2017-01-01")
@mock.patch('nectar_tools.expiry.notifier.ExpiryNotifier', new=mock.Mock())
@mock.patch('nectar_tools.auth.get_session', new=mock.Mock())
class ImageExpiryTests(test.TestCase):
    def test_get_project(self):
        image = fakes.FakeImage(owner='fake')
        ex = expirer.ImageExpirer(image)
        with mock.patch.object(ex, 'k_client') as mock_k_client:
            ex.get_project()
            mock_k_client.projects.get.assert_called_with('fake')

    def test_project_property(self):
        image = fakes.FakeImage()
        ex = expirer.ImageExpirer(image)
        with mock.patch.object(ex, 'get_project') as mock_project:
            mock_project.return_value = 'fake project'
            self.assertEqual('fake project', ex.project)

    def test_update_image(self):
        image = fakes.FakeImage()
        ex = expirer.ImageExpirer(image)
        today = datetime.datetime.now().strftime(expirer.DATE_FORMAT)
        with mock.patch.object(
            ex.g_client.images, 'update'
        ) as mock_glance_update:
            ex._update_resource(
                nectar_expiry_next_step='2016-02-02',
                nectar_expiry_status='blah',
            )
            mock_glance_update.assert_called_with(
                image.id,
                nectar_expiry_status='blah',
                nectar_expiry_next_step='2016-02-02',
                nectar_expiry_updated_at=today,
            )

    def test_get_notification_context(self):
        image = fakes.FakeImage()
        project = fakes.FakeProject()
        ex = expirer.ImageExpirer(image)

        with test.nested(
            mock.patch.object(ex, '_get_project_managers'),
            mock.patch.object(ex, '_get_project_members'),
            mock.patch.object(ex, 'get_project'),
            mock.patch.object(ex, 'make_next_step_date'),
        ) as (
            mock_get_managers,
            mock_get_members,
            mock_get_project,
            mock_make_date,
        ):
            mock_get_managers.return_value = fakes.MANAGERS
            mock_get_members.return_value = fakes.MEMBERS
            mock_get_project.return_value = project
            mock_make_date.return_value = 'fake'
            expected = {
                'expiry_date': 'fake',
                'image': {
                    'id': 'fake',
                    'name': 'fake_archive',
                    'nectar_expiry_next_step': '',
                    'nectar_expiry_status': '',
                    'nectar_expiry_ticket_id': '0',
                    'owner': 'fake_owner',
                    'protected': False,
                    'status': 'active',
                },
                'managers': [
                    {
                        'email': 'manager1@example.org',
                        'enabled': True,
                        'name': 'manager1@example.org',
                        'id': 'manager1',
                    },
                    {
                        'email': 'manager2@example.org',
                        'enabled': True,
                        'name': 'manager2@example.org',
                        'id': 'manager2',
                    },
                ],
                'members': [
                    {
                        'email': 'member1@example.org',
                        'enabled': True,
                        'name': 'member1@example.org',
                        'id': 'member1',
                    },
                    {
                        'email': 'member2@example.org',
                        'enabled': False,
                        'name': 'member2@example.org',
                        'id': 'member2',
                    },
                    {
                        'email': 'manager1@example.org',
                        'enabled': True,
                        'name': 'manager1@example.org',
                        'id': 'manager1',
                    },
                ],
                'project': {
                    'domain_id': 'default',
                    'enabled': True,
                    'id': 'dummy',
                    'name': 'MyProject',
                },
            }

            actual = ex._get_notification_context()
            mock_get_managers.assert_called_with()
            mock_get_members.assert_called_with()
            mock_make_date.assert_called_with(datetime.datetime(2017, 1, 1))
            self.assertEqual(expected, actual)

    def test_is_ignored_image(self):
        image = fakes.FakeImage(owner='fake')
        ex = expirer.ImageExpirer(image)
        self.assertFalse(ex._is_ignored_image())

        image2 = fakes.FakeImage(owner='11112222')
        ex2 = expirer.ImageExpirer(image2)
        self.assertTrue(ex2._is_ignored_image())
        image3 = fakes.FakeImage(owner='22223333')
        ex3 = expirer.ImageExpirer(image3)
        self.assertTrue(ex3._is_ignored_image())

    def test_has_no_running_instance_no_instance(self):
        image = fakes.FakeImage(owner='fake')
        ex = expirer.ImageExpirer(image)
        with mock.patch.object(ex, 'n_client') as mock_nova:
            mock_nova.servers.list.return_value = []
            actual = ex._has_no_running_instance()
            mock_nova.servers.list.assert_called_with(
                search_opts={'image': image.id, 'all_tenants': True}
            )
            self.assertTrue(actual)

    def test_has_no_running_instance_has_instance(self):
        image = fakes.FakeImage(owner='fake')
        ex = expirer.ImageExpirer(image)
        with mock.patch.object(ex, 'n_client') as mock_nova:
            mock_nova.servers.list.return_value = ['fake']
            actual = ex._has_no_running_instance()
            mock_nova.servers.list.assert_called_with(
                search_opts={'image': image.id, 'all_tenants': True}
            )
            self.assertFalse(actual)

    @freeze_time("2019-01-01")
    def test_has_no_recent_boot_no_instance(self):
        image = fakes.FakeImage(owner='fake')
        ex = expirer.ImageExpirer(image)
        days = 365 * 3
        with mock.patch.object(ex, 'n_client') as mock_nova:
            mock_nova.servers.list.return_value = []
            actual = ex._has_no_recent_boot(days)
            mock_nova.servers.list.assert_called_with(
                search_opts={
                    'image': image.id,
                    'all_tenants': True,
                    'deleted': True,
                    'limit': 1,
                    'changes-since': '2016-01-02T00:00:00',
                }
            )
            self.assertTrue(actual)

    @freeze_time("2019-01-01")
    def test_has_no_recent_boot_has_instance(self):
        image = fakes.FakeImage(owner='fake')
        ex = expirer.ImageExpirer(image)
        days = 365 * 3
        with mock.patch.object(ex, 'n_client') as mock_nova:
            mock_nova.servers.list.return_value = ['fake']
            actual = ex._has_no_recent_boot(days)
            mock_nova.servers.list.assert_called_with(
                search_opts={
                    'image': image.id,
                    'all_tenants': True,
                    'deleted': True,
                    'limit': 1,
                    'changes-since': '2016-01-02T00:00:00',
                }
            )
            self.assertFalse(actual)

    def test_get_warning_date(self):
        image = fakes.FakeImage(owner='fake')
        ex = expirer.ImageExpirer(image)
        image.created_at = '2017-01-01T23:37:45Z'
        expected = datetime.datetime(2020, 1, 1, 23, 37, 45)
        self.assertEqual(expected, ex.get_warning_date())

    def test_should_process_image(self):
        image = fakes.FakeImage(owner='fake')
        ex = expirer.ImageExpirer(image)
        project = fakes.FakeProject()
        with test.nested(
            mock.patch.object(ex, 'ready_for_warning'),
            mock.patch.object(ex, 'get_project'),
            mock.patch.object(ex, '_is_ignored_image'),
            mock.patch.object(ex, '_has_no_running_instance'),
            mock.patch.object(ex, '_has_no_recent_boot'),
        ) as (
            mock_warning,
            mock_project,
            mock_ignored,
            mock_no_running,
            mock_no_booting,
        ):
            mock_warning.return_value = True
            mock_project.return_value = project
            mock_ignored.return_value = False
            mock_no_running.return_value = True
            mock_no_booting.return_value = True
            self.assertTrue(ex.should_process())

    def test_should_process_image_warning_not_ready(self):
        image = fakes.FakeImage(owner='fake')
        ex = expirer.ImageExpirer(image)
        project = fakes.FakeProject()
        with test.nested(
            mock.patch.object(ex, 'ready_for_warning'),
            mock.patch.object(ex, 'get_project'),
            mock.patch.object(ex, '_is_ignored_image'),
            mock.patch.object(ex, '_has_no_running_instance'),
            mock.patch.object(ex, '_has_no_recent_boot'),
        ) as (
            mock_warning,
            mock_project,
            mock_ignored,
            mock_no_running,
            mock_no_booting,
        ):
            mock_warning.return_value = False
            mock_project.return_value = project
            mock_ignored.return_value = False
            mock_no_running.return_value = True
            mock_no_booting.return_value = True

            self.assertFalse(ex.should_process())

    def test_should_process_image_project_disabled(self):
        image = fakes.FakeImage(owner='fake')
        ex = expirer.ImageExpirer(image)
        project = fakes.FakeProject(enabled=False)
        with test.nested(
            mock.patch.object(ex, 'ready_for_warning'),
            mock.patch.object(ex, 'get_project'),
            mock.patch.object(ex, '_is_ignored_image'),
            mock.patch.object(ex, '_has_no_running_instance'),
            mock.patch.object(ex, '_has_no_recent_boot'),
        ) as (
            mock_warning,
            mock_project,
            mock_ignored,
            mock_no_running,
            mock_no_booting,
        ):
            mock_warning.return_value = True
            mock_project.return_value = project
            mock_ignored.return_value = False
            mock_no_running.return_value = True
            mock_no_booting.return_value = True

            self.assertFalse(ex.should_process())

    def test_should_process_image_ignored_image(self):
        image = fakes.FakeImage(owner='fake')
        ex = expirer.ImageExpirer(image)
        project = fakes.FakeProject()
        with test.nested(
            mock.patch.object(ex, 'ready_for_warning'),
            mock.patch.object(ex, 'get_project'),
            mock.patch.object(ex, '_is_ignored_image'),
            mock.patch.object(ex, '_has_no_running_instance'),
            mock.patch.object(ex, '_has_no_recent_boot'),
        ) as (
            mock_warning,
            mock_project,
            mock_ignored,
            mock_no_running,
            mock_no_booting,
        ):
            mock_warning.return_value = True
            mock_project.return_value = project
            mock_ignored.return_value = True
            mock_no_running.return_value = True
            mock_no_booting.return_value = True

            self.assertFalse(ex.should_process())

    def test_should_process_image_has_instance(self):
        image = fakes.FakeImage(owner='fake')
        ex = expirer.ImageExpirer(image)
        project = fakes.FakeProject()
        with test.nested(
            mock.patch.object(ex, 'ready_for_warning'),
            mock.patch.object(ex, 'get_project'),
            mock.patch.object(ex, '_is_ignored_image'),
            mock.patch.object(ex, '_has_no_running_instance'),
            mock.patch.object(ex, '_has_no_recent_boot'),
        ) as (
            mock_warning,
            mock_project,
            mock_ignored,
            mock_no_running,
            mock_no_booting,
        ):
            mock_warning.return_value = True
            mock_project.return_value = project
            mock_ignored.return_value = False
            mock_no_running.return_value = False
            mock_no_booting.return_value = True

            self.assertFalse(ex.should_process())

    def test_should_process_image_has_booting(self):
        image = fakes.FakeImage(owner='fake')
        ex = expirer.ImageExpirer(image)
        project = fakes.FakeProject()
        with test.nested(
            mock.patch.object(ex, 'ready_for_warning'),
            mock.patch.object(ex, 'get_project'),
            mock.patch.object(ex, '_is_ignored_image'),
            mock.patch.object(ex, '_has_no_running_instance'),
            mock.patch.object(ex, '_has_no_recent_boot'),
        ) as (
            mock_warning,
            mock_project,
            mock_ignored,
            mock_no_running,
            mock_no_booting,
        ):
            mock_warning.return_value = True
            mock_project.return_value = project
            mock_ignored.return_value = False
            mock_no_running.return_value = True
            mock_no_booting.return_value = False

            self.assertFalse(ex.should_process())

    def test_process_force_delete(self):
        image = fakes.FakeImage(owner='fake')
        ex = expirer.ImageExpirer(image, force_delete=True)
        with mock.patch.object(ex, 'delete_resources') as mock_delete:
            self.assertTrue(ex.process())
            mock_delete.assert_called_with(force=True)

    def test_process_should_not_process(self):
        image = fakes.FakeImage(owner='fake')
        ex = expirer.ImageExpirer(image)
        with test.nested(
            mock.patch.object(ex, 'should_process'),
            mock.patch.object(ex, 'finish_expiry'),
        ) as (mock_should_process, mock_finish):
            mock_should_process.return_value = False
            self.assertFalse(ex.process())
            mock_finish.assert_not_called()

    def test_process_should_not_process_finish_expiry(self):
        image = fakes.FakeImage(
            owner='fake',
            os_hidden=False,
            nectar_expiry_status=expiry_states.WARNING,
        )
        ex = expirer.ImageExpirer(image)
        with test.nested(
            mock.patch.object(ex, 'should_process'),
            mock.patch.object(ex, 'finish_expiry'),
        ) as (mock_should_process, mock_finish):
            mock_should_process.return_value = False
            self.assertFalse(ex.process())
            mock_finish.assert_called_with(
                'Reset status, expiry work flow is complete'
            )

    def test_process_should_not_process_unhide_image_finish_expiry(self):
        image = fakes.FakeImage(
            owner='fake',
            os_hidden=True,
            nectar_expiry_status=expiry_states.WARNING,
        )
        ex = expirer.ImageExpirer(image)
        with test.nested(
            mock.patch.object(ex, 'should_process'),
            mock.patch.object(ex.archiver, 'start_resources'),
            mock.patch.object(ex, 'finish_expiry'),
        ) as (mock_should_process, mock_start, mock_finish):
            mock_should_process.return_value = False
            self.assertFalse(ex.process())
            mock_start.assert_called_with()
            mock_finish.assert_called_with(
                'Reset status, expiry work flow is complete'
            )

    @mock.patch('nectar_tools.expiry.expirer.ImageExpirer.should_process')
    def test_process_active_send_warning(self, mock_should_process):
        mock_should_process.return_value = True
        image = fakes.FakeImage(owner='fake')
        ex = expirer.ImageExpirer(image)
        with mock.patch.object(ex, 'send_warning') as mock_send_warning:
            self.assertTrue(ex.process())
            mock_send_warning.assert_called_with()

    @freeze_time("2018-12-11")
    @mock.patch('nectar_tools.expiry.expirer.ImageExpirer.should_process')
    def test_process_warning_not_at_next_step(self, mock_should_process):
        mock_should_process.return_value = True
        image = fakes.FakeImage(
            owner='fake',
            nectar_expiry_status=expiry_states.WARNING,
            nectar_expiry_next_step='2018-12-12',
        )
        ex = expirer.ImageExpirer(image)
        with mock.patch.object(ex, 'stop_resource') as mock_stop:
            self.assertFalse(ex.process())
            mock_stop.assert_not_called()

    @freeze_time("2018-12-13")
    @mock.patch('nectar_tools.expiry.expirer.ImageExpirer.should_process')
    def test_process_warning_at_next_step(self, mock_should_process):
        mock_should_process.return_value = True
        image = fakes.FakeImage(
            owner='fake',
            nectar_expiry_status=expiry_states.WARNING,
            nectar_expiry_next_step='2018-12-12',
        )
        ex = expirer.ImageExpirer(image)
        with mock.patch.object(ex, 'stop_resource') as mock_stop:
            self.assertTrue(ex.process())
            mock_stop.assert_called_with()

    @mock.patch('nectar_tools.expiry.expirer.ImageExpirer.should_process')
    def test_process_stopped_not_hidden_image(self, mock_should_process):
        mock_should_process.return_value = True
        image = fakes.FakeImage(
            owner='fake',
            os_hidden=False,
            nectar_expiry_status=expiry_states.STOPPED,
        )
        ex = expirer.ImageExpirer(image)
        with mock.patch.object(ex.archiver, 'stop_resources') as mock_stop:
            self.assertTrue(ex.process())
            mock_stop.assert_called_with()

    @freeze_time("2019-01-01")
    @mock.patch('nectar_tools.expiry.expirer.ImageExpirer.should_process')
    def test_process_stopped_not_at_next_step(self, mock_should_process):
        mock_should_process.return_value = True
        image = fakes.FakeImage(
            owner='fake',
            os_hidden=True,
            nectar_expiry_status=expiry_states.STOPPED,
            nectar_expiry_next_step='2019-01-02',
        )
        ex = expirer.ImageExpirer(image)
        with test.nested(
            mock.patch.object(ex, 'delete_resources'),
            mock.patch.object(ex, 'finish_expiry'),
        ) as (mock_delete, mock_finish):
            self.assertFalse(ex.process())
            mock_delete.assert_not_called()
            mock_finish.assert_not_called()

    @freeze_time("2019-01-03")
    @mock.patch('nectar_tools.expiry.expirer.ImageExpirer.should_process')
    def test_process_stopped_at_next_step(self, mock_should_process):
        mock_should_process.return_value = True
        image = fakes.FakeImage(
            owner='fake',
            os_hidden=True,
            nectar_expiry_status=expiry_states.STOPPED,
            nectar_expiry_next_step='2019-01-02',
        )
        ex = expirer.ImageExpirer(image)
        with test.nested(
            mock.patch.object(ex, 'delete_resources'),
            mock.patch.object(ex, 'finish_expiry'),
        ) as (mock_delete, mock_finish):
            self.assertTrue(ex.process())
            mock_delete.assert_called_with(force=True)
            mock_finish.assert_called_with()

    @mock.patch('nectar_tools.expiry.expirer.ImageExpirer.should_process')
    def test_process_unspecified_status(self, mock_should_process):
        mock_should_process.return_value = True
        image = fakes.FakeImage(
            owner='fake', nectar_expiry_status='unspecified'
        )
        ex = expirer.ImageExpirer(image)
        self.assertFalse(ex.process())
