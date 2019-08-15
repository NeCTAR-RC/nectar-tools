import datetime
from dateutil.relativedelta import relativedelta
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


class FakeProjectWithOwner(object):

    def __init__(self, id='dummy', name='pt-123',
                 owner=mock.Mock(email='fake@fake.com', enabled=True),
                 **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        self.id = id
        self.name = name
        self.owner = owner

    def to_dict(self):
        return self.__dict__


@freeze_time("2017-01-01")
@mock.patch('nectar_tools.auth.get_session', new=mock.Mock())
class ExpiryTests(test.TestCase):
    def setUp(self):
        super(ExpiryTests, self).setUp()

    def test_get_project_managers(self):
        project = fakes.FakeProject()
        ex = expirer.Expirer({'project': project},
                             archivers='fake', notifier='fake')
        self.assertIsNone(ex.managers)
        with mock.patch.object(ex, '_get_users_by_role',
                               return_value=fakes.MANAGERS):
            managers = ex._get_project_managers()
            self.assertEqual(fakes.MANAGERS, ex.managers)
            self.assertEqual(fakes.MANAGERS, managers)

    def test_get_project_members(self):
        project = fakes.FakeProject()
        ex = expirer.Expirer({'project': project},
                             archivers='fake', notifier='fake')
        self.assertIsNone(ex.members)
        with mock.patch.object(ex, '_get_users_by_role',
                               return_value=fakes.MEMBERS):
            members = ex._get_project_members()
            self.assertEqual(fakes.MEMBERS, ex.members)
            self.assertEqual(fakes.MEMBERS, members)

    def test_get_users_by_role(self):
        project = fakes.FakeProject()
        ex = expirer.Expirer({'project': project},
                             archivers='fake', notifier='fake')
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

        with mock.patch.object(ex, 'k_client') as mock_keystone:
            mock_keystone.role_assignments.list.return_value = role_assignments
            mock_keystone.users.get.side_effect = user_side_effect
            users = ex._get_users_by_role('fakerole')
            mock_keystone.role_assignments.list.assert_called_with(
                project=project, role=role)
            mock_keystone.users.get.assert_has_calls([mock.call('fakeuser1'),
                                                      mock.call('fakeuser2')])
            self.assertEqual(['fakeuser1', 'fakeuser2'], [x.id for x in users])

    def test_delete_resources(self):
        project = fakes.FakeProject()
        ex = expirer.Expirer({'project': project},
                             archivers='fake', notifier='fake')
        with mock.patch.object(ex, 'archiver') as mock_archiver:
            ex.delete_resources()
            mock_archiver.delete_resources.assert_called_with()

    def test_send_notification(self):
        project = fakes.FakeProject()
        ex = expirer.Expirer({'project': project},
                             archivers='fake', notifier='fake')
        with test.nested(
            mock.patch.object(ex, 'notifier'),
            mock.patch.object(ex, '_get_notification_context',
                              return_value={'foo': 'bar'}),
            mock.patch.object(ex, '_get_recipients',
                              return_value=('owner@fake.org',
                                            ['manager1@fake.org']))
        ) as (mock_notifier, mock_context, mock_recipients):
            expected_context = {'foo': 'bar', 'foo2': 'bar2'}
            ex._send_notification('fakestage', {'foo2': 'bar2'})
            mock_notifier.send_message.assert_called_with(
                'fakestage', 'owner@fake.org', extra_context=expected_context,
                extra_recipients=['manager1@fake.org'])

    @mock.patch('nectar_tools.expiry.expirer.oslo_messaging')
    def test_send_event(self, mock_oslo_messaging):
        mock_notifier = mock.Mock()
        mock_oslo_messaging.Notifier.return_value = mock_notifier
        project = fakes.FakeProject()
        ex = expirer.Expirer({'project': project},
                             archivers='fake', notifier='fake')
        ex._send_event('foo', 'bar')
        mock_notifier.audit.assert_called_once_with(mock.ANY, 'foo', 'bar')

    def test_get_status(self):
        expected = 'archived'
        project = fakes.FakeProject(expiry_status=expected)
        actual = expirer.Expirer.get_status(project)
        self.assertEqual(expected, actual)

    def test_get_status_none(self):
        project = fakes.FakeProject()
        actual = expirer.Expirer.get_status(project)
        self.assertEqual('active', actual)

    def test_get_next_step_date(self):
        project = fakes.FakeProject(expiry_next_step='2017-01-01')
        expected = datetime.datetime(2017, 1, 1)
        actual = expirer.Expirer.get_next_step_date(project)
        self.assertEqual(expected, actual)

    def test_get_next_step_date_none(self):
        project = fakes.FakeProject()
        actual = expirer.Expirer.get_next_step_date(project)
        self.assertIsNone(actual)

    def test_at_next_step(self):
        project = fakes.FakeProject()
        with mock.patch(
            'nectar_tools.expiry.expirer.Expirer.get_next_step_date'
        ) as mock_next:
            mock_next.return_value = datetime.datetime(2016, 1, 1)
            self.assertTrue(expirer.Expirer.at_next_step(project))

    def test_at_next_step_negative(self):
        project = fakes.FakeProject()
        with mock.patch(
            'nectar_tools.expiry.expirer.Expirer.get_next_step_date'
        ) as mock_next:
            mock_next.return_value = datetime.datetime(2018, 1, 1)
            self.assertFalse(expirer.Expirer.at_next_step(project))
            mock_next.reset_mock()
            mock_next.return_value = None
            self.assertTrue(expirer.Expirer.at_next_step(project))

    def test_make_next_step_date_feb_1(self):
        now = datetime.datetime(2018, 2, 1)
        assert expirer.Expirer.make_next_step_date(now) == '2018-02-15'

    def test_make_next_step_date_feb_1_two_more_weeks(self):
        now = datetime.datetime(2018, 2, 1)
        assert expirer.Expirer.make_next_step_date(now, 2) == '2018-03-01'

    def test_make_next_step_date_dec_14(self):
        now = datetime.datetime(2018, 12, 14)
        assert expirer.Expirer.make_next_step_date(now) == '2018-12-28'

    def test_make_next_step_date_dec_15(self):
        now = datetime.datetime(2018, 12, 15)
        assert expirer.Expirer.make_next_step_date(now) == '2019-01-14'

    def test_make_next_step_date_jan_31(self):
        now = datetime.datetime(2019, 1, 31)
        assert expirer.Expirer.make_next_step_date(now) == '2019-03-02'


@freeze_time("2017-01-01")
@mock.patch('nectar_tools.auth.get_session', new=mock.Mock())
class ProjectExpirerTests(test.TestCase):
    def setUp(self):
        super(ProjectExpirerTests, self).setUp()

    def test_update_project(self):
        project = fakes.FakeProject()
        ex = expirer.ProjectExpirer(project, archivers='fake', notifier='fake')
        today = datetime.datetime.now().strftime(expirer.DATE_FORMAT)
        with mock.patch.object(
            ex.k_client.projects, 'update') as mock_keystone_update:
            ex._update_project(expiry_next_step='2016-02-02',
                               expiry_status='blah')
            mock_keystone_update.assert_called_with(
                project.id, expiry_status='blah',
                expiry_next_step='2016-02-02',
                expiry_updated_at=today)

    def test_check_archiving_status_success(self):
        project = fakes.FakeProject()
        ex = expirer.ProjectExpirer(project, archivers='fake', notifier='fake')

        with test.nested(
            mock.patch.object(ex, '_update_project'),
            mock.patch.object(ex, 'archiver'),
        ) as (mock_update_project, mock_archiver):
            mock_archiver.is_archive_successful.return_value = True
            ex.check_archiving_status()
            mock_archiver.is_archive_successful.assert_called_once_with()
            mock_update_project.assert_called_with(
                expiry_status=expiry_states.ARCHIVED)

    def test_check_archiving_status_nagative(self):
        project = fakes.FakeProject()
        ex = expirer.ProjectExpirer(project, archivers='fake', notifier='fake')

        with test.nested(
            mock.patch.object(ex, '_update_project'),
            mock.patch.object(ex, 'archiver'),
            mock.patch.object(ex, 'archive_project')
        ) as (mock_update_project, mock_archiver, mock_archive):
            mock_archiver.is_archive_successful.return_value = False
            ex.check_archiving_status()
            mock_archiver.is_archive_successful.assert_called_once_with()
            mock_update_project.assert_not_called()
            mock_archive.assert_called_with()

    def test_archive_project(self):
        project = fakes.FakeProject(expiry_status=expiry_states.STOPPED)
        ex = expirer.ProjectExpirer(project, archivers='fake', notifier='fake')

        with test.nested(
            mock.patch.object(ex, '_update_project'),
            mock.patch.object(ex, 'archiver'),
        ) as (mock_update_project, mock_archiver):
            ex.archive_project()
            mock_archiver.archive_resources.assert_called_once_with()
            expiry_next_step = (datetime.datetime.now()
                                + datetime.timedelta(days=90)).strftime(
                                expirer.DATE_FORMAT)
            mock_update_project.assert_called_with(
                expiry_status=expiry_states.ARCHIVING,
                expiry_next_step=expiry_next_step)

    def test_archive_project_retry(self):
        project = fakes.FakeProject(expiry_status=expiry_states.ARCHIVING)
        ex = expirer.ProjectExpirer(project, archivers='fake', notifier='fake')

        with test.nested(
            mock.patch.object(ex, '_update_project'),
            mock.patch.object(ex, 'archiver'),
        ) as (mock_update_project, mock_archiver):
            ex.archive_project()
            mock_archiver.archive_resources.assert_called_once_with()
            mock_update_project.assert_not_called()

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
        with mock.patch.object(ex, '_update_project') as mock_update:
            ex.set_project_archived()
            mock_update.assert_called_with(
                expiry_status=expiry_states.ARCHIVED)

    def test_delete_project(self):
        project = fakes.FakeProject()
        ex = expirer.ProjectExpirer(project, archivers='fake', notifier='fake')
        today = datetime.datetime.now().strftime(expirer.DATE_FORMAT)
        with test.nested(
                mock.patch.object(ex, '_update_project'),
                mock.patch.object(ex, 'archiver'),
                mock.patch.object(ex, 'notifier'),
                mock.patch.object(ex, 'send_event'),
        ) as (mock_update_project, mock_archiver, mock_notifier, mock_event):

            ex.delete_project()
            mock_archiver.delete_resources.assert_called_once_with(force=True)
            mock_archiver.delete_archives.assert_called_once_with()
            mock_notifier.finish.assert_called_with(message='Project deleted')
            mock_update_project.assert_called_with(
                expiry_status=expiry_states.DELETED,
                expiry_next_step='',
                expiry_deleted_at=today)
            mock_event.assert_called_once_with('delete')


@freeze_time("2017-01-01")
@mock.patch('nectar_tools.expiry.notifier.ExpiryNotifier',
            new=mock.Mock())
@mock.patch('nectarallocationclient.v1.allocations.AllocationManager',
            new=fakes.FakeAllocationManager)
@mock.patch('nectar_tools.auth.get_session', new=mock.Mock())
class AllocationExpiryTests(test.TestCase):

    def test_init(self):
        project = fakes.FakeProject('dummy')
        ex = expirer.AllocationExpirer(project)
        self.assertEqual(fakes.ALLOCATIONS['dummy']['id'], ex.allocation.id)

    def test_init_no_allocation(self):
        project = fakes.FakeProject('no-allocation')
        self.assertRaises(exceptions.AllocationDoesNotExist,
                          expirer.AllocationExpirer, project)

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
                project_id=project.id)
            self.assertEqual(active, output)

    def test_get_allocation_no_allocation(self):
        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project)

        with mock.patch.object(ex, 'a_client') as mock_api:
            mock_api.allocations.get_current.side_effect = \
                allocation_exceptions.AllocationDoesNotExist()

            self.assertRaises(exceptions.AllocationDoesNotExist,
                              ex.get_allocation)

    def test_get_allocation_no_allocation_force(self):
        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project, force_no_allocation=True)

        with mock.patch.object(ex, 'a_client') as mock_api:
            mock_api.allocations.get_current.side_effect = \
                allocation_exceptions.AllocationDoesNotExist()

            output = ex.get_allocation()
            self.assertEqual('NO-ALLOCATION', output.id)

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
                project_id=project.id)
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
                project_id=project.id)
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
        project = fakes.FakeProject(expiry_status=expiry_states.WARNING,
                                    expiry_next_step=BEFORE)
        ex = expirer.AllocationExpirer(project)

        with mock.patch.object(ex, 'restrict_project') as mock_restrict:
            self.assertTrue(ex.process())
            mock_restrict.assert_called_with()

    def test_process_restricted(self):
        project = fakes.FakeProject(expiry_status=expiry_states.RESTRICTED,
                                    expiry_next_step=BEFORE)
        ex = expirer.AllocationExpirer(project)

        with mock.patch.object(ex, 'stop_project') as mock_stop_project:
            self.assertTrue(ex.process())
            mock_stop_project.assert_called_with()

    def test_process_stopped(self):
        project = fakes.FakeProject(expiry_status=expiry_states.STOPPED,
                                    expiry_next_step=BEFORE)
        ex = expirer.AllocationExpirer(project)

        with mock.patch.object(ex, 'archive_project') as mock_archive_project:
            self.assertTrue(ex.process())
            mock_archive_project.assert_called_with()

    def test_process_archiving(self):
        project = fakes.FakeProject(expiry_status=expiry_states.ARCHIVING,
                                    expiry_next_step=AFTER)
        ex = expirer.AllocationExpirer(project)

        with mock.patch.object(ex, 'check_archiving_status') as mock_check:
            self.assertTrue(ex.process())
            mock_check.assert_called_with()

    def test_process_archiving_expired(self):
        project = fakes.FakeProject(expiry_status=expiry_states.ARCHIVING,
                                    expiry_next_step=BEFORE)
        ex = expirer.AllocationExpirer(project)

        with mock.patch.object(ex, 'set_project_archived') as mock_proj_arch:
            self.assertTrue(ex.process())
            mock_proj_arch.assert_called_with()

    def test_process_archived(self):
        project = fakes.FakeProject(expiry_status=expiry_states.ARCHIVED,
                                    expiry_next_step=BEFORE)
        ex = expirer.AllocationExpirer(project)

        with mock.patch.object(ex, 'delete_project') as mock_delete:
            self.assertTrue(ex.process())
            mock_delete.assert_called_with()

    def test_process_archived_not_expiry_next_step(self):
        project = fakes.FakeProject(expiry_status=expiry_states.ARCHIVED,
                                    expiry_next_step=AFTER)
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

    def test_allocation_ready_for_warning(self):
        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project)
        mock_allocations = fakes.FakeAllocationManager()
        ex.allocation = mock_allocations.get_current('active')
        self.assertFalse(ex.allocation_ready_for_warning())

        ex.allocation = mock_allocations.get_current('expired')
        self.assertTrue(ex.allocation_ready_for_warning())

        ex.allocation = mock_allocations.get_current('warning1')
        self.assertTrue(ex.allocation_ready_for_warning())

        ex.allocation = mock_allocations.get_current('warning2')
        self.assertTrue(ex.allocation_ready_for_warning())

    def test_should_process_project(self):
        project = fakes.FakeProject(name='Allocation')
        ex = expirer.AllocationExpirer(project)
        self.assertTrue(ex.should_process_project())

        project = fakes.FakeProject(name='pt-33')
        ex = expirer.AllocationExpirer(project)
        self.assertFalse(ex.should_process_project())

        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project)
        mock_allocations = fakes.FakeAllocationManager()
        ex.allocation = mock_allocations.get_current('active')
        self.assertTrue(ex.should_process_project())

        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project)
        ex.allocation = mock_allocations.get_current('pending1')
        self.assertFalse(ex.should_process_project())

        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project)
        ex.allocation = mock_allocations.get_current('active')

        with mock.patch.object(ex, 'is_ignored_project') as mock_ignore:
            mock_ignore.return_value = True
            self.assertFalse(ex.should_process_project())
            mock_ignore.reset_mock()
            mock_ignore.return_value = False
            self.assertTrue(ex.should_process_project())

    def test_revert_expiry_warning(self):
        project = fakes.FakeProject(expiry_status=expiry_states.WARNING,
                                    expiry_next_step=BEFORE,
                                    expiry_ticket_id='20')
        ex = expirer.AllocationExpirer(project)

        with test.nested(
            mock.patch.object(ex, '_update_project'),
            mock.patch.object(ex, 'archiver'),
        ) as (mock_update_project, mock_archiver):
            ex.revert_expiry()
            mock_update_project.assert_called_once_with(expiry_status='',
                                                        expiry_next_step='',
                                                        expiry_ticket_id=0)
            mock_archiver.reset_quota.assert_not_called()
            mock_archiver.enable_resources.assert_called_once_with()

    def test_revert_expiry_restricted(self):
        project = fakes.FakeProject(expiry_status=expiry_states.RESTRICTED,
                                    expiry_next_step=BEFORE,
                                    expiry_ticket_id='20')
        ex = expirer.AllocationExpirer(project)

        with test.nested(
            mock.patch.object(ex, '_update_project'),
            mock.patch.object(ex, 'archiver'),
        ) as (mock_update_project, mock_archiver):
            ex.revert_expiry()
            mock_update_project.assert_called_once_with(expiry_status='',
                                                        expiry_next_step='',
                                                        expiry_ticket_id=0)
            mock_archiver.reset_quota.assert_called_once_with()
            mock_archiver.enable_resources.assert_called_once_with()

    def test_revert_expiry_stopped(self):
        project = fakes.FakeProject(expiry_status=expiry_states.STOPPED,
                                    expiry_next_step=BEFORE,
                                    expiry_ticket_id='20')
        ex = expirer.AllocationExpirer(project)

        with test.nested(
            mock.patch.object(ex, '_update_project'),
            mock.patch.object(ex, 'archiver'),
        ) as (mock_update_project, mock_archiver):
            ex.revert_expiry()
            mock_update_project.assert_called_once_with(expiry_status='',
                                                        expiry_next_step='',
                                                        expiry_ticket_id=0)
            mock_archiver.reset_quota.assert_called_once_with()
            mock_archiver.enable_resources.assert_called_once_with()

    def test_revert_expiry_renewed(self):
        project = fakes.FakeProject(expiry_status=expiry_states.RENEWED,
                                    expiry_next_step=BEFORE,
                                    expiry_ticket_id='20')
        ex = expirer.AllocationExpirer(project)

        with test.nested(
            mock.patch.object(ex, '_update_project'),
            mock.patch.object(ex, 'archiver'),
        ) as (mock_update_project, mock_archiver):
            ex.revert_expiry()
            mock_update_project.assert_called_once_with(expiry_status='',
                                                        expiry_next_step='',
                                                        expiry_ticket_id=0)
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
            mock.patch.object(ex, '_update_project'),
            mock.patch.object(ex, 'send_event'),
        ) as (mock_notification, mock_update_project, mock_event):
            ex.send_warning()
            mock_update_project.assert_called_with(
                expiry_next_step=next_step_date,
                expiry_status=expiry_states.WARNING)
            extra_context = {'expiry_date': ex.allocation.end_date}
            mock_notification.assert_called_with('first',
                                                 extra_context=extra_context)
            mock_event.assert_called_once_with('warning',
                                               extra_context=extra_context)

    @freeze_time('2018-02-01')
    def test_send_warning_late(self):
        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project)
        mock_allocations = fakes.FakeAllocationManager()
        ex.allocation = mock_allocations.get_current('active')
        next_step_date = '2018-03-03'

        with test.nested(
            mock.patch.object(ex, '_send_notification'),
            mock.patch.object(ex, '_update_project'),
            mock.patch.object(ex, 'send_event'),
        ) as (mock_notification, mock_update_project, mock_event):
            ex.send_warning()
            mock_update_project.assert_called_with(
                expiry_next_step=next_step_date,
                expiry_status=expiry_states.WARNING)
            extra_context = {'expiry_date': ex.allocation.end_date}
            mock_notification.assert_called_with('first',
                                                 extra_context=extra_context)
            mock_event.assert_called_once_with('warning',
                                               extra_context=extra_context)

    def test_send_event(self):
        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project)
        with mock.patch.object(ex, '_send_event') as mock_send:
            ex.send_event('foo', {'uni': 'melb'})
            payload = {'allocation': ex.allocation.to_dict(),
                       'uni': 'melb'}
            mock_send.assert_called_once_with('expiry.allocation.foo', payload)

    def test_send_notification(self):
        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project)
        with test.nested(
            mock.patch.object(ex, 'notifier'),
            mock.patch.object(ex, '_get_notification_context',
                              return_value={'foo': 'bar'}),
            mock.patch.object(ex, '_get_recipients',
                              return_value=('owner@fake.org',
                                            ['manager1@fake.org']))
        ) as (mock_notifier, mock_context, mock_recipients):
            expected_context = {'foo': 'bar', 'foo2': 'bar2'}
            ex._send_notification('fakestage', {'foo2': 'bar2'})
            mock_notifier.send_message.assert_called_with(
                'fakestage', 'owner@fake.org', extra_context=expected_context,
                extra_recipients=['manager1@fake.org'])

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

    def test_restrict_project(self):
        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project)
        one_month = (datetime.datetime.now()
                     + datetime.timedelta(days=30)).strftime(
                         expirer.DATE_FORMAT)

        with test.nested(
            mock.patch.object(ex, '_send_notification'),
            mock.patch.object(ex, '_update_project'),
            mock.patch.object(ex, 'archiver'),
            mock.patch.object(ex, 'send_event'),
        ) as (mock_notification, mock_update_project, mock_archiver,
              mock_event):

            ex.restrict_project()
            mock_update_project.assert_called_with(expiry_next_step=one_month,
                                        expiry_status=expiry_states.RESTRICTED)

            mock_archiver.zero_quota.assert_called_once_with()
            mock_notification.assert_called_with('final')
            mock_event.assert_called_once_with('restrict')

    def test_stop_project(self):
        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project)
        one_month = (datetime.datetime.now()
                     + datetime.timedelta(days=30)).strftime(
                         expirer.DATE_FORMAT)

        with test.nested(
            mock.patch.object(ex, '_update_project'),
            mock.patch.object(ex, 'archiver'),
            mock.patch.object(ex, 'send_event'),
        ) as (mock_update_project, mock_archiver, mock_event):

            ex.stop_project()
            mock_update_project.assert_called_with(
                expiry_next_step=one_month,
                expiry_status=expiry_states.STOPPED)

            mock_archiver.stop_resources.assert_called_once_with()
            mock_event.assert_called_once_with('stop')

    def test_get_recipients(self):
        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project)
        with test.nested(
            mock.patch.object(ex, '_get_project_managers',
                              return_value=fakes.MANAGERS),
            mock.patch.object(ex, '_get_project_members',
                              return_value=fakes.MEMBERS)):
            to, cc = ex._get_recipients()
            self.assertEqual('fake@fake.org', to)
            cc.sort()
            self.assertEqual(['approver@fake.org', 'manager1@example.org',
                              'manager2@example.org', 'member1@example.org'],
                             cc)

    def test_set_project_archived(self):
        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project)

        with test.nested(
            mock.patch.object(ex, '_send_notification'),
            mock.patch('nectar_tools.expiry.expirer.ProjectExpirer.'
                       'set_project_archived'),
            mock.patch.object(ex, 'send_event'),
        ) as (mock_send_notification, mock_parent_set_proj_arch, mock_event):
            ex.set_project_archived()
            mock_parent_set_proj_arch.assert_called_once_with()
            mock_send_notification.assert_called_once_with('archived')
            mock_event.assert_called_once_with('archived')

    def test_delete_project(self):
        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project)

        with test.nested(
            mock.patch.object(ex, 'allocation'),
            mock.patch(
                'nectar_tools.expiry.expirer.ProjectExpirer.delete_project'),
        ) as (mock_allocation, mock_parent_delete):
            ex.delete_project()
            mock_parent_delete.assert_called_once_with()
            mock_allocation.delete.assert_called_once_with()


@freeze_time("2017-01-01")
@mock.patch('nectar_tools.expiry.notifier.ExpiryNotifier',
            new=mock.Mock())
@mock.patch('nectar_tools.auth.get_session')
class PTExpiryTests(test.TestCase):

    def test_should_process_project(self, mock_session):
        project = FakeProjectWithOwner()
        ex = expirer.PTExpirer(project)
        should = ex.should_process_project()
        self.assertTrue(should)

    def test_should_process_project_admin(self, mock_session):
        project = FakeProjectWithOwner(expiry_status='admin')
        ex = expirer.PTExpirer(project)
        should = ex.should_process_project()
        self.assertFalse(should)

    def test_should_process_project_no_owner(self, mock_session):
        project = FakeProjectWithOwner(owner=None)
        ex = expirer.PTExpirer(project)
        should = ex.should_process_project()
        self.assertFalse(should)

    def test_should_process_project_non_pt(self, mock_session):
        project = FakeProjectWithOwner(name='MeritAllocation')
        ex = expirer.PTExpirer(project)
        should = ex.should_process_project()
        self.assertFalse(should)

    def test_process_invalid(self, mock_session):
        project = FakeProjectWithOwner()
        ex = expirer.PTExpirer(project)
        with mock.patch.object(ex, 'should_process_project') as mock_should:
            mock_should.return_value = False
            self.assertRaises(exceptions.InvalidProjectTrial, ex.process)

    def test_process_ok(self, mock_session):
        project = FakeProjectWithOwner()
        ex = expirer.PTExpirer(project)
        with mock.patch.object(ex, 'check_cpu_usage') as mock_limit:
            mock_limit.return_value = CPULimit.UNDER_LIMIT
            notify_method = ex.process()
            self.assertFalse(notify_method)

    def test_process_archiving(self, mock_session):
        project = FakeProjectWithOwner(expiry_status=expiry_states.ARCHIVING,
                                       expiry_next_step=AFTER)
        ex = expirer.PTExpirer(project)
        with mock.patch.object(ex, 'check_archiving_status') as mock_status:
            processed = ex.process()
            mock_status.assert_called_with()
            self.assertTrue(processed)

    def test_process_archiving_expired(self, mock_session):
        project = FakeProjectWithOwner(expiry_status=expiry_states.ARCHIVING,
                                       expiry_next_step=BEFORE)
        ex = expirer.PTExpirer(project)
        with mock.patch.object(ex, '_update_project') as mock_update:
            processed = ex.process()
            mock_update.assert_called_with(
                expiry_status=expiry_states.ARCHIVED)
            self.assertTrue(processed)

    def test_process_archived(self, mock_session):
        project = FakeProjectWithOwner(expiry_status='archived',
                                       expiry_next_step=BEFORE)
        ex = expirer.PTExpirer(project)
        with mock.patch.object(ex, 'delete_project') as mock_delete:
            processed = ex.process()
            mock_delete.assert_called_with()
            self.assertTrue(processed)

    def test_process_archived_not_next_step(self, mock_session):
        project = FakeProjectWithOwner(expiry_status='archived',
                                       expiry_next_step=AFTER)
        ex = expirer.PTExpirer(project)
        with mock.patch.object(ex, 'delete_resources') as mock_delete:
            processed = ex.process()
            mock_delete.assert_called_with()
            self.assertFalse(processed)

    def test_process_archive_error(self, mock_session):
        project = FakeProjectWithOwner(expiry_status='archive error',
                              expiry_next_step=BEFORE)
        ex = expirer.PTExpirer(project)
        with mock.patch.object(ex, 'delete_project') as mock_delete:
            processed = ex.process()
            mock_delete.assert_called_with()
            self.assertTrue(processed)

    def test_process_suspended(self, mock_session):
        project = FakeProjectWithOwner(expiry_status='suspended',
                              expiry_next_step=BEFORE)
        ex = expirer.PTExpirer(project)
        with mock.patch.object(ex, 'archive_project') as mock_archive:
            processed = ex.process()
            mock_archive.assert_called_with()
            self.assertTrue(processed)

    def _test_check_cpu_usage(self, usage, expect):
        project = FakeProjectWithOwner()
        ex = expirer.PTExpirer(project)
        mock_usage = mock.Mock()
        mock_usage.total_vcpus_usage = usage
        with mock.patch.object(ex, 'n_client') as mock_nova:
            mock_nova.usage.get.return_value = mock_usage
            limit = ex.check_cpu_usage()

            self.assertEqual(expect, limit)

    def test_check_cpu_usage_under(self, mock_session):
        self._test_check_cpu_usage(0, CPULimit.UNDER_LIMIT)
        self._test_check_cpu_usage(1, CPULimit.UNDER_LIMIT)
        self._test_check_cpu_usage(3506, CPULimit.UNDER_LIMIT)

    def test_check_cpu_usage_near(self, mock_session):
        self._test_check_cpu_usage(3507, CPULimit.NEAR_LIMIT)
        self._test_check_cpu_usage(4382, CPULimit.NEAR_LIMIT)

    def test_check_cpu_at_over(self, mock_session):
        self._test_check_cpu_usage(4383, CPULimit.AT_LIMIT)
        self._test_check_cpu_usage(5259, CPULimit.AT_LIMIT)

    def test_check_cpu_usage_over(self, mock_session):
        self._test_check_cpu_usage(5260, CPULimit.OVER_LIMIT)
        self._test_check_cpu_usage(15260, CPULimit.OVER_LIMIT)

    def test_check_cpu_usage_none(self, mock_session):
        project = FakeProjectWithOwner()
        ex = expirer.PTExpirer(project)
        mock_usage = mock.Mock()
        mock_usage.total_vcpus_usage = None
        with mock.patch.object(ex, 'n_client') as mock_nova:
            mock_nova.usage.get.return_value = mock_usage
            self.assertRaises(exceptions.NoUsageError, ex.check_cpu_usage)

    def test_notify(self, mock_session):
        project = FakeProjectWithOwner()
        ex = expirer.PTExpirer(project)
        self.assertEqual(False, ex.notify(CPULimit.UNDER_LIMIT))
        with mock.patch.object(ex, 'notify_near_limit') as mock_notify:
            self.assertEqual(mock_notify(), ex.notify(CPULimit.NEAR_LIMIT))
            mock_notify.assert_called_with()
        with mock.patch.object(ex, 'notify_at_limit') as mock_notify:
            self.assertEqual(mock_notify(), ex.notify(CPULimit.AT_LIMIT))
            mock_notify.assert_called_with()
        with mock.patch.object(ex, 'notify_over_limit') as mock_notify:
            self.assertEqual(mock_notify(), ex.notify(CPULimit.OVER_LIMIT))
            mock_notify.assert_called_with()

    def test_notify_near_limit(self, mock_session):
        project = FakeProjectWithOwner()
        ex = expirer.PTExpirer(project)
        with test.nested(
            mock.patch.object(ex, '_update_project'),
            mock.patch.object(ex, '_send_notification'),
            mock.patch.object(ex, 'send_event'),
        ) as (mock_update_project, mock_notification, mock_event):
            ex.notify_near_limit()
            mock_notification.assert_called_with('first')
            mock_event.assert_called_once_with('first-warning')
            next_step = datetime.datetime.now() + relativedelta(days=18)
            next_step = next_step.strftime(expirer.DATE_FORMAT)
            mock_update_project.assert_called_with(
                expiry_status='quota warning',
                expiry_next_step=next_step)

    def test_notify_at_limit(self, mock_session):
        project = FakeProjectWithOwner()
        ex = expirer.PTExpirer(project)
        new_expiry = datetime.datetime.now() + relativedelta(days=30)
        new_expiry = new_expiry.strftime(expirer.DATE_FORMAT)

        with test.nested(
                mock.patch.object(ex, '_update_project'),
                mock.patch.object(ex, '_send_notification'),
                mock.patch.object(ex, 'archiver'),
                mock.patch.object(ex, 'send_event'),
        ) as (mock_update_project, mock_notification, mock_archiver,
              mock_event):
            ex.notify_at_limit()
            mock_notification.assert_called_with('second')
            mock_event.assert_called_once_with('second-warning')
            mock_update_project.assert_called_with(
                expiry_status='pending suspension',
                expiry_next_step=new_expiry)
            mock_archiver.zero_quota.assert_called_with()

    def test_notify_over_limit(self, mock_session):
        project = FakeProjectWithOwner(expiry_status='pending suspension',
                              expiry_next_step='2014-01-01')
        ex = expirer.PTExpirer(project)
        new_expiry = datetime.datetime.now() + relativedelta(days=30)
        new_expiry = new_expiry.strftime(expirer.DATE_FORMAT)

        with test.nested(
                mock.patch.object(ex, '_update_project'),
                mock.patch.object(ex, '_send_notification'),
                mock.patch.object(ex, 'archiver'),
                mock.patch.object(ex, 'send_event'),
        ) as (mock_update_project, mock_notification, mock_archiver,
              mock_event):
            ex.notify_over_limit()
            mock_notification.assert_called_with('final')
            mock_event.assert_called_once_with('suspended')
            mock_update_project.assert_called_with(
                expiry_status='suspended',
                expiry_next_step=new_expiry)
            mock_archiver.zero_quota.assert_called_with()
            mock_archiver.stop_resources.assert_called_with()

    def test_send_event(self, mock_session):
        project = fakes.FakeProject()
        ex = expirer.PTExpirer(project)
        with mock.patch.object(ex, '_send_event') as mock_send:
            ex.send_event('foo', {'uni': 'melb'})
            payload = {'project': project.to_dict(),
                       'uni': 'melb'}
            mock_send.assert_called_once_with('expiry.pt.foo', payload)
