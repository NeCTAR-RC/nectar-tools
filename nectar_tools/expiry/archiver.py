import logging

from nectar_tools import auth


ARCHIVE_ATTEMPTS = 10
LOG = logging.getLogger(__name__)


class Archiver(object):

    def __init__(self, project, ks_session=None, dry_run=False):
        self.k_client = auth.get_keystone_client(ks_session)
        self.g_client = auth.get_glance_client(ks_session)
        self.dry_run = dry_run
        self.project = project
        self.ks_session = ks_session

    def is_archive_successful(self):
        return True

    def zero_quota(self):
        raise NotImplementedError

    def stop_resources(self):
        raise NotImplementedError

    def archive_resources(self):
        raise NotImplementedError

    def delete_resources(self, force=False):
        raise NotImplementedError

    def delete_archives(self):
        raise NotImplementedError

    def enable_resources(self):
        raise NotImplementedError


class NovaArchiver(Archiver):

    def __init__(self, project, ks_session=None, dry_run=False):
        super(NovaArchiver, self).__init__(project, ks_session, dry_run)
        self.n_client = auth.get_nova_client(self.ks_session)
        self.images = None
        self.servers = None

    def is_archive_successful(self):
        instances = self.all_servers()

        if len(instances) == 0:
            return True

        LOG.debug('Found %d instances', len(instances))

        project_archive_success = True

        for instance in instances:
            if not self.instance_has_archive(instance):
                project_archive_success = False
        return project_archive_success

    def instance_has_archive(self, instance):
        LOG.debug('Checking instance: %s (%s)',
                  instance.id, instance.status)
        task_state = getattr(instance, 'OS-EXT-STS:task_state')
        if task_state in ['image_snapshot_pending',
                          'image_snapshot', 'image_pending_upload']:
            return False
        image = self.get_image_by_instance_id(instance.id)
        if image:
            if image.status == 'active':
                LOG.info('%s: Instance %s archived successfully',
                         self.project.id, instance.id)
                if not image.get('nectar_archive'):
                    LOG.debug('Setting nectar_archive property on image: %s',
                              image.id)
                    self.g_client.images.update(image.id,
                                                nectar_archive='True')
                return True
            elif image.status in ['queued', 'saving']:
                LOG.info("Archiving in progress (%s) for %s (image: %s)",
                         image.status, instance.id, image.id)
                return False
            else:
                LOG.warning('Image found with status: %s', image.status)
                return False

        LOG.debug('Archive for instance %s not found', instance.id)
        return False

    def zero_quota(self):
        if not self.dry_run:
            self.n_client.quotas.update(tenant_id=self.project.id,
                                        ram=0,
                                        instances=0,
                                        cores=0,
                                        force=True)
        LOG.info("%s: Zero nova quota", self.project.id)

    def stop_resources(self):
        instances = self.all_servers()
        for instance in instances:
            self.lock_instance(instance)
            self.stop_instance(instance)

    def archive_resources(self):
        instances = self.all_servers()
        for instance in instances:
            if self.instance_has_archive(instance):
                self.delete_instance(instance)
            else:
                self.archive_instance(instance)

    def delete_resources(self, force=False):
        instances = self.all_servers()
        for instance in instances:
            if force or self.instance_has_archive(instance):
                self.delete_instance(instance)
            else:
                LOG.error("Instance %s has no archive", instance.id)
        return instances

    def enable_resources(self):
        instances = self.all_servers()
        for instance in instances:
            # Don't unlock security locked instances?
            self.unlock_instance(instance)

    def delete_archives(self):
        """Delete all image snapshots
        """
        images = self._get_project_images()
        LOG.debug("%s: Found %s instance archive image",
                  self.project.id, len(images))
        for image in images:
            if not self.dry_run:
                self.g_client.images.delete(image.id)
                LOG.info("%s: Deleted image %s", self.project.id, image.id)
            else:
                LOG.info("%s: Would delete image %s(%s)",
                         self.project.id, image.name, image.id)

    def all_servers(self):
        if self.servers is None:
            servers = []
            marker = None
            opts = {"all_tenants": True}
            opts['tenant_id'] = self.project.id

            while True:
                if marker:
                    opts["marker"] = marker
                result = self.n_client.servers.list(search_opts=opts)
                if not result:
                    break
                servers.extend(result)
                marker = servers[-1].id

            self.servers = servers
        return self.servers

    def archive_instance(self, instance):
        # Increment the archive attempt counter
        attempts = int(instance.metadata.get('archive_attempts', 0))
        if attempts >= ARCHIVE_ATTEMPTS:
            LOG.error('Limit reached for archive attempts of instance %s',
                      instance.id)
            return

        set_attempts = attempts + 1
        task_state = getattr(instance, 'OS-EXT-STS:task_state')
        vm_state = getattr(instance, 'OS-EXT-STS:vm_state')

        if instance.status == 'ERROR':
            host = getattr(instance, 'OS-EXT-SRV-ATTR:host')
            if not host:
                LOG.info("Instance %s in error and no host", instance.id)
                self.delete_instance(instance)
                return
            LOG.warn("%s: Can't snapshot %s due to instance status %s",
                     self.project.id, instance.id, instance.status)
            return

        if instance.status == 'DELETED' or task_state == 'deleting':
            self.delete_instance(instance)
            return

        if instance.status == 'ACTIVE':
            # Instance should be stopped when moving into suspended status
            # but we can stop for now and start archiving next run
            LOG.warn("%s: Instance %s is running, expected it to be stopped",
                     self.project.id, instance.id)
            self.stop_instance(instance)
            return

        if task_state in ['suspending', 'image_snapshot_pending',
                          'image_snapshot', 'image_pending_upload',
                          'image_uploading', 'powering-off', 'powering-on']:
            LOG.error("%s: Can't snapshot %s due to task_state %s",
                      self.project.id, instance.id, task_state)
            return

        if vm_state in ['stopped', 'suspended', 'paused']:
            # We need to be in stopped, suspended or paused state to
            # create an image
            archive_name = "%s_archive" % instance.id

            if self.dry_run:
                LOG.info("Would create archive %s (attempt %d/%d)",
                         archive_name, set_attempts, ARCHIVE_ATTEMPTS)
            else:
                metadata = {'archive_attempts': str(set_attempts)}
                self.n_client.servers.set_meta(instance.id, metadata)

                try:
                    LOG.info("Creating archive %s (attempt %d/%d)",
                             archive_name, set_attempts, ARCHIVE_ATTEMPTS)
                    image_id = self.n_client.servers.create_image(
                        instance.id, archive_name,
                        metadata={'nectar_archive': 'True'})
                    LOG.info("Archive image id: %s", image_id)
                except Exception as e:
                    LOG.error("Error creating archive: %s", e)
        else:
            # Fail in an unknown state
            LOG.warning("Instance %s is %s (vm_state: %s)",
                        instance.id, instance.status, vm_state)

    def stop_instance(self, instance):
        task_state = getattr(instance, 'OS-EXT-STS:task_state')
        vm_state = getattr(instance, 'OS-EXT-STS:vm_state')

        if instance.status == 'SHUTOFF':
            LOG.info("Instance %s already SHUTOFF", instance.id)
        elif instance.status == 'ACTIVE':
            if task_state:
                LOG.info("Cannot stop instance %s in task_state=%s",
                         instance.id, task_state)
            else:
                if self.dry_run:
                    LOG.info("Instance %s would be stopped", instance.id)
                else:
                    LOG.info("Stopping instance %s", instance.id)
                    self.n_client.servers.stop(instance.id)
        else:
            task_state = getattr(instance, 'OS-EXT-STS:task_state')
            LOG.info("Instance %s is %s (task_state=%s vm_state=%s)",
                     instance.id, instance.status, task_state, vm_state)

    def lock_instance(self, instance):
        if self.dry_run:
            LOG.info("Instance %s would be locked", instance.id)
        else:
            self.n_client.servers.lock(instance.id)

    def unlock_instance(self, instance):
        if self.dry_run:
            LOG.info("Instance %s would be unlocked", instance.id)
        else:
            self.n_client.servers.unlock(instance.id)

    def delete_instance(self, instance):
        if self.dry_run:
            LOG.info("%s: Would delete instance: %s",
                     self.project.id, instance.id)
        else:
            LOG.info("%s: Deleting instance: %s", self.project.id, instance.id)
            self.n_client.servers.delete(instance.id)

    def get_image_by_instance_id(self, instance_id):
        image_name = '%s_archive' % instance_id
        return self.get_image_by_name(image_name)

    def _get_project_images(self):
        if self.images is None:
            images = [i for i in self.g_client.images.list(
                filters={'owner_id': self.project.id,
                         'nectar_archive': 'True'})]
            self.images = images
        return self.images

    def get_image_by_name(self, image_name):
        """Get an image by a given name """
        images = self._get_project_images()
        image_names = [i.name for i in images]
        if image_name in image_names:
            return [i for i in images if i.name == image_name][0]


class CinderArchiver(Archiver):

    def __init__(self, project, ks_session=None, dry_run=False):
        super(CinderArchiver, self).__init__(project, ks_session, dry_run)
        self.c_client = auth.get_cinder_client()
        self.volumes = None

    def zero_quota(self):
        if not self.dry_run:
            self.c_client.quotas.update(tenant_id=self.project.id,
                                        volumes=0,
                                        gigabytes=0,
                                        snapshots=0)
        LOG.info("%s: Zero cinder quota", self.project.id)

    def delete_resources(self, force=False):
        if not force:
            return

        volumes = self._all_volumes()
        for volume in volumes:
            self._delete_volume(volume)
        return volumes

    def _all_volumes(self):
        if self.volumes is None:
            opts = {'all_tenants': True,
                    'project_id': self.project.id}
            volumes = self.c_client.volumes.list(search_opts=opts)
            self.volumes = volumes
        return self.volumes

    def _delete_volume(self, volume):
        if self.dry_run:
            LOG.info("%s: Would delete volume: %s", self.project.id, volume.id)
        else:
            LOG.info("%s: Deleting volume: %s", self.project.id, volume.id)
            self.c_client.volumes.delete(volume.id)


class NeutronBasicArchiver(Archiver):

    def __init__(self, project, ks_session=None, dry_run=False):
        super(NeutronBasicArchiver, self).__init__(project, ks_session,
                                                   dry_run)
        self.ne_client = auth.get_neutron_client()

    def zero_quota(self):
        body = {'quota': {'floatingip': 0,
                          'router': 0,
                          'subnet': 0,
                          'network': 0,
                          'port': 0,
                          'security_group': 0,
                          'security_group_rule': 0}
        }

        if not self.dry_run:
            self.ne_client.update_quota(self.project.id, body)
        LOG.info("%s: Zero neutron quota", self.project.id)

    def delete_resources(self, force=False):
        # Because we can't archive only delete when forced
        if not force:
            return []

        self._delete_neutron_resources('security_groups',
                                       self.ne_client.list_security_groups,
                                       self.ne_client.delete_security_group)

    def _delete_neutron_resources(self, name, list_method, delete_method,
                                  list_args={}, log_name=None):
        if not log_name:
            log_name = name
        resources = list_method(tenant_id=self.project.id, **list_args)[name]
        LOG.debug("%s: Found %s %s", self.project.id, len(resources), log_name)
        if not resources:
            return
        for r in resources:
            if not self.dry_run:
                delete_method(r['id'])
                LOG.info("%s: Deleted %s %s", self.project.id, log_name,
                         r['id'])
            else:
                LOG.info("%s: Would delete %s %s", self.project.id, log_name,
                         r['id'])


class NeutronArchiver(NeutronBasicArchiver):

    def delete_resources(self, force=False):
        # Because we can't archive only delete when forced
        if not force:
            return []
        super(NeutronArchiver, self).delete_resources(force=force)

        self._delete_neutron_resources('floatingips',
                                       self.ne_client.list_floatingips,
                                       self.ne_client.delete_floatingip)

        self._delete_routers()

        self._delete_neutron_resources('subnets',
                                       self.ne_client.list_subnets,
                                       self.ne_client.delete_subnet)
        self._delete_neutron_resources('networks',
                                       self.ne_client.list_networks,
                                       self.ne_client.delete_network)

    def _delete_routers(self):
        routers = self.ne_client.list_routers(
            tenant_id=self.project.id)['routers']
        LOG.debug("%s: Found %s routers", self.project.id,
                  len(routers))

        for router in routers:
            interfaces = self.ne_client.list_ports(
                device_id=router['id'],
                device_owner='network:router_interface')['ports']
            for interface in interfaces:
                body = {'port_id': interface['id']}
                if not self.dry_run:
                    self.ne_client.remove_interface_router(router['id'], body)
            if not self.dry_run:
                self.ne_client.delete_router(router['id'])
                LOG.info("%s: Deleted router %s", self.project.id,
                         router['id'])
            else:
                LOG.info("%s: Would delete router %s", self.project.id,
                         router['id'])


class GlanceArchiver(Archiver):

    def __init__(self, project, ks_session=None, dry_run=False):
        super(GlanceArchiver, self).__init__(project, ks_session, dry_run)
        self.g_client = auth.get_glance_client(ks_session)

    def delete_resources(self, force=False):
        if not force:
            return

        images = list(self.g_client.images.list(
            filters={'owner': self.project.id}))

        LOG.debug("%s: Found %s images", self.project.id, len(images))

        for image in images:
            if image.visibility == 'private':
                self._delete_image(image)
            else:
                LOG.warn("%s: Can't delete image %s visability=%s",
                         self.project.id, image.id, image.visibility)

    def _delete_image(self, image):
        if not self.dry_run:
            LOG.info("%s: Deleting image %s", self.project.id, image.id)
            self.g_client.images.delete(image.id)
        else:
            LOG.info("%s: Would delete image %s", self.project.id, image.id)


class SwiftArchiver(Archiver):

    SWIFT_QUOTA_KEY = 'x-account-meta-quota-bytes'

    def __init__(self, project, ks_session=None, dry_run=False):
        super(SwiftArchiver, self).__init__(project, ks_session, dry_run)
        self.s_client = auth.get_swift_client(ks_session,
                                              project_id=project.id)

    def zero_quota(self):
        if not self.dry_run:
            self.s_client.post_account(
                headers={SwiftArchiver.SWIFT_QUOTA_KEY: 0})
        LOG.info("%s: Zero swift quota", self.project.id)

    def delete_resources(self, force=False):
        if not force:
            return
        account, containers = self.s_client.get_account()
        for c in containers:
            container_stat, objects = self.s_client.get_container(c['name'])
            if 'x-container-read' in container_stat:
                read_acl = container_stat['x-container-read']
                LOG.warn("%s: Ignoring container %s due to read_acl %s",
                         self.project.id, c['name'], read_acl)
                continue
            self._delete_container(c, objects)

    def _delete_container(self, container, objects):
        for obj in objects:
            if not self.dry_run:
                LOG.info("%s: Deleting object %s/%s", self.project.id,
                         container['name'], obj['name'])
                self.s_client.delete_object(container['name'], obj['name'])
            else:
                LOG.info("%s: Would delete object %s/%s", self.project.id,
                         container['name'], obj['name'])
        if not self.dry_run:
            LOG.info("%s: Deleting container %s", self.project.id,
                     container['name'])
            self.s_client.delete_container(container['name'])
        else:
            LOG.info("%s: Would delete container %s", self.project.id,
                     container['name'])


class ResourceArchiver(object):

    def __init__(self, project, archivers, ks_session=None, dry_run=False):
        enabled = []
        if 'nova' in archivers:
            enabled.append(NovaArchiver(project, ks_session, dry_run))
        if 'cinder' in archivers:
            enabled.append(CinderArchiver(project, ks_session, dry_run))
        if 'neutron_basic' in archivers:
            enabled.append(NeutronBasicArchiver(project, ks_session, dry_run))
        if 'neutron' in archivers:
            enabled.append(NeutronArchiver(project, ks_session, dry_run))
        if 'glance' in archivers:
            enabled.append(GlanceArchiver(project, ks_session, dry_run))
        if 'swift' in archivers:
            enabled.append(SwiftArchiver(project, ks_session, dry_run))
        self.archivers = enabled

    def is_archive_successful(self):
        success = True
        for archiver in self.archivers:
            if not archiver.is_archive_successful():
                success = False
        return success

    def zero_quota(self):
        for archiver in self.archivers:
            try:
                archiver.zero_quota()
            except NotImplementedError:
                continue

    def stop_resources(self):
        for archiver in self.archivers:
            try:
                archiver.stop_resources()
            except NotImplementedError:
                continue

    def archive_resources(self):
        for archiver in self.archivers:
            try:
                archiver.archive_resources()
            except NotImplementedError:
                continue

    def delete_resources(self, force=False):
        for archiver in self.archivers:
            try:
                archiver.delete_resources(force=force)
            except NotImplementedError:
                continue

    def delete_archives(self):
        for archiver in self.archivers:
            try:
                archiver.delete_archives()
            except NotImplementedError:
                continue

    def enable_resources(self):
        for archiver in self.archivers:
            try:
                archiver.enable_resources()
            except NotImplementedError:
                continue
