import datetime
import testtools
from unittest.mock import patch

from nectar_tools.allocation_expiry import archiver
from nectar_tools import auth
from nectar_tools.tests import fakes

PROJECT = fakes.FakeProject('active')


@patch('nectar_tools.auth.get_session')
class NovaArchiverTests(testtools.TestCase):

    def test_is_archive_successful_no_instances(self, mock_session):
        na = archiver.NovaArchiver(project=PROJECT)

        with patch.object(na, 'all_servers', return_value=[]):
            self.assertTrue(na.is_archive_successful())

    def test_is_archive_successful_no_image(self, mock_session):
        na = archiver.NovaArchiver(project=PROJECT)

        with patch.object(na, 'all_servers', return_value=[fakes.FakeInstance()]):
            with patch.object(na.g_client.images, 'list', return_value=[]):
                self.assertFalse(na.is_archive_successful())

    def test_is_archive_successful_image_active(self, mock_session):
        na = archiver.NovaArchiver(project=PROJECT)

        with patch.object(na, 'all_servers', return_value=[fakes.FakeInstance()]):
            with patch.object(na.g_client.images, 'list', return_value=[fakes.FakeImage()]):
                self.assertTrue(na.is_archive_successful())

    def test_is_archive_successful_image_saving(self, mock_session):
        na = archiver.NovaArchiver(project=PROJECT)

        with patch.object(na, 'all_servers', return_value=[fakes.FakeInstance()]):
            with patch.object(na.g_client.images, 'list', return_value=[fakes.FakeImage(status='saving')]):
                self.assertFalse(na.is_archive_successful())

    def test_is_archive_successful_image_queued(self, mock_session):
        na = archiver.NovaArchiver(project=PROJECT)

        with patch.object(na, 'all_servers', return_value=[fakes.FakeInstance()]):
            with patch.object(na.g_client.images, 'list', return_value=[fakes.FakeImage(status='queued')]):
                self.assertFalse(na.is_archive_successful())

    def test_is_archive_successful_image_error(self, mock_session):
        na = archiver.NovaArchiver(project=PROJECT)

        with patch.object(na, 'all_servers', return_value=[fakes.FakeInstance()]):
            with patch.object(na.g_client.images, 'list', return_value=[fakes.FakeImage(status='error')]):
                self.assertFalse(na.is_archive_successful())

    def test_archive_instance(self, mock_session):
        na = archiver.NovaArchiver(project=PROJECT)
        instance = fakes.FakeInstance(status='SHUTDOWN', vm_state='stopped')
        with patch.object(na.n_client, 'servers') as mock_servers:
            na.archive_instance(instance)
            mock_servers.create_image.assert_called_with(instance.id, '%s_archive' % instance.id)
                
    def test_archive_instance_active_no_meta(self, mock_session):
        na = archiver.NovaArchiver(project=PROJECT)
        instance = fakes.FakeInstance()
        with patch.object(na.n_client, 'servers') as mock_servers:
            na.archive_instance(instance)
            metadata = {'archive_attempts': '1'}
            mock_servers.set_meta.assert_called_with(instance.id, metadata)
            mock_servers.stop.assert_called_with(instance.id)
            mock_servers.create_image.assert_not_called()

    def test_archive_instance_increment_meta(self, mock_session):
        na = archiver.NovaArchiver(project=PROJECT)
        instance = fakes.FakeInstance(status='SHUTDOWN', metadata={'archive_attempts': '1'})
        with patch.object(na.n_client, 'servers') as mock_servers:
            na.archive_instance(instance)
            metadata = {'archive_attempts': '2'}
            mock_servers.set_meta.assert_called_with(instance.id, metadata)
            mock_servers.create_image.assert_not_called()

    def test_archive_instance_error(self, mock_session):
        na = archiver.NovaArchiver(project=PROJECT)
        instance = fakes.FakeInstance(status='ERROR')
        with patch.object(na.n_client, 'servers') as mock_servers:
            na.archive_instance(instance)
            mock_servers.create_image.assert_not_called()

    def test_archive_instance_deleted(self, mock_session):
        na = archiver.NovaArchiver(project=PROJECT)
        instance = fakes.FakeInstance(status='DELETED')
        with patch.object(na.n_client, 'servers') as mock_servers:
            na.archive_instance(instance)
            mock_servers.delete.assert_called_with(instance.id)
            mock_servers.create_image.assert_not_called()

    def test_archive_instance_bad_task_states(self, mock_session):
        na = archiver.NovaArchiver(project=PROJECT)

        with patch.object(na.n_client, 'servers') as mock_servers:
            for state in ['suspending', 'image_snapshot_pending', 'deleting'
                          'image_snapshot', 'image_pending_upload']:
                instance = fakes.FakeInstance(status='SHUTOFF', task_state=state)
                na.archive_instance(instance)

            mock_servers.create_image.assert_not_called()
