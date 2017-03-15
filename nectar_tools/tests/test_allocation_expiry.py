import datetime
from unittest import mock

from nectar_tools.expiry import exceptions
from nectar_tools.expiry import expirer
from nectar_tools.expiry import expiry_states

from nectar_tools.expiry.expirer import base

from nectar_tools import test


from nectar_tools.tests import fakes

NOW = datetime.datetime(2017, 1, 1)

BEFORE = '2016-01-01'
AFTER = '2018-01-01'


@mock.patch('nectar_tools.expiry.notifier.FreshDeskNotifier', new=mock.Mock())
@mock.patch('nectar_tools.expiry.allocations.NectarAllocationSession',
       return_value=fakes.FakeAllocationSession(fakes.ALLOCATIONS))
@mock.patch('nectar_tools.auth.get_session', new=mock.Mock())
class AllocationExpiryTests(test.TestCase):

    def test_process_no_allocation(self, mock_allocation_session):
        project = fakes.FakeProject('no-allocation')
        ex = expirer.AllocationExpirer(project, now=NOW)
        self.assertRaises(exceptions.AllocationDoesNotExist, ex.process)

    def test_process_active(self, mock_allocation_session):
        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project, now=NOW)
        ex.process()

    def test_process_send_warning(self, mock_allocation_session):
        project = fakes.FakeProject('warning1')
        ex = expirer.AllocationExpirer(project, now=NOW)

        with mock.patch.object(ex, 'send_warning') as mock_send_warning:
            # Warning with long project, one month out
            ex.process()
            mock_send_warning.assert_called_with()
            mock_send_warning.reset_mock()

            # Warning with short project < 1 month out
            project = fakes.FakeProject('warning2')
            ex.project = project
            ex.process()
            mock_send_warning.assert_called_with()
            mock_send_warning.reset_mock()

            # Warningready but  project extension in
            project = fakes.FakeProject('warning3')
            ex.project = project
            ex.process()
            mock_send_warning.assert_not_called()

    def test_process_warning(self, mock_allocation_session):
        project = fakes.FakeProject(expiry_status=expiry_states.WARNING,
                                    expiry_next_step=BEFORE)
        ex = expirer.AllocationExpirer(project, now=NOW)

        with mock.patch.object(ex, 'restrict_project') as mock_restrict:
            ex.process()
            mock_restrict.assert_called_with()

    def test_process_restricted(self, mock_allocation_session):
        project = fakes.FakeProject(expiry_status=expiry_states.RESTRICTED,
                                    expiry_next_step=BEFORE)
        ex = expirer.AllocationExpirer(project, now=NOW)

        with mock.patch.object(ex, 'stop_project') as mock_stop_project:
            ex.process()
            mock_stop_project.assert_called_with()

    def test_process_stopped(self, mock_allocation_session):
        project = fakes.FakeProject(expiry_status=expiry_states.STOPPED,
                                    expiry_next_step=BEFORE)
        ex = expirer.AllocationExpirer(project, now=NOW)

        with test.nested(
            mock.patch.object(ex, '_update_project'),
            mock.patch.object(ex, 'archive_project'),
        ) as (mock_update_project, mock_archive_project):
            ex.process()
            mock_archive_project.assert_called_with()
            expiry_next_step = (NOW + datetime.timedelta(days=90)).strftime(
                base.DATE_FORMAT)
            mock_update_project.assert_called_with(
                expiry_status=expiry_states.ARCHIVING,
                expiry_next_step=expiry_next_step)

    def test_process_archiving(self, mock_allocation_session):
        project = fakes.FakeProject(expiry_status=expiry_states.ARCHIVING,
                                    expiry_next_step=AFTER)
        ex = expirer.AllocationExpirer(project, now=NOW)

        with mock.patch.object(ex, 'check_archiving_status') as mock_check:
            ex.process()
            mock_check.assert_called_with()

    def test_process_archiving_expired(self,
                                       mock_allocation_session):
        project = fakes.FakeProject(expiry_status=expiry_states.ARCHIVING,
                                    expiry_next_step=BEFORE)
        ex = expirer.AllocationExpirer(project, now=NOW)

        with mock.patch.object(ex, '_update_project') as mock_update:
            ex.process()
            mock_update.assert_called_with(
                expiry_status=expiry_states.ARCHIVED)

    def test_process_archived(self, mock_allocation_session):
        project = fakes.FakeProject(expiry_status=expiry_states.ARCHIVED,
                                    expiry_next_step=BEFORE)
        ex = expirer.AllocationExpirer(project, now=NOW)

        with mock.patch.object(ex, 'delete_project') as mock_delete:
            ex.process()
            mock_delete.assert_called_with()

    def test_process_archived_not_expiry_next_step(self,
                                            mock_allocation_session):
        project = fakes.FakeProject(expiry_status=expiry_states.ARCHIVED,
                                    expiry_next_step=AFTER)
        ex = expirer.AllocationExpirer(project, now=NOW)

        with mock.patch.object(ex, 'delete_resources') as mock_delete:
            ex.process()
            mock_delete.assert_called_with()

    def test_update_project(self, mock_allocation_session):
        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project, now=NOW)
        with mock.patch.object(
            ex.k_client.projects, 'update') as mock_keystone_update:
            ex._update_project(expiry_next_step='2016-02-02',
                               expiry_status='blah')
            mock_keystone_update.assert_called_with(
                project.id, expiry_status='blah',
                expiry_next_step='2016-02-02')

    def test_send_warning(self, mock_allocation_session):
        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project, now=NOW)
        one_month = (NOW + datetime.timedelta(days=30)).strftime(
            base.DATE_FORMAT)
        with mock.patch.object(ex, '_update_project') as mock_update_project:
            ex.send_warning()
            mock_update_project.assert_called_with(
                expiry_next_step=one_month,
                expiry_status=expiry_states.WARNING)

    def test_restrict_project(self, mock_allocation_session):
        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project, now=NOW)
        one_month = (NOW + datetime.timedelta(days=30)).strftime(
            base.DATE_FORMAT)

        with test.nested(
            mock.patch.object(ex, '_update_project'),
            mock.patch.object(ex, 'nova_archiver'),
            mock.patch.object(ex, 'cinder_archiver'),
        ) as (mock_update_project, mock_nova, mock_cinder):

            ex.restrict_project()
            mock_update_project.assert_called_with(expiry_next_step=one_month,
                                        expiry_status=expiry_states.RESTRICTED)

            mock_nova.zero_quota.assert_called_once_with()
            mock_cinder.zero_quota.assert_called_once_with()

    def test_stop_project(self, mock_allocation_session):
        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project, now=NOW)
        one_month = (NOW + datetime.timedelta(days=30)).strftime(
            base.DATE_FORMAT)

        with test.nested(
            mock.patch.object(ex, '_update_project'),
            mock.patch.object(ex, 'nova_archiver'),
        ) as (mock_update_project, mock_archiver):

            ex.stop_project()
            mock_update_project.assert_called_with(
                expiry_next_step=one_month,
                expiry_status=expiry_states.STOPPED)

            mock_archiver.stop_resources.assert_called_once_with()

    def test_archive_project(self, mock_allocation_session):
        project = fakes.FakeProject(expiry_status=expiry_states.STOPPED)
        ex = expirer.AllocationExpirer(project, now=NOW)

        with mock.patch.object(ex, 'nova_archiver') as mock_archiver:
            ex.archive_project()
            mock_archiver.archive_resources.assert_called_once_with()

    def test_check_archiving_status_success(self,
                                            mock_allocation_session):
        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project, now=NOW)

        with test.nested(
            mock.patch.object(ex, '_update_project'),
            mock.patch.object(ex, 'nova_archiver'),
        ) as (mock_update_project, mock_archiver):
            mock_archiver.is_archive_successful.return_value = True
            ex.check_archiving_status()
            mock_archiver.is_archive_successful.assert_called_once_with()
            mock_update_project.assert_called_with(
                expiry_status=expiry_states.ARCHIVED)

    def test_check_archiving_status_nagative(self,
                                             mock_allocation_session):
        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project, now=NOW)

        with test.nested(
            mock.patch.object(ex, '_update_project'),
            mock.patch.object(ex, 'nova_archiver'),
            mock.patch.object(ex, 'archive_project')
        ) as (mock_update_project, mock_archiver, mock_archive):
            mock_archiver.is_archive_successful.return_value = False
            ex.check_archiving_status()
            mock_archiver.is_archive_successful.assert_called_once_with()
            mock_update_project.assert_not_called()
            mock_archive.assert_called_with()

    def test_delete_project(self, mock_allocation_session):
        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project, now=NOW)

        with test.nested(
            mock.patch.object(ex, '_update_project'),
            mock.patch.object(ex, 'nova_archiver'),
        ) as (mock_update_project, mock_archiver):

            ex.delete_project()
            mock_archiver.delete_resources.assert_called_once_with(force=True)
            mock_archiver.delete_archives.assert_called_once_with()
            mock_update_project.assert_called_with(
                expiry_status=expiry_states.DELETED)

    def test_delete_resources(self, mock_allocation_session):
        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project, now=NOW)
        with mock.patch.object(ex, 'nova_archiver') as mock_archiver:
            ex.delete_resources()
            mock_archiver.delete_resources.assert_called_with()
