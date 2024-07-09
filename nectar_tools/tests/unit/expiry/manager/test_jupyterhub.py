import datetime
from freezegun import freeze_time
from unittest import mock

from nectar_tools import test

from nectar_tools.expiry import expirer as base_expirer
from nectar_tools.expiry import expiry_states
from nectar_tools.expiry.manager import jupyterhub as expirer

from nectar_tools.tests import fakes


@freeze_time('2024-07-01')
@mock.patch('nectar_tools.expiry.notifier.ExpiryNotifier',
            new=mock.Mock())
@mock.patch('nectar_tools.auth.get_session', new=mock.Mock())
@mock.patch('nectar_tools.auth.get_kube_client', new=mock.Mock())
class JupyterHubVolumeExpiryTests(test.TestCase):

    def setUp(self):
        super().setUp()
        self.username = 'fake@user.com'
        self.annotations = {'hub.jupyter.org/username': self.username}
        self.metadata = fakes.FakeK8sObject(
            name='claim-' + self.username,
            annotations=self.annotations)
        self.pvc = fakes.FakeK8sObject(metadata=self.metadata)

    def test_ready_for_warning_negative(self):
        ex = expirer.JupyterHubVolumeExpirer(self.pvc)
        with mock.patch.object(ex, 'get_last_active_date') as mock_glad:
            mock_glad.return_value = datetime.datetime(2024, 3, 1)
            self.assertFalse(ex.ready_for_warning())

    def test_ready_for_warning(self):
        ex = expirer.JupyterHubVolumeExpirer(self.pvc)
        with mock.patch.object(ex, 'get_last_active_date') as mock_glad:
            mock_glad.return_value = datetime.datetime(2024, 1, 1)
            self.assertTrue(ex.ready_for_warning())

    def test_has_metadata(self):
        ex = expirer.JupyterHubVolumeExpirer(self.pvc)
        self.assertTrue(ex.has_metadata('hub.jupyter.org/username'))
        self.assertFalse(ex.has_metadata('missing_metadata'))

    def test_get_metadata(self):
        annotations = {'foo': 'bar'}
        metadata = fakes.FakeK8sObject(name='fake', annotations=annotations)
        pvc = fakes.FakeK8sObject(metadata=metadata)
        ex = expirer.JupyterHubVolumeExpirer(pvc)
        self.assertEqual('bar', ex.get_metadata('foo'))

    def test_get_metadata_empty_string(self):
        metadata = fakes.FakeK8sObject(name='fake', annotations={})
        pvc = fakes.FakeK8sObject(metadata=metadata)
        ex = expirer.JupyterHubVolumeExpirer(pvc)
        self.assertIsNone(ex.get_metadata('foo'))

    def test_set_metadata(self):
        ex = expirer.JupyterHubVolumeExpirer(self.pvc)
        ex.set_metadata('foo', 'bar')
        self.assertEqual(
            'bar', ex.get_metadata('foo'))

    def test_get_recipients(self):
        ex = expirer.JupyterHubVolumeExpirer(self.pvc)
        expected = (self.username, [])
        actual = ex._get_recipients()
        self.assertEqual(expected, actual)

    def test_update_object(self):
        ex = expirer.JupyterHubVolumeExpirer(self.pvc)
        ex.kube_client = mock.Mock()
        mock_kube_client = ex.kube_client
        ex._update_object(foo='bar')
        (mock_kube_client
             .patch_namespaced_persistent_volume_claim
             .assert_called_once_with(
                 'claim-fake@user.com', 'fake_namespace',
                 body={'metadata': {'annotations': {'foo': 'bar'}}}))

    def test_get_notification_context(self):
        ex = expirer.JupyterHubVolumeExpirer(self.pvc)
        expected = {
            'name': self.username,
            'expiry_date': '2024-07-15',
        }
        actual = ex._get_notification_context()
        self.assertEqual(expected, actual)

    def test_get_status(self):
        ex = expirer.JupyterHubVolumeExpirer(self.pvc)
        expected = expiry_states.ACTIVE
        actual = ex.get_status()
        self.assertEqual(expected, actual)

    def test_get_status_warning(self):
        expected = expiry_states.WARNING
        annotations = {expirer.JupyterHubVolumeExpirer.STATUS_KEY: expected}
        metadata = fakes.FakeK8sObject(name='fake', annotations=annotations)
        pvc = fakes.FakeK8sObject(metadata=metadata)
        ex = expirer.JupyterHubVolumeExpirer(pvc)
        actual = ex.get_status()
        self.assertEqual(expected, actual)

    def test_get_next_step_date(self):
        expected = datetime.datetime(2024, 7, 1)
        ex = expirer.JupyterHubVolumeExpirer(self.pvc)
        with mock.patch.object(ex, 'get_metadata') as mock_get_metadata:
            mock_get_metadata.return_value = '2024-07-01'
            actual = ex.get_next_step_date()
            self.assertEqual(expected, actual)

    def test_get_last_active_date(self):
        ex = expirer.JupyterHubVolumeExpirer(self.pvc)
        with mock.patch.object(ex, '_jupyterhub_api') as mock_jhub_api:
            mock_jhub_api.return_value = fakes.JUPYTERHUB_USER
            expected = datetime.datetime(2024, 6, 1)
            actual = ex.get_last_active_date()
            self.assertEqual(expected, actual)

    def test_get_warning_date(self):
        ex = expirer.JupyterHubVolumeExpirer(self.pvc)
        with mock.patch.object(ex, 'get_last_active_date') as mock_glad:
            mock_glad.return_value = datetime.datetime(2024, 1, 1)
            expected = datetime.datetime(2024, 6, 29)  # 180 days
            actual = ex.get_warning_date()
            self.assertEqual(expected, actual)

    def test_stop_resource(self):
        ex = expirer.JupyterHubVolumeExpirer(self.pvc)
        one_day = (datetime.datetime.now()
                     + datetime.timedelta(days=1)).strftime(
                         base_expirer.DATE_FORMAT)
        with test.nested(
            mock.patch.object(ex, '_update_resource'),
            mock.patch.object(ex, 'send_event'),
            mock.patch.object(ex, '_send_notification'),
        ) as (mock_update_resource, mock_event, mock_notification):
            mock_notification.side_effect = Exception('fake')
            try:
                ex.stop_resource()
            except Exception:
                mock_update_resource.assert_has_calls([
                    mock.call(**{
                        expirer.JupyterHubVolumeExpirer.STATUS_KEY:
                        expiry_states.STOPPED,
                        expirer.JupyterHubVolumeExpirer.NEXT_STEP_KEY:
                        one_day,
                    }),
                    mock.call(**{
                        expirer.JupyterHubVolumeExpirer.STATUS_KEY:
                        None,
                        expirer.JupyterHubVolumeExpirer.NEXT_STEP_KEY:
                        None,
                    }),
                ])

    def test_revert_expiry(self):
        ex = expirer.JupyterHubVolumeExpirer(self.pvc)
        with test.nested(
            mock.patch.object(ex, 'get_status'),
            mock.patch.object(ex, 'finish_expiry'),
        ) as (mock_status, mock_finish):
            mock_status.return_value = expiry_states.WARNING
            ex.revert_expiry()
            mock_finish.assert_called_once()

    def test_should_process(self):
        ex = expirer.JupyterHubVolumeExpirer(self.pvc)
        with test.nested(
            mock.patch.object(ex, 'ready_for_warning'),
            mock.patch.object(ex, 'get_last_active_date'),
            mock.patch.object(ex, 'get_status'),
        ) as (mock_ready, mock_last_active, mock_status):
            mock_ready.return_value = True
            mock_last_active.return_value = datetime.datetime(2024, 1, 1)
            mock_status.return_value = expiry_states.WARNING
            self.assertTrue(ex.should_process())

    def test_should_process_not_ready(self):
        ex = expirer.JupyterHubVolumeExpirer(self.pvc)
        with test.nested(
            mock.patch.object(ex, 'ready_for_warning'),
            mock.patch.object(ex, 'get_last_active_date'),
            mock.patch.object(ex, 'get_status'),
        ) as (mock_ready, mock_last_active, mock_status):
            mock_ready.return_value = False
            mock_last_active.return_value = datetime.datetime(2024, 6, 1)
            self.assertFalse(ex.should_process())

    def test_should_process_revert(self):
        ex = expirer.JupyterHubVolumeExpirer(self.pvc)
        with test.nested(
            mock.patch.object(ex, 'ready_for_warning'),
            mock.patch.object(ex, 'get_last_active_date'),
            mock.patch.object(ex, 'get_status'),
            mock.patch.object(ex, 'revert_expiry'),
        ) as (mock_ready, mock_last_active, mock_status, mock_revert):
            mock_ready.return_value = False
            mock_last_active.return_value = datetime.datetime(2024, 6, 1)
            mock_status.return_value = expiry_states.WARNING
            self.assertFalse(ex.process())
            mock_revert.assert_called_once_with()

    def test_process_force_delete(self):
        ex = expirer.JupyterHubVolumeExpirer(self.pvc, force_delete=True)
        with mock.patch.object(ex, 'delete_resources') as mock_delete:
            self.assertTrue(ex.process())
            mock_delete.assert_called_with(force=True)

    def test_process_should_not_process(self):
        ex = expirer.JupyterHubVolumeExpirer(self.pvc)
        with test.nested(
            mock.patch.object(ex, 'should_process'),
            mock.patch.object(ex, 'stop_resource'),
            mock.patch.object(ex, 'finish_expiry'),
            mock.patch.object(ex, 'delete_resources'),
        ) as (mock_should_process, mock_stop, mock_finish, mock_delete):
            mock_should_process.return_value = False
            self.assertFalse(ex.process())
            mock_stop.assert_not_called()
            mock_finish.assert_not_called()
            mock_delete.assert_not_called()

    def test_process_send_warning(self):
        ex = expirer.JupyterHubVolumeExpirer(self.pvc)
        with test.nested(
            mock.patch.object(ex, 'get_status'),
            mock.patch.object(ex, 'should_process'),
            mock.patch.object(ex, 'send_warning'),
        ) as (mock_status, mock_should_process, mock_warning):
            mock_status.return_value = expiry_states.ACTIVE
            mock_should_process.return_value = True
            self.assertTrue(ex.process())
            mock_warning.assert_called_with()

    def test_process_warning_not_at_next_step(self):
        ex = expirer.JupyterHubVolumeExpirer(self.pvc)
        with test.nested(
            mock.patch.object(ex, 'get_status'),
            mock.patch.object(ex, 'should_process'),
            mock.patch.object(ex, 'at_next_step'),
            mock.patch.object(ex, 'stop_resource'),
        ) as (mock_status, mock_should_process, mock_next_step, mock_stop):
            mock_status.return_value = expiry_states.WARNING
            mock_should_process.return_value = True
            mock_next_step.return_value = False
            self.assertFalse(ex.process())
            mock_stop.assert_not_called()

    def test_process_warning_at_next_step(self):
        ex = expirer.JupyterHubVolumeExpirer(self.pvc)
        with test.nested(
            mock.patch.object(ex, 'get_status'),
            mock.patch.object(ex, 'should_process'),
            mock.patch.object(ex, 'at_next_step'),
            mock.patch.object(ex, 'stop_resource'),
        ) as (mock_status, mock_should_process, mock_next_step, mock_stop):
            mock_status.return_value = expiry_states.WARNING
            mock_should_process.return_value = True
            mock_next_step.return_value = True
            self.assertTrue(ex.process())
            mock_stop.assert_called_once_with()

    def test_process_stopped_not_at_next_step(self):
        ex = expirer.JupyterHubVolumeExpirer(self.pvc)
        with test.nested(
            mock.patch.object(ex, 'get_status'),
            mock.patch.object(ex, 'should_process'),
            mock.patch.object(ex, 'at_next_step'),
            mock.patch.object(ex, 'finish_expiry'),
            mock.patch.object(ex, 'delete_resources'),
        ) as (mock_status, mock_should_process, mock_next_step,
              mock_finish, mock_delete):
            mock_status.return_value = expiry_states.STOPPED
            mock_should_process.return_value = True
            mock_next_step.return_value = False
            self.assertFalse(ex.process())
            mock_finish.assert_not_called()
            mock_delete.assert_not_called()

    def test_process_stopped_at_next_step(self):
        ex = expirer.JupyterHubVolumeExpirer(self.pvc)
        with test.nested(
            mock.patch.object(ex, 'get_status'),
            mock.patch.object(ex, 'should_process'),
            mock.patch.object(ex, 'at_next_step'),
            mock.patch.object(ex, 'finish_expiry'),
            mock.patch.object(ex, 'delete_resources'),
        ) as (mock_status, mock_should_process, mock_next_step,
              mock_finish, mock_delete):
            mock_status.return_value = expiry_states.STOPPED
            mock_should_process.return_value = True
            mock_next_step.return_value = True
            self.assertTrue(ex.process())
            mock_finish.assert_called_once_with()
            mock_delete.assert_called_once_with(force=True)

    def test_process_unspecified_status(self):
        ex = expirer.JupyterHubVolumeExpirer(self.pvc)
        with test.nested(
            mock.patch.object(ex, 'should_process'),
            mock.patch.object(ex, 'send_warning'),
            mock.patch.object(ex, 'stop_resource'),
            mock.patch.object(ex, 'finish_expiry'),
            mock.patch.object(ex, 'delete_resources'),
        ) as (mock_should_process, mock_warning, mock_stop,
              mock_finish, mock_delete):
            mock_should_process.return_value = False
            self.assertFalse(ex.process())
            mock_warning.assert_not_called()
            mock_stop.assert_not_called()
            mock_finish.assert_not_called()
            mock_delete.assert_not_called()
