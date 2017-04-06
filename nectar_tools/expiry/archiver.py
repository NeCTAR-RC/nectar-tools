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


class NovaArchiver(Archiver):

    def __init__(self, project, ks_session=None, dry_run=False):
        super(NovaArchiver, self).__init__(project, ks_session, dry_run)
        self.n_client = auth.get_nova_client(self.ks_session)
        self.images = None
        self.servers = None

    def is_archive_successful(self):
        LOG.debug('Checking if archive was successful')
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
                LOG.info('Instance %s archived successfully',
                         instance.id)
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
        else:
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
            if self.instance_has_archive(instance) or force:
                self.delete_instance(instance)
            else:
                LOG.error("Instance %s has no archive", instance.id)
        return instances

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
            LOG.error("Can't snapshot due to instance status %s",
                      instance.status)
            return

        if instance.status == 'DELETED' or task_state == 'deleting':
            self.delete_instance(instance)
            return

        if instance.status == 'ACTIVE':
            # Instance should be stopped when moving into suspended status
            # but we can stop for now and start archiving next run
            self.stop_instance(instance)
            return

        if task_state in ['suspending', 'image_snapshot_pending',
                          'image_snapshot', 'image_pending_upload',
                          'image_uploading']:
            LOG.error("Can't snapshot due to task_state %s", task_state)
            return

        if vm_state in ['stopped', 'suspended', 'paused']:
            # We need to be in stopped, suspended or paused state to
            # create an image
            archive_name = "%s_archive" % instance.id

            if not self.dry_run:
                LOG.debug("Setting archive attempts counter to %d",
                          set_attempts)
                metadata = {'archive_attempts': str(set_attempts)}
                self.n_client.servers.set_meta(instance.id, metadata)
            else:
                LOG.debug("Would set archive attempts counter to %d",
                          set_attempts)

            if self.dry_run:
                LOG.info("Would create archive %s (attempt %d/%d)",
                         archive_name, set_attempts, ARCHIVE_ATTEMPTS)
            else:
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

    def is_archive_successful(self):
        pass

    def zero_quota(self):
        if not self.dry_run:
            self.c_client.quotas.update(tenant_id=self.project.id,
                                        volumes=0,
                                        gigabytes=0,
                                        snapshots=0)
        else:
            LOG.info("%s: Zero cinder quota", self.project.id)

    def stop_resources(self):
        pass

    def archive_resources(self):
        pass

    def delete_resources(self, force=False):
        pass

    def delete_archives(self):
        pass


class NeutronArchiver(Archiver):

    def __init__(self, project, ks_session=None, dry_run=False):
        super(NeutronArchiver, self).__init__(project, ks_session, dry_run)
        self.ne_client = auth.get_neutron_client()

    def is_archive_successful(self):
        pass

    def zero_quota(self):
        if not self.dry_run:
            self.ne_client.quotas.update(tenant_id=self.project.id,
                                         volumes=0,
                                         gigabytes=0,
                                         snapshots=0)
        else:
            LOG.info("%s: Zero Neutron quota", self.project.id)

    def stop_resources(self):
        # Disassociate floating IPs?
        # Remove router ports?
        pass

    def archive_resources(self):
        pass

    def delete_resources(self, force=False):
        # Because we can't archive only delete when forced
        if not force:
            return []

        self._delete_neutron_resources('securitygroups',
                                       self.ne_client.list_security_groups,
                                       self.ne_client.delete_security_group)
        #self._delete_neutron_resources('floatingips',
        #                               self.ne_client.list_floatingips,
        #                               self.ne_client.delete_floatingip)

        # Routers
        # Subnets
        # Networks
        pass

    def delete_archives(self):
        pass

    def _delete_neutron_resources(self, name, list_method, delete_method):
        resources = list_method(tenant_id=self.project.id)[name]
        if not resources:
            return
        LOG.debug("%s: Found %s %s", self.project.id, len(resources), name)
        for r in resources:
            if not self.dry_run:
                delete_method(r['id'])
                LOG.info("%s: Deleted %s %s", self.project.id, name, r['id'])
            else:
                LOG.info("%s: Would delete %s %s", self.project.id, name,
                         r['id'])


class ResourceArchiver(object):

    def __init__(self, project, ks_session=None, dry_run=False):
        nova_archiver = NovaArchiver(project, ks_session, dry_run)
        cinder_archiver = CinderArchiver(project, ks_session, dry_run)
        neutron_archiver = NeutronArchiver(project, ks_session, dry_run)
        self.archivers = [nova_archiver, cinder_archiver, neutron_archiver]

    def is_archive_successful(self):
        success = True
        for archiver in self.archivers:
            if not archiver.is_archive_successful():
                success = False
        return success

    def zero_quota(self):
        for archiver in self.archivers:
            archiver.zero_quota()

    def stop_resources(self):
        for archiver in self.archivers:
            archiver.stop_resources()

    def archive_resources(self):
        for archiver in self.archivers:
            archiver.archive_resources()

    def delete_resources(self, force=False):
        for archiver in self.archivers:
            archiver.delete_resources(force=force)

    def delete_archives(self):
        for archiver in self.archivers:
            archiver.delete_archives()
