import datetime
import testtools
from unittest.mock import call
from unittest.mock import patch

from nectar_tools.expiry import archiver
from nectar_tools import auth
from nectar_tools import test
from nectar_tools.tests import fakes

PROJECT = fakes.FakeProject('active')


@patch('nectar_tools.auth.get_session')
class NovaArchiverTests(testtools.TestCase):

    def test_zero_quota(self, mock_session):
        na = archiver.NovaArchiver(project=PROJECT)
        with patch.object(na.n_client, 'quotas') as mock_quotas:
            na.zero_quota()
            mock_quotas.update.assert_called_with(tenant_id=PROJECT.id,
                                                  cores=0, ram=0, instances=0,
                                                  force=True)
            
    def test_is_archive_successful_no_instances(self, mock_session):
        na = archiver.NovaArchiver(project=PROJECT)

        with patch.object(na, 'all_servers', return_value=[]):
            self.assertTrue(na.is_archive_successful())

    def test_is_archive_instance_has_archive(self, mock_session):
        na = archiver.NovaArchiver(project=PROJECT)

        with test.nested(
            patch.object(na, 'all_servers',
                         return_value=[fakes.FakeInstance]),
            patch.object(na, 'instance_has_archive',
                         return_value=True),
        ) as (mock_servers, mock_has_archive):
            self.assertTrue(na.is_archive_successful())

    def test_is_archive_instance_no_archive(self, mock_session):
        na = archiver.NovaArchiver(project=PROJECT)

        with test.nested(
            patch.object(na, 'all_servers',
                         return_value=[fakes.FakeInstance()]),
            patch.object(na, 'instance_has_archive',
                         return_value=False),
        ) as (mock_servers, mock_has_archive):
            self.assertFalse(na.is_archive_successful())

    def test_instance_has_archive_bad_state(self, mock_session):
        na = archiver.NovaArchiver(project=PROJECT)
        for state in ['image_snapshot_pending',
                      'image_snapshot', 'image_pending_upload']:
            self.assertFalse(na.instance_has_archive(
                fakes.FakeInstance(task_state=state)))

    def test_instance_has_archive_no_image(self, mock_session):
        na = archiver.NovaArchiver(project=PROJECT)
        instance = fakes.FakeInstance()
        with patch.object(na, 'get_image_by_instance_id',
                          return_value=None) as mock_get_image:
            self.assertFalse(na.instance_has_archive(instance))

    def test_instance_has_archive_image_active(self, mock_session):
        na = archiver.NovaArchiver(project=PROJECT)
        instance = fakes.FakeInstance()
        image = fakes.FakeImage(nectar_archive='True')
        with patch.object(na, 'get_image_by_instance_id',
                          return_value=image) as mock_get_image:
            self.assertTrue(na.instance_has_archive(instance))

    def test_instance_has_archive_image_active_no_prop(self, mock_session):
        na = archiver.NovaArchiver(project=PROJECT)
        instance = fakes.FakeInstance()
        image = fakes.FakeImage()
        with patch.object(na, 'get_image_by_instance_id',
                          return_value=image) as mock_get_image:
            with patch.object(na, 'g_client') as mock_glance:
                self.assertTrue(na.instance_has_archive(instance))
                mock_glance.images.update.assert_called_with(
                    image.id, nectar_archive='True')

    def test_instance_has_archive_image_in_progress(self, mock_session):
        na = archiver.NovaArchiver(project=PROJECT)
        instance = fakes.FakeInstance()
        image = fakes.FakeImage(status='queued')
        with patch.object(na, 'get_image_by_instance_id',
                          return_value=image) as mock_get_image:
            self.assertFalse(na.instance_has_archive(instance))
            mock_get_image.reset_mock()
            mock_get_image.return_value = fakes.FakeImage(status='saving')
            self.assertFalse(na.instance_has_archive(instance))
            
    def test_instance_has_archive_image_error(self, mock_session):
        na = archiver.NovaArchiver(project=PROJECT)
        instance = fakes.FakeInstance()
        image = fakes.FakeImage(status='error')
        with patch.object(na, 'get_image_by_instance_id',
                          return_value=image) as mock_get_image:
            self.assertFalse(na.instance_has_archive(instance))

    def test_archive_instance(self, mock_session):
        na = archiver.NovaArchiver(project=PROJECT)
        instance = fakes.FakeInstance(status='SHUTDOWN', vm_state='stopped')
        with patch.object(na.n_client, 'servers') as mock_servers:
            na.archive_instance(instance)
            mock_servers.create_image.assert_called_with(
                instance.id, '%s_archive' % instance.id,
                metadata={'nectar_archive': 'True'})
                
    def test_archive_instance_active(self, mock_session):
        na = archiver.NovaArchiver(project=PROJECT)
        instance = fakes.FakeInstance()
        with patch.object(na.n_client, 'servers') as mock_servers:
            na.archive_instance(instance)
            mock_servers.stop.assert_called_with(instance.id)
            mock_servers.create_image.assert_not_called()

    def test_archive_instance_increment_meta(self, mock_session):
        na = archiver.NovaArchiver(project=PROJECT)
        instance = fakes.FakeInstance(status='SHUTDOWN', vm_state='stopped',
                                      metadata={'archive_attempts': '1'})
        with patch.object(na.n_client, 'servers') as mock_servers:
            na.archive_instance(instance)
            metadata = {'archive_attempts': '2'}
            mock_servers.set_meta.assert_called_with(instance.id, metadata)
            mock_servers.create_image.assert_called_with(
                instance.id, '%s_archive' % instance.id,
                metadata={'nectar_archive': 'True'})

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
                instance = fakes.FakeInstance(status='SHUTOFF',
                                              task_state=state)
                na.archive_instance(instance)

            mock_servers.create_image.assert_not_called()

    def test_stop_resources(self, mock_session):
        na = archiver.NovaArchiver(project=PROJECT)
        instance1 = fakes.FakeInstance()
        instance2 = fakes.FakeInstance(id='fake2')

        with test.nested(
            patch.object(na, 'all_servers', return_value=[
                instance1, instance2]),
            patch.object(na, 'lock_instance'),
            patch.object(na, 'stop_instance'),
        ) as (mock_all_servers, mock_lock_instance, mock_stop_instance):
            na.stop_resources()
            mock_lock_instance.assert_has_calls([call(instance1),
                                                 call(instance2)])
            self.assertEqual(mock_lock_instance.call_count, 2)
            mock_stop_instance.assert_has_calls([call(instance1),
                                                 call(instance2)])
            self.assertEqual(mock_stop_instance.call_count, 2)

    def test_archive_resources(self, mock_session):
        na = archiver.NovaArchiver(project=PROJECT)
        instance1 = fakes.FakeInstance()
        instance2 = fakes.FakeInstance(id='fake2')

        with test.nested(
            patch.object(na, 'all_servers', return_value=[
                instance1, instance2]),
            patch.object(na, 'instance_has_archive'),
            patch.object(na, 'delete_instance'),
            patch.object(na, 'archive_instance'),
        ) as (mock_all_servers, mock_has_archive, mock_delete, mock_archive):
            mock_has_archive.return_value = False
            na.archive_resources()
            mock_archive.assert_has_calls([call(instance1),
                                                    call(instance2)])
            self.assertEqual(mock_archive.call_count, 2)

    def test_archive_resources_already_archived(self, mock_session):
        na = archiver.NovaArchiver(project=PROJECT)
        instance1 = fakes.FakeInstance()
        instance2 = fakes.FakeInstance(id='fake2')

        with test.nested(
            patch.object(na, 'all_servers', return_value=[
                instance1, instance2]),
            patch.object(na, 'instance_has_archive'),
            patch.object(na, 'delete_instance'),
            patch.object(na, 'archive_instance'),
        ) as (mock_all_servers, mock_has_archive, mock_delete, mock_archive):
            mock_has_archive.return_value = True
            na.archive_resources()
            mock_delete.assert_has_calls([call(instance1),
                                                   call(instance2)])
            self.assertEqual(mock_delete.call_count, 2)

    def test_delete_resources_ready(self, mock_session):
        na = archiver.NovaArchiver(project=PROJECT)
        instance1 = fakes.FakeInstance()
        instance2 = fakes.FakeInstance(id='fake2')

        with test.nested(
            patch.object(na, 'all_servers', return_value=[
                instance1, instance2]),
            patch.object(na, 'instance_has_archive'),
            patch.object(na, 'delete_instance'),
        ) as (mock_all_servers, mock_has_archive, mock_delete_instance):
            mock_has_archive.return_value = True
            na.delete_resources()
            mock_delete_instance.assert_has_calls([call(instance1),
                                                   call(instance2)])
            self.assertEqual(mock_delete_instance.call_count, 2)

    def test_delete_resources_not_ready(self, mock_session):
        na = archiver.NovaArchiver(project=PROJECT)
        instance1 = fakes.FakeInstance()
        instance2 = fakes.FakeInstance(id='fake2')

        with test.nested(
            patch.object(na, 'all_servers', return_value=[
                instance1, instance2]),
            patch.object(na, 'instance_has_archive'),
            patch.object(na, 'delete_instance'),
        ) as (mock_all_servers, mock_has_archive, mock_delete_instance):
            mock_has_archive.return_value = False
            na.delete_resources()
            mock_delete_instance.assert_not_called()

    def test_delete_resources_force(self, mock_session):
        na = archiver.NovaArchiver(project=PROJECT)
        instance1 = fakes.FakeInstance()
        instance2 = fakes.FakeInstance(id='fake2')

        with test.nested(
            patch.object(na, 'all_servers', return_value=[
                instance1, instance2]),
            patch.object(na, 'instance_has_archive'),
            patch.object(na, 'delete_instance'),
        ) as (mock_all_servers, mock_has_archive, mock_delete_instance):
            mock_has_archive.return_value = False
            na.delete_resources(force=True)
            mock_delete_instance.assert_has_calls([call(instance1),
                                                   call(instance2)])
            self.assertEqual(mock_delete_instance.call_count, 2)

    def test_delete_archives(self, mock_session):
        na = archiver.NovaArchiver(project=PROJECT)
        image1 = fakes.FakeImage()
        image2 = fakes.FakeImage(id='fake2')

        with test.nested(
            patch.object(na, '_get_project_images', return_value=[
                image1, image2]),
            patch.object(na, 'g_client'),
        ) as (mock_get_images, mock_glance):
            
            mock_get_images.return_value = [image1, image2]
            na.delete_archives()
            mock_get_images.assert_called_with()
            mock_glance.images.delete.assert_has_calls([call(image1.id),
                                                       call(image2.id)])
            self.assertEqual(mock_glance.images.delete.call_count, 2)

    def test_get_project_images(self, mock_session):
        na = archiver.NovaArchiver(project=PROJECT)
        image1 = fakes.FakeImage()
        image2 = fakes.FakeImage(id='fake2')
        
        with patch.object(na, 'g_client') as mock_glance:
            mock_glance.images.list.return_value = [image1, image2]
            output = na._get_project_images()
            # Run twice to ensure glance call only happens once
            output = na._get_project_images()
            mock_glance.images.list.assert_called_with(
                filters={'owner_id': PROJECT.id, 'nectar_archive': 'True'})
            self.assertEqual(mock_glance.images.list.call_count, 1)
            self.assertEqual([image1, image2], output)

    def test_lock_instance(self, mock_session):
        na = archiver.NovaArchiver(project=PROJECT)
        instance = fakes.FakeInstance()
        with patch.object(na.n_client, 'servers') as mock_servers:
            na.lock_instance(instance)
            mock_servers.lock.assert_called_with(instance.id)

    def test_delete_instance(self, mock_session):
        na = archiver.NovaArchiver(project=PROJECT)
        instance = fakes.FakeInstance()
        with patch.object(na.n_client, 'servers') as mock_servers:
            na.delete_instance(instance)
            mock_servers.delete.assert_called_with(instance.id)

    def test_get_image_by_name(self, mock_session):
        na = archiver.NovaArchiver(project=PROJECT)
        image1 = fakes.FakeImage(name='fake-name1')
        image2 = fakes.FakeImage(id='fake2', name='fake-name2')
        with patch.object(na, '_get_project_images',
                          return_value=[image1, image2]) as mock_images:
            self.assertEqual(image1, na.get_image_by_name('fake-name1'))
            self.assertEqual(image2, na.get_image_by_name('fake-name2'))
            mock_images.reset_mock()
            mock_images.return_value = []
            self.assertIsNone(na.get_image_by_name('fake-name1'))
