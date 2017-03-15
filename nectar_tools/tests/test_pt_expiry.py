
import datetime
from dateutil.relativedelta import relativedelta
import testtools
from unittest import mock

from nectar_tools import test
from nectar_tools import config
from nectar_tools.expiry import expirer
from nectar_tools.expiry import exceptions
from nectar_tools.expiry.expirer import base
from nectar_tools.expiry.expirer import pt

from nectar_tools.tests import fakes


CONF = config.CONFIG
USAGE_LIMIT_HOURS = pt.USAGE_LIMIT_HOURS
CPULimit = pt.CPULimit


NOW = datetime.datetime(2017, 1, 1)


class FakeProject(object):

    def __init__(self, project_id='dummy', name='pt-123',
                 owner=mock.Mock(email='fake@fake.com', enabled=True),
                 **kwargs):
        for k,v in kwargs.items():
            setattr(self, k, v)
        self.id = project_id
        self.name = name
        self.owner = owner


@mock.patch('nectar_tools.auth.get_session')
class PTExpiryTests(test.TestCase):

    def test_should_process_project(self, mock_session):
        project = FakeProject()
        ex = expirer.PTExpirer(project, now=NOW)
        should = ex.should_process_project()
        self.assertTrue(should)
    
    def test_should_process_project_admin(self, mock_session):
        project = FakeProject(status='admin')
        ex = expirer.PTExpirer(project, now=NOW)
        should = ex.should_process_project()
        self.assertFalse(should)

    def test_should_process_project_no_owner(self, mock_session):
        project = FakeProject(owner=None)
        ex = expirer.PTExpirer(project, now=NOW)
        should = ex.should_process_project()
        self.assertFalse(should)

    def test_should_process_project_non_pt(self, mock_session):
        project = FakeProject(name='MeritAllocation')
        ex = expirer.PTExpirer(project, now=NOW)
        should = ex.should_process_project()
        self.assertFalse(should)

    def test_project_at_next_step(self, mock_session):
        project = FakeProject()
        ex = expirer.PTExpirer(project, now=NOW)
        with mock.patch.object(ex, 'get_next_step_date') as mock_next_step:
            mock_next_step.return_value = datetime.datetime(2016, 1, 1)
            self.assertTrue(ex.project_at_next_step_date())

    def test_project_not_at_next_step(self, mock_session):
        project = FakeProject()
        ex = expirer.PTExpirer(project, now=NOW)
        with mock.patch.object(ex, 'get_next_step_date') as mock_next_step:
            mock_next_step.return_value = datetime.datetime(2018, 1, 1)
            self.assertFalse(ex.project_at_next_step_date())
            mock_next_step.reset_mock()
            mock_next_step.return_value = None
            self.assertFalse(ex.project_at_next_step_date())

    def test_get_next_step_date(self, mock_session):
        project = FakeProject(next_step='2017-01-01')
        ex = expirer.PTExpirer(project, now=NOW)
        expected = datetime.datetime(2017, 1, 1)
        with mock.patch.object(ex, '_update_project') as mock_update_project:
            actual = ex.get_next_step_date()
            self.assertEqual(expected, actual)
            mock_update_project.assert_not_called()

    def test_get_next_step_date_legacy(self, mock_session):
        project = FakeProject(expires='2017-01-01')
        ex = expirer.PTExpirer(project, now=NOW)
        expected = datetime.datetime(2017, 1, 1)
        with mock.patch.object(ex, '_update_project') as mock_update_project:
            actual = ex.get_next_step_date()
            self.assertEqual(expected, actual)
            mock_update_project.assert_called_with(next_step='2017-01-01',
                                                   expires='')

    def test_get_next_step_date_none(self, mock_session):
        project = FakeProject()
        ex = expirer.PTExpirer(project, now=NOW)
        with mock.patch.object(ex, '_update_project') as mock_update_project:
            actual = ex.get_next_step_date()
            self.assertIsNone(actual)
            mock_update_project.assert_not_called()

    def test_get_status(self, mock_session):
        expected = 'archived'
        project = FakeProject(expiry_status=expected)
        ex = expirer.PTExpirer(project, now=NOW)
        with mock.patch.object(ex, '_update_project') as mock_update_project:
            actual = ex.get_status()
            self.assertEqual(expected, actual)
            mock_update_project.assert_not_called()

    def test_get_status_legacy(self, mock_session):
        expected = 'archived'
        project = FakeProject(status=expected)
        ex = expirer.PTExpirer(project, now=NOW)
        with mock.patch.object(ex, '_update_project') as mock_update_project:
            actual = ex.get_status()
            self.assertEqual(expected, actual)
            mock_update_project.assert_called_with(expiry_status=expected,
                                                   status='')

    def test_get_status_none(self, mock_session):
        project = FakeProject()
        ex = expirer.PTExpirer(project, now=NOW)
        with mock.patch.object(ex, '_update_project') as mock_update_project:
            actual = ex.get_status()
            self.assertEqual('OK', actual)
            mock_update_project.assert_not_called()

    def test_get_next_step_date_none(self, mock_session):
        project = FakeProject()
        ex = expirer.PTExpirer(project, now=NOW)
        self.assertIsNone(ex.get_next_step_date())

    def test_get_next_step_date_invalid(self, mock_session):
        project = FakeProject(next_step='bogus_date')
        ex = expirer.PTExpirer(project, now=NOW)
        self.assertIsNone(ex.get_next_step_date())

    def test_process_invalid(self, mock_session):
        project = FakeProject()
        ex = expirer.PTExpirer(project, now=NOW)
        with mock.patch.object(ex, 'should_process_project') as mock_should:
            mock_should.return_value = False
            self.assertRaises(exceptions.InvalidProjectTrial, ex.process)

    def test_process_ok(self, mock_session):
        project = FakeProject()
        ex = expirer.PTExpirer(project, now=NOW)
        with mock.patch.object(ex, 'check_cpu_usage') as mock_limit:
            mock_limit.return_value = CPULimit.UNDER_LIMIT
            notify_method = ex.process()
            self.assertEqual(False, notify_method)

    def test_process_archiving(self, mock_session):
        project = FakeProject(status='archiving')
        ex = expirer.PTExpirer(project, now=NOW)
        with mock.patch.object(ex, 'check_archiving_status') as mock_status:
            ex.process()
            mock_status.assert_called_with()

    def test_process_archived(self, mock_session):
        project = FakeProject(status='archived', next_step='2014-01-01')
        ex = expirer.PTExpirer(project, now=NOW)
        with mock.patch.object(ex, 'delete_resources') as mock_delete:
            ex.process()
            mock_delete.assert_called_with()

    def test_process_archive_error(self, mock_session):
        project = FakeProject(status='archive_error', next_step='2014-01-01')
        ex = expirer.PTExpirer(project, now=NOW)
        with mock.patch.object(ex, 'delete_resources') as mock_delete:
            ex.process()
            mock_delete.assert_called_with()

    def test_process_suspended(self, mock_session):
        project = FakeProject(status='suspended', next_step='2014-01-01')
        ex = expirer.PTExpirer(project, now=NOW)
        with mock.patch.object(ex, 'archive_project') as mock_archive:
            ex.process()
            mock_archive.assert_called_with()

    def _test_check_cpu_usage(self, usage, expect):
        project = FakeProject()
        ex = expirer.PTExpirer(project, now=NOW)
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

    def test_check_cpu_usage_over(self, mock_session):
        self._test_check_cpu_usage(4383, CPULimit.AT_LIMIT)
        self._test_check_cpu_usage(5259, CPULimit.AT_LIMIT)

    def test_check_cpu_usage_over(self, mock_session):
        self._test_check_cpu_usage(5260, CPULimit.OVER_LIMIT)
        self._test_check_cpu_usage(15260, CPULimit.OVER_LIMIT)

    def test_notify(self, mock_session):
        project = FakeProject()
        ex = expirer.PTExpirer(project, now=NOW)
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
        project = FakeProject()
        ex = expirer.PTExpirer(project, now=NOW)
        with test.nested(
            mock.patch.object(ex, '_update_project'),
            mock.patch.object(ex, 'send_email'),
        ) as (mock_update_project, mock_send_mail):
            ex.notify_near_limit()
            mock_send_mail.assert_called_with('first')
            mock_update_project.assert_called_with(expiry_status='quota warning')

    def test_notify_at_limit(self, mock_session):
        project = FakeProject()
        ex = expirer.PTExpirer(project, now=NOW)
        new_expiry = NOW + relativedelta(months=1)
        new_expiry = new_expiry.strftime(base.DATE_FORMAT)
        
        with test.nested(
            mock.patch.object(ex, '_update_project'),
            mock.patch.object(ex, 'send_email'),
            mock.patch.object(ex, 'nova_archiver')
        ) as (mock_update_project, mock_send_mail, mock_archiver):
            ex.notify_at_limit()
            mock_send_mail.assert_called_with('second')
            mock_update_project.assert_called_with(
                expiry_status='pending suspension',
                next_step=new_expiry)
            mock_archiver.zero_quota.assert_called_with()
            
    def test_notify_over_limit(self, mock_session):
        project = FakeProject(expiry_status='pending suspension',
                              next_step='2014-01-01')
        ex = expirer.PTExpirer(project, now=NOW)
        new_expiry = NOW + relativedelta(months=1)
        new_expiry = new_expiry.strftime(base.DATE_FORMAT)
        
        with test.nested(
            mock.patch.object(ex, '_update_project'),
            mock.patch.object(ex, 'send_email'),
            mock.patch.object(ex, 'nova_archiver')
        ) as (mock_update_project, mock_send_mail, mock_archiver):
            ex.notify_over_limit()
            mock_send_mail.assert_called_with('final')
            mock_update_project.assert_called_with(
                expiry_status='suspended',
                next_step=new_expiry)
            mock_archiver.zero_quota.assert_called_with()
            mock_archiver.stop_project.assert_called_with()

    def _test_render_template(self, status):
        project = FakeProject(expires='2016-01-01')
        ex = expirer.PTExpirer(project, now=NOW)
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
        project = FakeProject(expires='2016-01-01')
        ex = expirer.PTExpirer(project, now=NOW)
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
        project = FakeProject(expires='2016-01-01', owner=owner)
        ex = expirer.PTExpirer(project, now=NOW)
        ex.send_email('first')
        mock_smtp.assert_not_called()

