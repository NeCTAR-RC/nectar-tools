import datetime
from dateutil.relativedelta import relativedelta
from freezegun import freeze_time
from unittest import mock

from nectar_tools import config
from nectar_tools import test

from nectar_tools.expiry import exceptions
from nectar_tools.expiry import expirer
from nectar_tools.expiry import expiry_states

from nectar_tools.tests import fakes


CONF = config.CONFIG
USAGE_LIMIT_HOURS = expirer.USAGE_LIMIT_HOURS
CPULimit = expirer.CPULimit
BEFORE = '2016-01-01'
AFTER = '2018-01-01'


class FakeProjectWithOwner(object):

    def __init__(self, project_id='dummy', name='pt-123',
                 owner=mock.Mock(email='fake@fake.com', enabled=True),
                 **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        self.id = project_id
        self.name = name
        self.owner = owner


@freeze_time("2017-01-01")
@mock.patch('nectar_tools.auth.get_session', new=mock.Mock())
class ExpiryTests(test.TestCase):

    def test_update_project(self):
        project = fakes.FakeProject()
        ex = expirer.Expirer(project)
        with mock.patch.object(
            ex.k_client.projects, 'update') as mock_keystone_update:
            ex._update_project(expiry_next_step='2016-02-02',
                               expiry_status='blah')
            mock_keystone_update.assert_called_with(
                project.id, expiry_status='blah',
                expiry_next_step='2016-02-02')

    def test_check_archiving_status_success(self):
        project = fakes.FakeProject()
        ex = expirer.Expirer(project)

        with test.nested(
            mock.patch.object(ex, '_update_project'),
            mock.patch.object(ex, 'nova_archiver'),
        ) as (mock_update_project, mock_archiver):
            mock_archiver.is_archive_successful.return_value = True
            ex.check_archiving_status()
            mock_archiver.is_archive_successful.assert_called_once_with()
            mock_update_project.assert_called_with(
                expiry_status=expiry_states.ARCHIVED)

    def test_check_archiving_status_nagative(self):
        project = fakes.FakeProject()
        ex = expirer.Expirer(project)

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

    def test_archive_project(self):
        project = fakes.FakeProject(expiry_status=expiry_states.STOPPED)
        ex = expirer.Expirer(project)

        with mock.patch.object(ex, 'nova_archiver') as mock_archiver:
            ex.archive_project()
            mock_archiver.archive_resources.assert_called_once_with()

    def test_delete_resources(self):
        project = fakes.FakeProject()
        ex = expirer.Expirer(project)
        with mock.patch.object(ex, 'nova_archiver') as mock_archiver:
            ex.delete_resources()
            mock_archiver.delete_resources.assert_called_with()

    def test_get_status(self):
        expected = 'archived'
        project = FakeProjectWithOwner(expiry_status=expected)
        ex = expirer.Expirer(project)
        with mock.patch.object(ex, '_update_project') as mock_update_project:
            actual = ex.get_status()
            self.assertEqual(expected, actual)
            mock_update_project.assert_not_called()

    def test_get_status_legacy(self):
        expected = 'archived'
        project = FakeProjectWithOwner(status=expected)
        ex = expirer.Expirer(project)
        with mock.patch.object(ex, '_update_project') as mock_update_project:
            actual = ex.get_status()
            self.assertEqual(expected, actual)
            mock_update_project.assert_called_with(expiry_status=expected,
                                                   status='')

    def test_get_status_none(self):
        project = FakeProjectWithOwner()
        ex = expirer.Expirer(project)
        with mock.patch.object(ex, '_update_project') as mock_update_project:
            actual = ex.get_status()
            self.assertEqual('active', actual)
            mock_update_project.assert_not_called()

    def test_get_next_step_date(self):
        project = FakeProjectWithOwner(expiry_next_step='2017-01-01')
        ex = expirer.Expirer(project)
        expected = datetime.datetime(2017, 1, 1)
        with mock.patch.object(ex, '_update_project') as mock_update_project:
            actual = ex.get_next_step_date()
            self.assertEqual(expected, actual)
            mock_update_project.assert_not_called()

    def test_get_next_step_date_legacy(self):
        project = FakeProjectWithOwner(expires='2017-01-01')
        ex = expirer.Expirer(project)
        expected = datetime.datetime(2017, 1, 1)
        with mock.patch.object(ex, '_update_project') as mock_update_project:
            actual = ex.get_next_step_date()
            self.assertEqual(expected, actual)
            mock_update_project.assert_called_with(
                expiry_next_step='2017-01-01', expires='')

    def test_get_next_step_date_none(self):
        project = FakeProjectWithOwner()
        ex = expirer.Expirer(project)
        with mock.patch.object(ex, '_update_project') as mock_update_project:
            actual = ex.get_next_step_date()
            self.assertIsNone(actual)
            mock_update_project.assert_not_called()


@freeze_time("2017-01-01")
@mock.patch('nectar_tools.expiry.notifier.FreshDeskNotifier', new=mock.Mock())
@mock.patch('nectar_tools.expiry.allocations.NectarAllocationSession',
       return_value=fakes.FakeAllocationSession(fakes.ALLOCATIONS))
@mock.patch('nectar_tools.auth.get_session', new=mock.Mock())
class AllocationExpiryTests(test.TestCase):

    def test_process_no_allocation(self, mock_allocation_session):
        project = fakes.FakeProject('no-allocation')
        ex = expirer.AllocationExpirer(project)
        self.assertRaises(exceptions.AllocationDoesNotExist, ex.process)

    def test_process_active(self, mock_allocation_session):
        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project)
        ex.process()

    def test_process_send_warning_long(self, mock_allocation_session):
        project = fakes.FakeProject('warning1')
        ex = expirer.AllocationExpirer(project)

        with mock.patch.object(ex, 'send_warning') as mock_send_warning:
            ex.process()
            mock_send_warning.assert_called_with()

    def test_process_send_warning_short(self, mock_allocation_session):
        project = fakes.FakeProject('warning2')
        ex = expirer.AllocationExpirer(project)

        with mock.patch.object(ex, 'send_warning') as mock_send_warning:
            ex.process()
            mock_send_warning.assert_called_with()
            mock_send_warning.reset_mock()

    def test_process_send_warning_extension(self, mock_allocation_session):
        project = fakes.FakeProject('warning3')
        ex = expirer.AllocationExpirer(project)

        with mock.patch.object(ex, 'send_warning') as mock_send_warning:
            ex.process()
            mock_send_warning.assert_not_called()

    def test_process_warning(self, mock_allocation_session):
        project = fakes.FakeProject(expiry_status=expiry_states.WARNING,
                                    expiry_next_step=BEFORE)
        ex = expirer.AllocationExpirer(project)

        with mock.patch.object(ex, 'restrict_project') as mock_restrict:
            ex.process()
            mock_restrict.assert_called_with()

    def test_process_restricted(self, mock_allocation_session):
        project = fakes.FakeProject(expiry_status=expiry_states.RESTRICTED,
                                    expiry_next_step=BEFORE)
        ex = expirer.AllocationExpirer(project)

        with mock.patch.object(ex, 'stop_project') as mock_stop_project:
            ex.process()
            mock_stop_project.assert_called_with()

    def test_process_stopped(self, mock_allocation_session):
        project = fakes.FakeProject(expiry_status=expiry_states.STOPPED,
                                    expiry_next_step=BEFORE)
        ex = expirer.AllocationExpirer(project)

        with test.nested(
            mock.patch.object(ex, '_update_project'),
            mock.patch.object(ex, 'archive_project'),
        ) as (mock_update_project, mock_archive_project):
            ex.process()
            mock_archive_project.assert_called_with()
            expiry_next_step = (datetime.datetime.now() +
                                datetime.timedelta(days=90)).strftime(
                                    expirer.DATE_FORMAT)
            mock_update_project.assert_called_with(
                expiry_status=expiry_states.ARCHIVING,
                expiry_next_step=expiry_next_step)

    def test_process_archiving(self, mock_allocation_session):
        project = fakes.FakeProject(expiry_status=expiry_states.ARCHIVING,
                                    expiry_next_step=AFTER)
        ex = expirer.AllocationExpirer(project)

        with mock.patch.object(ex, 'check_archiving_status') as mock_check:
            ex.process()
            mock_check.assert_called_with()

    def test_process_archiving_expired(self,
                                       mock_allocation_session):
        project = fakes.FakeProject(expiry_status=expiry_states.ARCHIVING,
                                    expiry_next_step=BEFORE)
        ex = expirer.AllocationExpirer(project)

        with mock.patch.object(ex, '_update_project') as mock_update:
            ex.process()
            mock_update.assert_called_with(
                expiry_status=expiry_states.ARCHIVED)

    def test_process_archived(self, mock_allocation_session):
        project = fakes.FakeProject(expiry_status=expiry_states.ARCHIVED,
                                    expiry_next_step=BEFORE)
        ex = expirer.AllocationExpirer(project)

        with mock.patch.object(ex, 'delete_project') as mock_delete:
            ex.process()
            mock_delete.assert_called_with()

    def test_process_archived_not_expiry_next_step(self,
                                            mock_allocation_session):
        project = fakes.FakeProject(expiry_status=expiry_states.ARCHIVED,
                                    expiry_next_step=AFTER)
        ex = expirer.AllocationExpirer(project)

        with mock.patch.object(ex, 'delete_resources') as mock_delete:
            ex.process()
            mock_delete.assert_called_with()

    def test_send_warning(self, mock_allocation_session):
        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project)
        one_month = (datetime.datetime.now() +
                     datetime.timedelta(days=30)).strftime(expirer.DATE_FORMAT)
        with mock.patch.object(ex, '_update_project') as mock_update_project:
            ex.send_warning()
            mock_update_project.assert_called_with(
                expiry_next_step=one_month,
                expiry_status=expiry_states.WARNING)

    def test_restrict_project(self, mock_allocation_session):
        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project)
        one_month = (datetime.datetime.now() +
                     datetime.timedelta(days=30)).strftime(expirer.DATE_FORMAT)

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
        ex = expirer.AllocationExpirer(project)
        one_month = (datetime.datetime.now() +
                     datetime.timedelta(days=30)).strftime(expirer.DATE_FORMAT)

        with test.nested(
            mock.patch.object(ex, '_update_project'),
            mock.patch.object(ex, 'nova_archiver'),
        ) as (mock_update_project, mock_archiver):

            ex.stop_project()
            mock_update_project.assert_called_with(
                expiry_next_step=one_month,
                expiry_status=expiry_states.STOPPED)

            mock_archiver.stop_resources.assert_called_once_with()

    def test_delete_project(self, mock_allocation_session):
        project = fakes.FakeProject()
        ex = expirer.AllocationExpirer(project)

        with test.nested(
            mock.patch.object(ex, '_update_project'),
            mock.patch.object(ex, 'nova_archiver'),
        ) as (mock_update_project, mock_archiver):

            ex.delete_project()
            mock_archiver.delete_resources.assert_called_once_with(force=True)
            mock_archiver.delete_archives.assert_called_once_with()
            mock_update_project.assert_called_with(
                expiry_status=expiry_states.DELETED)


@freeze_time("2017-01-01")
@mock.patch('nectar_tools.auth.get_session')
class PTExpiryTests(test.TestCase):

    def test_should_process_project(self, mock_session):
        project = FakeProjectWithOwner()
        ex = expirer.PTExpirer(project)
        should = ex.should_process_project()
        self.assertTrue(should)

    def test_should_process_project_admin(self, mock_session):
        project = FakeProjectWithOwner(status='admin')
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

    def test_project_at_next_step(self, mock_session):
        project = FakeProjectWithOwner()
        ex = expirer.PTExpirer(project)
        with mock.patch.object(ex, 'get_next_step_date') as mock_next:
            mock_next.return_value = datetime.datetime(2016, 1, 1)
            self.assertTrue(ex.project_at_next_step_date())

    def test_project_not_at_expiry_next_step(self, mock_session):
        project = FakeProjectWithOwner()
        ex = expirer.PTExpirer(project)
        with mock.patch.object(ex, 'get_next_step_date') as mock_next:
            mock_next.return_value = datetime.datetime(2018, 1, 1)
            self.assertFalse(ex.project_at_next_step_date())
            mock_next.reset_mock()
            mock_next.return_value = None
            self.assertFalse(ex.project_at_next_step_date())

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
            self.assertEqual(False, notify_method)

    def test_process_archiving(self, mock_session):
        project = FakeProjectWithOwner(status='archiving')
        ex = expirer.PTExpirer(project)
        with mock.patch.object(ex, 'check_archiving_status') as mock_status:
            ex.process()
            mock_status.assert_called_with()

    def test_process_archived(self, mock_session):
        project = FakeProjectWithOwner(status='archived', expiry_next_step='2014-01-01')
        ex = expirer.PTExpirer(project)
        with mock.patch.object(ex, 'delete_resources') as mock_delete:
            ex.process()
            mock_delete.assert_called_with()

    def test_process_archive_error(self, mock_session):
        project = FakeProjectWithOwner(status='archive_error',
                              expiry_next_step='2014-01-01')
        ex = expirer.PTExpirer(project)
        with mock.patch.object(ex, 'delete_resources') as mock_delete:
            ex.process()
            mock_delete.assert_called_with()

    def test_process_suspended(self, mock_session):
        project = FakeProjectWithOwner(status='suspended',
                              expiry_next_step='2014-01-01')
        ex = expirer.PTExpirer(project)
        with mock.patch.object(ex, 'archive_project') as mock_archive:
            ex.process()
            mock_archive.assert_called_with()

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
            mock.patch.object(ex, 'send_email'),
        ) as (mock_update_project, mock_send_mail):
            ex.notify_near_limit()
            mock_send_mail.assert_called_with('first')
            mock_update_project.assert_called_with(
                expiry_status='quota warning')

    def test_notify_at_limit(self, mock_session):
        project = FakeProjectWithOwner()
        ex = expirer.PTExpirer(project)
        new_expiry = datetime.datetime.now() + relativedelta(months=1)
        new_expiry = new_expiry.strftime(expirer.DATE_FORMAT)

        with test.nested(
            mock.patch.object(ex, '_update_project'),
            mock.patch.object(ex, 'send_email'),
            mock.patch.object(ex, 'nova_archiver')
        ) as (mock_update_project, mock_send_mail, mock_archiver):
            ex.notify_at_limit()
            mock_send_mail.assert_called_with('second')
            mock_update_project.assert_called_with(
                expiry_status='pending suspension',
                expiry_next_step=new_expiry)
            mock_archiver.zero_quota.assert_called_with()

    def test_notify_over_limit(self, mock_session):
        project = FakeProjectWithOwner(expiry_status='pending suspension',
                              expiry_next_step='2014-01-01')
        ex = expirer.PTExpirer(project)
        new_expiry = datetime.datetime.now() + relativedelta(months=1)
        new_expiry = new_expiry.strftime(expirer.DATE_FORMAT)

        with test.nested(
            mock.patch.object(ex, '_update_project'),
            mock.patch.object(ex, 'send_email'),
            mock.patch.object(ex, 'nova_archiver')
        ) as (mock_update_project, mock_send_mail, mock_archiver):
            ex.notify_over_limit()
            mock_send_mail.assert_called_with('final')
            mock_update_project.assert_called_with(
                expiry_status='suspended',
                expiry_next_step=new_expiry)
            mock_archiver.zero_quota.assert_called_with()
            mock_archiver.stop_project.assert_called_with()

    def _test_render_template(self, status):
        project = FakeProjectWithOwner(expires='2016-01-01')
        ex = expirer.PTExpirer(project)
        template = ex.render_template(status)
        self.assertIn(project.name, template)
        if status == 'second':
            self.assertIn(project.expires, template)

    def test_render_template_first(self, mock_session):
        self._test_render_template('first')

    def test_render_template_second(self, mock_session):
        self._test_render_template('second')

    def test_render_template_final(self, mock_session):
        self._test_render_template('final')

    @mock.patch('email.mime.text.MIMEText', autospec=True)
    @mock.patch('smtplib.SMTP', autospec=True)
    def test_send_email(self, mock_smtp, mock_mime, mock_session):
        project = FakeProjectWithOwner(expires='2016-01-01')
        ex = expirer.PTExpirer(project)
        ex.send_email('first')
        mock_smtp.return_value.sendmail.assert_called_with(
            mock_mime.return_value['From'],
            [project.owner.email],
            mock_mime.return_value.as_string()
        )
        mime_calls = [
            mock.call('From', CONF.expiry.email_from),
            mock.call('To', project.owner.email),
            mock.call('Subject', 'NeCTAR project upcoming expiry for pt-123\n')
        ]
        mock_mime.return_value.__setitem__.assert_has_calls(mime_calls)
        mock_smtp.return_value.quit.assert_called_with()

    @mock.patch('smtplib.SMTP', autospec=True)
    def test_send_email_disabled_owner(self, mock_smtp, mock_session):
        owner = mock.Mock(email='fake@fake.com', enabled=False)
        project = FakeProjectWithOwner(expires='2016-01-01', owner=owner)
        ex = expirer.PTExpirer(project)
        ex.send_email('first')
        mock_smtp.assert_not_called()


