from unittest import mock

from designateclient import exceptions as designate_exc

from nectar_tools import config
from nectar_tools.expiry import archiver
from nectar_tools import test
from nectar_tools.tests import fakes

CONF = config.CONFIG
PROJECT = fakes.FakeProject('active')
IMAGE = fakes.FakeImage()

PROJECT_RESOURCE = {'project': PROJECT}
RESOURCES = {'project': PROJECT,
             'image': IMAGE}


@mock.patch('nectar_tools.auth.get_session', new=mock.Mock())
class NovaArchiverTests(test.TestCase):

    def test_zero_quota(self):
        na = archiver.NovaArchiver(resources=PROJECT_RESOURCE)
        with mock.patch.object(na.n_client, 'quotas') as mock_quotas:
            na.zero_quota()
            mock_quotas.update.assert_called_with(tenant_id=PROJECT.id,
                                                  cores=0, ram=0, instances=0,
                                                  force=True)

    def test_is_archive_successful_no_instances(self):
        na = archiver.NovaArchiver(resources=PROJECT_RESOURCE)

        with mock.patch.object(na, '_all_instances', return_value=[]):
            self.assertTrue(na.is_archive_successful())

    def test_is_archive_instance_has_archive(self):
        na = archiver.NovaArchiver(resources=PROJECT_RESOURCE)

        with test.nested(
            mock.patch.object(na, '_all_instances',
                         return_value=[fakes.FakeInstance]),
            mock.patch.object(na, '_instance_has_archive',
                         return_value=True),
        ) as (mock_servers, mock_has_archive):
            self.assertTrue(na.is_archive_successful())

    def test_is_archive_instance_no_archive(self):
        na = archiver.NovaArchiver(resources=PROJECT_RESOURCE)

        with test.nested(
            mock.patch.object(na, '_all_instances',
                         return_value=[fakes.FakeInstance()]),
            mock.patch.object(na, '_instance_has_archive',
                         return_value=False),
        ) as (mock_servers, mock_has_archive):
            self.assertFalse(na.is_archive_successful())

    def test_instance_has_archive_bad_state(self):
        na = archiver.NovaArchiver(resources=PROJECT_RESOURCE)
        for state in ['image_snapshot_pending',
                      'image_snapshot', 'image_pending_upload']:
            self.assertFalse(na._instance_has_archive(
                fakes.FakeInstance(task_state=state)))

    def test_instance_has_archive_no_image(self):
        na = archiver.NovaArchiver(resources=PROJECT_RESOURCE)
        instance = fakes.FakeInstance()
        with mock.patch.object(na, '_get_image_by_instance_id',
                          return_value=None):
            self.assertFalse(na._instance_has_archive(instance))

    def test_instance_has_archive_image_active(self):
        na = archiver.NovaArchiver(resources=PROJECT_RESOURCE)
        instance = fakes.FakeInstance()
        image = fakes.FakeImage(nectar_archive='True')
        with mock.patch.object(na, '_get_image_by_instance_id',
                          return_value=image):
            self.assertTrue(na._instance_has_archive(instance))

    def test_instance_has_archive_image_in_progress(self):
        na = archiver.NovaArchiver(resources=PROJECT_RESOURCE)
        instance = fakes.FakeInstance()
        image = fakes.FakeImage(status='queued')
        with mock.patch.object(na, '_get_image_by_instance_id',
                          return_value=image) as mock_get_image:
            self.assertFalse(na._instance_has_archive(instance))
            mock_get_image.reset_mock()
            mock_get_image.return_value = fakes.FakeImage(status='saving')
            self.assertFalse(na._instance_has_archive(instance))

    def test_instance_has_archive_image_error(self):
        na = archiver.NovaArchiver(resources=PROJECT_RESOURCE)
        instance = fakes.FakeInstance()
        image = fakes.FakeImage(status='error')
        with mock.patch.object(na, '_get_image_by_instance_id',
                          return_value=image):
            self.assertFalse(na._instance_has_archive(instance))

    def test_archive_instance(self):
        na = archiver.NovaArchiver(resources=PROJECT_RESOURCE)
        instance = fakes.FakeInstance(status='SHUTDOWN', vm_state='stopped')
        with mock.patch.object(na.n_client, 'servers') as mock_servers:
            na._archive_instance(instance)
            mock_servers.create_image.assert_called_with(
                instance.id, '%s_archive' % instance.id,
                metadata={'nectar_archive': 'True'})

    def test_archive_instance_active(self):
        na = archiver.NovaArchiver(resources=PROJECT_RESOURCE)
        instance = fakes.FakeInstance()
        with mock.patch.object(na.n_client, 'servers') as mock_servers:
            na._archive_instance(instance)
            mock_servers.stop.assert_called_with(instance.id)
            mock_servers.create_image.assert_not_called()

    def test_archive_instance_increment_meta(self):
        na = archiver.NovaArchiver(resources=PROJECT_RESOURCE)
        instance = fakes.FakeInstance(status='SHUTDOWN', vm_state='stopped',
                                      metadata={'archive_attempts': '1'})
        with mock.patch.object(na.n_client, 'servers') as mock_servers:
            na._archive_instance(instance)
            metadata = {'archive_attempts': '2'}
            mock_servers.set_meta.assert_called_with(instance.id, metadata)
            mock_servers.create_image.assert_called_with(
                instance.id, '%s_archive' % instance.id,
                metadata={'nectar_archive': 'True'})

    def test_archive_instance_error(self):
        na = archiver.NovaArchiver(resources=PROJECT_RESOURCE)
        instance = fakes.FakeInstance(status='ERROR')
        with mock.patch.object(na.n_client, 'servers') as mock_servers:
            na._archive_instance(instance)
            mock_servers.create_image.assert_not_called()

    def test_archive_instance_deleted(self):
        na = archiver.NovaArchiver(resources=PROJECT_RESOURCE)
        instance = fakes.FakeInstance(status='DELETED')
        with mock.patch.object(na.n_client, 'servers') as mock_servers:
            na._archive_instance(instance)
            mock_servers.delete.assert_called_with(instance.id)
            mock_servers.create_image.assert_not_called()

    def test_archive_instance_bad_task_states(self):
        na = archiver.NovaArchiver(resources=PROJECT_RESOURCE)

        with mock.patch.object(na.n_client, 'servers') as mock_servers:
            for state in ['suspending', 'image_snapshot_pending', 'deleting'
                          'image_snapshot', 'image_pending_upload']:
                instance = fakes.FakeInstance(status='SHUTOFF',
                                              task_state=state)
                na._archive_instance(instance)

            mock_servers.create_image.assert_not_called()

    def test_stop_resources(self):
        na = archiver.NovaArchiver(resources=PROJECT_RESOURCE)
        instance1 = fakes.FakeInstance()
        instance2 = fakes.FakeInstance(id='fake2')

        with test.nested(
            mock.patch.object(na, '_all_instances', return_value=[
                instance1, instance2]),
            mock.patch.object(na, '_lock_instance'),
            mock.patch.object(na, '_stop_instance'),
        ) as (mock__all_instances, mock_lock_instance, mock_stop_instance):
            na.stop_resources()
            mock_lock_instance.assert_has_calls([mock.call(instance1),
                                                 mock.call(instance2)])
            self.assertEqual(mock_lock_instance.call_count, 2)
            mock_stop_instance.assert_has_calls([mock.call(instance1),
                                                 mock.call(instance2)])
            self.assertEqual(mock_stop_instance.call_count, 2)

    def test_archive_resources(self):
        na = archiver.NovaArchiver(resources=PROJECT_RESOURCE)
        instance1 = fakes.FakeInstance()
        instance2 = fakes.FakeInstance(id='fake2')

        with test.nested(
            mock.patch.object(na, '_all_instances', return_value=[
                instance1, instance2]),
            mock.patch.object(na, '_instance_has_archive'),
            mock.patch.object(na, '_delete_instance'),
            mock.patch.object(na, '_archive_instance'),
        ) as (mock__all_instances, mock_has_archive, mock_delete,
              mock_archive):
            mock_has_archive.return_value = False
            na.archive_resources()
            mock_archive.assert_has_calls([mock.call(instance1),
                                           mock.call(instance2)])
            self.assertEqual(mock_archive.call_count, 2)

    def test_archive_resources_already_archived(self):
        na = archiver.NovaArchiver(resources=PROJECT_RESOURCE)
        instance1 = fakes.FakeInstance()
        instance2 = fakes.FakeInstance(id='fake2')

        with test.nested(
            mock.patch.object(na, '_all_instances', return_value=[
                instance1, instance2]),
            mock.patch.object(na, '_instance_has_archive'),
            mock.patch.object(na, '_delete_instance'),
            mock.patch.object(na, '_archive_instance'),
        ) as (mock__all_instances, mock_has_archive, mock_delete,
              mock_archive):
            mock_has_archive.return_value = True
            na.archive_resources()
            mock_delete.assert_has_calls([mock.call(instance1),
                                          mock.call(instance2)])
            self.assertEqual(mock_delete.call_count, 2)

    def test_delete_resources_ready(self):
        na = archiver.NovaArchiver(resources=PROJECT_RESOURCE)
        instance1 = fakes.FakeInstance()
        instance2 = fakes.FakeInstance(id='fake2')

        with test.nested(
            mock.patch.object(na, '_all_instances', return_value=[
                instance1, instance2]),
            mock.patch.object(na, '_instance_has_archive'),
            mock.patch.object(na, '_delete_instance'),
        ) as (mock__all_instances, mock_has_archive, mock_delete_instance):
            mock_has_archive.return_value = True
            na.delete_resources()
            mock_delete_instance.assert_has_calls([mock.call(instance1),
                                                   mock.call(instance2)])
            self.assertEqual(mock_delete_instance.call_count, 2)

    def test_delete_resources_not_ready(self):
        na = archiver.NovaArchiver(resources=PROJECT_RESOURCE)
        instance1 = fakes.FakeInstance()
        instance2 = fakes.FakeInstance(id='fake2')

        with test.nested(
            mock.patch.object(na, '_all_instances', return_value=[
                instance1, instance2]),
            mock.patch.object(na, '_instance_has_archive'),
            mock.patch.object(na, '_delete_instance'),
        ) as (mock__all_instances, mock_has_archive, mock_delete_instance):
            mock_has_archive.return_value = False
            na.delete_resources()
            mock_delete_instance.assert_not_called()

    def test_delete_resources_force(self):
        na = archiver.NovaArchiver(resources=PROJECT_RESOURCE)
        instance1 = fakes.FakeInstance()
        instance2 = fakes.FakeInstance(id='fake2')

        with test.nested(
            mock.patch.object(na, '_all_instances', return_value=[
                instance1, instance2]),
            mock.patch.object(na, '_instance_has_archive'),
            mock.patch.object(na, '_delete_instance'),
        ) as (mock__all_instances, mock_has_archive, mock_delete_instance):
            mock_has_archive.return_value = False
            na.delete_resources(force=True)
            mock_delete_instance.assert_has_calls([mock.call(instance1),
                                                   mock.call(instance2)])
            self.assertEqual(mock_delete_instance.call_count, 2)

    def test_enable_resources(self):
        na = archiver.NovaArchiver(resources=PROJECT_RESOURCE)
        instance1 = fakes.FakeInstance(metadata={'expiry_locked': 'True'})
        with test.nested(
            mock.patch.object(na, '_all_instances', return_value=[instance1]),
            mock.patch.object(na, '_unlock_instance'),
        ) as (mock_all_instances, mock_unlock):
            na.enable_resources()
            mock_unlock.assert_called_once_with(instance1)

    def test_enable_resources_no_metadata(self):
        na = archiver.NovaArchiver(resources=PROJECT_RESOURCE)
        instance1 = fakes.FakeInstance()
        with test.nested(
            mock.patch.object(na, '_all_instances', return_value=[instance1]),
            mock.patch.object(na, '_unlock_instance'),
        ) as (mock_all_instances, mock_unlock):
            na.enable_resources()
            mock_unlock.assert_not_called()

    def test_enable_resources_security(self):
        na = archiver.NovaArchiver(resources=PROJECT_RESOURCE)
        instance1 = fakes.FakeInstance(metadata={'security_ticket': 123})
        with test.nested(
            mock.patch.object(na, '_all_instances', return_value=[instance1]),
            mock.patch.object(na, '_unlock_instance'),
        ) as (mock_all_instances, mock_unlock):
            na.enable_resources()
            mock_unlock.assert_not_called()

    def test_delete_archives(self):
        na = archiver.NovaArchiver(resources=PROJECT_RESOURCE)
        image1 = fakes.FakeImage()
        image2 = fakes.FakeImage(id='fake2')

        with test.nested(
            mock.patch.object(na, '_get_project_images', return_value=[
                image1, image2]),
            mock.patch.object(na, 'g_client'),
        ) as (mock_get_images, mock_glance):

            mock_get_images.return_value = [image1, image2]
            na.delete_archives()
            mock_get_images.assert_called_with()
            mock_glance.images.delete.assert_has_calls([mock.call(image1.id),
                                                        mock.call(image2.id)])
            self.assertEqual(mock_glance.images.delete.call_count, 2)

    def test_all_instances(self):
        na = archiver.NovaArchiver(resources=PROJECT_RESOURCE)
        i1 = fakes.FakeInstance(id='i1')
        i2 = fakes.FakeInstance(id='i2')

        def fake_list(search_opts):
            if 'marker' in search_opts:
                return []
            else:
                return [i1, i2]

        with mock.patch.object(na, 'n_client') as mock_nova:
            mock_nova.servers.list.side_effect = fake_list
            instances = na._all_instances()
            self.assertEqual(2, mock_nova.servers.list.call_count)
            self.assertEqual([i1, i2], instances)

    def test_get_project_images(self):
        na = archiver.NovaArchiver(resources=PROJECT_RESOURCE)
        image1 = fakes.FakeImage()
        image2 = fakes.FakeImage(id='fake2')

        with mock.patch.object(na, 'g_client') as mock_glance:
            mock_glance.images.list.return_value = [image1, image2]
            output = na._get_project_images()
            # Run twice to ensure glance call only happens once
            output = na._get_project_images()
            mock_glance.images.list.assert_called_with(
                filters={'owner_id': PROJECT.id, 'nectar_archive': 'True'})
            self.assertEqual(mock_glance.images.list.call_count, 1)
            self.assertEqual([image1, image2], output)

    def test_lock_instance(self):
        na = archiver.NovaArchiver(resources=PROJECT_RESOURCE)
        instance = fakes.FakeInstance()
        with mock.patch.object(na.n_client, 'servers') as mock_servers:
            na._lock_instance(instance)
            mock_servers.lock.assert_called_with(instance.id)
            mock_servers.set_meta.assert_called_with(instance.id,
                                                     {'expiry_locked': 'True'})

    def test_unlock_instance(self):
        na = archiver.NovaArchiver(resources=PROJECT_RESOURCE)
        instance = fakes.FakeInstance(locked=True)
        with mock.patch.object(na.n_client, 'servers') as mock_servers:
            na._unlock_instance(instance)
            mock_servers.unlock.assert_called_with(instance.id)
            mock_servers.delete_meta.assert_called_with(instance.id,
                                                        ['expiry_locked'])

    def test_unlock_instance_already_unlocked(self):
        na = archiver.NovaArchiver(resources=PROJECT_RESOURCE)
        instance = fakes.FakeInstance(locked=False)
        with mock.patch.object(na.n_client, 'servers') as mock_servers:
            na._unlock_instance(instance)
            mock_servers.unlock.assert_not_called()

    def test_delete_instance(self):
        na = archiver.NovaArchiver(resources=PROJECT_RESOURCE)
        instance = fakes.FakeInstance()
        with mock.patch.object(na.n_client, 'servers') as mock_servers:
            na._delete_instance(instance)
            mock_servers.delete.assert_called_with(instance.id)

    def test_get_image_by_instance_id(self):
        na = archiver.NovaArchiver(resources=PROJECT_RESOURCE)
        image1 = fakes.FakeImage(id='fake1', name='fake1_archive')
        image2 = fakes.FakeImage(id='fake2', name='fake2_archive')
        instance1 = fakes.FakeInstance(id='fake1')
        instance2 = fakes.FakeInstance(id='fake2')
        instance3 = fakes.FakeInstance(id='fake3')
        with mock.patch.object(na, '_get_project_images',
                               return_value=[image1, image2]):
            self.assertEqual(image1,
                             na._get_image_by_instance_id(instance1.id))
            self.assertEqual(image2,
                             na._get_image_by_instance_id(instance2.id))
            self.assertIsNone(na._get_image_by_instance_id(instance3.id))


@mock.patch('nectar_tools.auth.get_session', new=mock.Mock())
class CinderArchiverTests(test.TestCase):

    def test_zero_quota(self):
        ca = archiver.CinderArchiver(resources=PROJECT_RESOURCE)
        with mock.patch.object(ca.c_client, 'quotas') as mock_quotas:
            ca.zero_quota()
            mock_quotas.update.assert_called_with(tenant_id=PROJECT.id,
                                                  volumes=0, gigabytes=0,
                                                  snapshots=0)

    def test_delete_resources(self):
        ca = archiver.CinderArchiver(resources=PROJECT_RESOURCE)
        volume1 = fakes.FakeVolume()
        with test.nested(
            mock.patch.object(ca, '_all_volumes', return_value=[volume1]),
            mock.patch.object(ca, '_delete_volume'),
        ) as (mock_volumes, mock_delete):
            ca.delete_resources()
            mock_delete.assert_not_called()

    def test_delete_resources_force(self):
        ca = archiver.CinderArchiver(resources=PROJECT_RESOURCE)
        volume1 = fakes.FakeVolume()
        volume2 = fakes.FakeVolume(id='fake2')

        with test.nested(
            mock.patch.object(ca, '_all_volumes',
                              return_value=[volume1, volume2]),
            mock.patch.object(ca, '_delete_volume'),
        ) as (mock_volumes, mock_delete):
            ca.delete_resources(force=True)
            mock_delete.assert_has_calls([mock.call(volume1),
                                          mock.call(volume2)])
            self.assertEqual(mock_delete.call_count, 2)

    def test_all_volumes(self):
        ca = archiver.CinderArchiver(resources=PROJECT_RESOURCE)
        volume1 = fakes.FakeVolume()
        setattr(volume1, 'os-vol-tenant-attr:tenant_id', PROJECT.id)
        volume2 = fakes.FakeVolume(id='fake2')
        setattr(volume2, 'os-vol-tenant-attr:tenant_id', PROJECT.id)
        volumes = [volume1, volume2]
        with mock.patch.object(ca, 'c_client') as mock_cinder:
            mock_cinder.volumes.list.return_value = volumes
            output = ca._all_volumes()
            opts = {'all_tenants': True, 'project_id': PROJECT.id}
            mock_cinder.volumes.list.assert_called_with(search_opts=opts)
            self.assertEqual(volumes, output)
            self.assertEqual(volumes, ca.volumes)

    def test_all_volumes_bug_1742313(self):
        ca = archiver.CinderArchiver(resources=PROJECT_RESOURCE)
        volume1 = fakes.FakeVolume()
        setattr(volume1, 'os-vol-tenant-attr:tenant_id', PROJECT.id)
        volume2 = fakes.FakeVolume(id='fake2')
        setattr(volume2, 'os-vol-tenant-attr:tenant_id', 'bogus-id')
        volumes = [volume1, volume2]
        with mock.patch.object(ca, 'c_client') as mock_cinder:
            mock_cinder.volumes.list.return_value = volumes
            output = ca._all_volumes()
            opts = {'all_tenants': True, 'project_id': PROJECT.id}
            mock_cinder.volumes.list.assert_called_with(search_opts=opts)
            self.assertEqual([volume1], output)
            self.assertEqual([volume1], ca.volumes)

    def test_delete_volume(self):
        ca = archiver.CinderArchiver(resources=PROJECT_RESOURCE)
        volume = fakes.FakeVolume()
        with mock.patch.object(ca, 'c_client') as mock_cinder:
            ca._delete_volume(volume)
            mock_cinder.volumes.delete.assert_called_once_with(
                volume.id, cascade=True)


@mock.patch('nectar_tools.auth.get_session', new=mock.Mock())
class NeutronBasicArchiverTests(test.TestCase):

    def test_zero_quota(self):
        na = archiver.NeutronBasicArchiver(resources=PROJECT_RESOURCE)
        with mock.patch.object(na, 'ne_client') as mock_neutron:
            na.zero_quota()
            body = {'quota': {'port': 0,
                              'security_group': 0,
                              'security_group_rule': 0,
                              'floatingip': 0,
                              'router': 0,
                              'network': 0,
                              'subnet': 0,
                              'loadbalancer': 0,
                          }
            }
            mock_neutron.update_quota.assert_called_with(PROJECT.id, body)

    def test_delete_neutron_resources(self):
        na = archiver.NeutronBasicArchiver(resources=PROJECT_RESOURCE)

        mock_list = mock.Mock()
        mock_list.return_value = {'fakeresources': [{'id': 'fakeresource1'},
                                                    {'id': 'fakeresource2'}]}
        mock_delete = mock.Mock()
        na._delete_neutron_resources('fakeresources', mock_list, mock_delete)
        mock_list.assert_called_once_with(tenant_id=PROJECT.id)
        mock_delete.assert_has_calls([mock.call('fakeresource1'),
                                      mock.call('fakeresource2')])


@mock.patch('nectar_tools.auth.get_session', new=mock.Mock())
class NeutronArchiverTests(test.TestCase):

    def test_delete_routers(self):
        na = archiver.NeutronArchiver(resources=PROJECT_RESOURCE)
        router1 = {'id': 'router1'}
        routers = [router1]
        port1 = {'id': 'port1'}
        ports = [port1]
        with mock.patch.object(na, 'ne_client') as mock_neutron:
            mock_neutron.list_routers.return_value = {'routers': routers}
            mock_neutron.list_ports.return_value = {'ports': ports}
            na._delete_routers()

            mock_neutron.update_router.assert_called_once_with(
                router1['id'], {'router': {'routes': None}})

            mock_neutron.list_routers.assert_called_once_with(
                tenant_id=PROJECT.id)

            mock_neutron.list_ports.assert_called_once_with(
                device_id=router1['id'],
                device_owner='network:router_interface')

            mock_neutron.remove_interface_router.assert_called_once_with(
                router1['id'], {'port_id': port1['id']})

            mock_neutron.delete_router.assert_called_once_with(router1['id'])


@mock.patch('nectar_tools.auth.get_session', new=mock.Mock())
class GlanceArchiverTests(test.TestCase):

    def test_delete_resources(self):
        ga = archiver.GlanceArchiver(resources=PROJECT_RESOURCE)
        ga.delete_resources()

    def test_delete_resources_force(self):
        ga = archiver.GlanceArchiver(resources=PROJECT_RESOURCE)
        image1 = fakes.FakeImage(visibility='private')
        image2 = fakes.FakeImage(visibility='public')
        image3 = fakes.FakeImage(visibility='private', protected=True)
        images = [image1, image2, image3]
        with mock.patch.object(ga, 'g_client') as mock_glance:
            mock_glance.images.list.return_value = images

            ga.delete_resources(force=True)
            mock_glance.images.list.assert_called_once_with(
                filters={'owner': PROJECT.id})

            mock_glance.images.delete.assert_called_once_with(image1.id)


@mock.patch('nectar_tools.auth.get_session', new=mock.Mock())
class SwiftArchiverTests(test.TestCase):

    def test_zero_quota(self):
        sa = archiver.SwiftArchiver(resources=PROJECT_RESOURCE)
        with mock.patch.object(sa, 's_client') as mock_swift:
            sa.zero_quota()
            mock_swift.post_account.assert_called_once_with(
                headers={'x-account-meta-quota-bytes': 0})

    def test_delete_resources(self):
        sa = archiver.SwiftArchiver(resources=PROJECT_RESOURCE)
        sa.delete_resources()

    def test_delete_resources_force(self):
        sa = archiver.SwiftArchiver(resources=PROJECT_RESOURCE)

        containers = [{'name': 'public'}, {'name': 'private'}]
        account = ('fake', containers)

        def _get_container(value):
            if value == 'public':
                return ({'x-container-read': 'r'}, ['fake-object'])
            else:
                return ({'fake': 'fake'}, ['fake-object1'])

        with test.nested(
            mock.patch.object(sa, 's_client'),
            mock.patch.object(sa, '_delete_container'),
        ) as (mock_swift, mock_delete):
            mock_swift.get_account.return_value = account
            mock_swift.get_container.side_effect = _get_container

            sa.delete_resources(force=True)
            mock_swift.get_account.assert_called_once_with()
            mock_delete.assert_called_once_with({'name': 'private'},
                                                ['fake-object1'])

    def test_delete_container(self):
        sa = archiver.SwiftArchiver(resources=PROJECT_RESOURCE)
        container = {'name': 'private'}
        obj1 = {'name': 'object1'}
        obj2 = {'name': 'object2'}
        objects = [obj1, obj2]

        with mock.patch.object(sa, 's_client') as mock_swift:
            sa._delete_container(container, objects)
            delete_calls = [mock.call(container['name'], obj1['name']),
                            mock.call(container['name'], obj2['name'])]
            mock_swift.delete_object.assert_has_calls(delete_calls)
            mock_swift.delete_container.assert_called_once_with(
                container['name'])


@mock.patch('nectar_tools.auth.get_session', new=mock.Mock())
class DesignateArchiverTests(test.TestCase):

    def test_delete_resources(self):
        da = archiver.DesignateArchiver(resources=PROJECT_RESOURCE)
        with test.nested(
            mock.patch.object(da, 'd_client'),
            mock.patch.object(da, '_delete_zone'),
        ) as (mock_designate, mock_delete):
            da.delete_resources()
            mock_delete.assert_not_called()

    def test_delete_resources_force(self):
        da = archiver.DesignateArchiver(resources=PROJECT_RESOURCE)
        zone1 = fakes.FakeZone(id='fake1')
        zone2 = fakes.FakeZone(id='fake2')
        zones = [zone1, zone2]
        with test.nested(
            mock.patch.object(da, 'd_client'),
            mock.patch.object(da, '_delete_zone'),
        ) as (mock_designate, mock_delete):
            mock_designate.zones.list.return_value = zones
            da.delete_resources(force=True)
            mock_designate.zones.list.assert_called_once_with()
            mock_delete.assert_has_calls([mock.call(zone1),
                                          mock.call(zone2)])
            self.assertEqual(mock_delete.call_count, 2)

    def test_clean_zone_name(self):
        da = archiver.DesignateArchiver(resources=PROJECT_RESOURCE)
        for pname, zname in fakes.ZONE_SANITISING:
            zone_name = da._clean_zone_name(pname)
            self.assertEqual(zone_name, zname)

    def test_create_resources(self):
        da = archiver.DesignateArchiver(resources=PROJECT_RESOURCE)
        with test.nested(
            mock.patch.object(da, 'd_client'),
            mock.patch.object(da, '_create_zone'),
        ) as (mock_designate, mock_create):
            mock_designate.zones.get.side_effect = designate_exc.NotFound()
            da.create_resources()
            mock_create.called_once_with()

    def test_create_resources_exists(self):
        da = archiver.DesignateArchiver(resources=PROJECT_RESOURCE)
        with test.nested(
            mock.patch.object(da, 'd_client'),
            mock.patch.object(da, '_create_zone'),
        ) as (mock_designate, mock_create):
            mock_designate.zones.get.return_value = fakes.FakeZone()
            mock_create.assert_not_called()

    def test_create_zone(self):
        da = archiver.DesignateArchiver(resources=PROJECT_RESOURCE)
        with test.nested(
            mock.patch.object(da, 'd_client'),
            mock.patch.object(da, '_clean_zone_name'),
        ) as (mock_designate, mock_clean_zone_name):
            mock_clean_zone_name.return_value = fakes.ZONE['name']
            mock_designate.zone_transfers.create_request.return_value = \
                fakes.ZONE_CREATE_TRANSFER
            mock_designate.zone_transfers.accept_request.return_value = \
                fakes.ZONE_ACCEPT_TRANSFER

            da._create_zone(fakes.ZONE['name'])

            mock_designate.zones.create.assert_called_once_with(
                'myproject.example.com.', email=CONF.designate.zone_email)

            mock_designate.zone_transfers.create_request.\
                assert_called_once_with(fakes.ZONE['name'], PROJECT.id)

            mock_designate.zone_transfers.accept_request.\
                assert_called_once_with(fakes.ZONE_CREATE_TRANSFER['id'],
                                        fakes.ZONE_CREATE_TRANSFER['key'])


@mock.patch('nectar_tools.auth.get_session', new=mock.Mock())
class ImageArchiverTests(test.TestCase):

    def test_delete_resource(self):
        image = fakes.FakeImage(visibility='private', owner='123')
        project = fakes.FakeProject(project_id='123')
        ia = archiver.ImageArchiver(
            resources={'project': project, 'image': image})
        with mock.patch.object(ia, 'g_client') as mock_image:
            ia.delete_resource(force=True)
            mock_image.images.delete.assert_called_once_with(image.id)

    def test_delete_resource_not_ready(self):
        image = fakes.FakeImage(visibility='public', owner='123')
        project = fakes.FakeProject(project_id='123')
        ia = archiver.ImageArchiver(
            resources={'project': project, 'image': image})
        with mock.patch.object(ia, 'g_client') as mock_image:
            ia.delete_resource(force=True)
            mock_image.delete.assert_not_called()

    def test_restrict_resource(self):
        image = fakes.FakeImage(visibility='public', owner='123')
        project = fakes.FakeProject(project_id='123')
        ia = archiver.ImageArchiver(
            resources={'project': project, 'image': image})
        with mock.patch.object(ia, 'g_client') as mock_image:
            ia.restrict_resource()
            mock_image.images.update.assert_called_once_with(
                visibility='private')

    def test_restrict_resource_not_ready(self):
        image = fakes.FakeImage(visibility='private', owner='123')
        project = fakes.FakeProject(project_id='123')
        ia = archiver.ImageArchiver(
            resources={'project': project, 'image': image})
        with mock.patch.object(ia, 'g_client') as mock_image:
            ia.restrict_resource()
            mock_image.images.update.assert_not_called()


@mock.patch('nectar_tools.auth.get_session', new=mock.Mock())
class ResourcerArchiverTests(test.TestCase):

    def test_init(self):
        ra = archiver.ResourceArchiver(resources=RESOURCES,
                                       archivers=['nova', 'cinder', 'image'])
        self.assertEqual(3, len(ra.archivers))
        self.assertIs(archiver.NovaArchiver, type(ra.archivers[0]))
        self.assertIs(archiver.CinderArchiver, type(ra.archivers[1]))
        self.assertIs(archiver.ImageArchiver, type(ra.archivers[2]))
