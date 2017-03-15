
import logging

from nectar_tools import auth


LOG = logging.getLogger(__name__)

ARCHIVE_ATTEMPTS = 10

class Archiver(object):

    def __init__(self, project, dry_run=False):
        self.k_client = auth.get_keystone_client()
        self.g_client = auth.get_glance_client()
        self.dry_run = dry_run
        self.project = project

class NovaArchiver(Archiver):



    def __init__(self, project, dry_run=False):
        super(NovaArchiver, self).__init__(project, dry_run)
        self.n_client = auth.get_nova_client()

    def is_archive_successful(self):
        LOG.debug('\tchecking if archive was successful')
        instances = self.all_servers()

        if len(instances) == 0:
            return True

        LOG.debug('\tfound %d instances' % len(instances))

        project_archive_success = True

        for instance in instances:
            LOG.debug('\tchecking instance: %s (%s)' %
                      (instance.id, instance.status))

            image = self.get_image_by_instance_id(instance.id)
            if image:
                if self.is_image_successful(image):
                    LOG.info('\tinstance %s archived successfully' %
                             instance.id)
                    if not image.properties.get('nectar_archive'):
                        LOG.debug('\tsetting nectar_archive property on image:'
                                  ' %s' % image.id)
                        image.update(properties={'nectar_archive': True})
                elif self.is_image_in_progress(image):
                    LOG.info("\tarchiving in progress (%s) for %s (image: %s)"
                             % (image.status, instance.id, image.id))
                    project_archive_success = False
                else:
                    LOG.warning('\timage found with status: %s' % image.status)
                    project_archive_success = False
            else:
                LOG.debug('\tarchive for instance %s not found' % instance.id)
                project_archive_success = False

        return project_archive_success

    def all_servers(self):
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
        return servers

    def stop_instances(self):
        instances = self.all_servers()
        for instance in instances:
            self.lock_instance(instance)
            self.stop_instance(instance)

    def archive_instances(self):
        instances = self.all_servers()
        for instance in instances:
            self.archive_instance(instance)

    def archive_instance(self, instance):

        # Increment the archive attempt counter
        attempts = int(instance.metadata.get('archive_attempts', 0))
        set_attempts = attempts + 1
        if not self.dry_run:
            LOG.debug("\tsetting archive attempts counter to %d" % set_attempts)
            metadata = {'archive_attempts': str(set_attempts)}
            self.n_client.servers.set_meta(instance.id, metadata)
        else:
            LOG.debug("\twould set archive attempts counter to %d" % set_attempts)

        task_state = getattr(instance, 'OS-EXT-STS:task_state')
        vm_state = getattr(instance, 'OS-EXT-STS:vm_state')

        if instance.status == 'ERROR':
            LOG.error("\tcan't snapshot due to instance status %s"
                      % instance.status)
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
                          'image_snapshot', 'image_pending_upload']:
            LOG.error("\tcan't snapshot due to task_state %s" % task_state)
            return

        if vm_state in ['stopped', 'suspended']:
            # We need to be in stopped or suspended state to create an image
            archive_name = "%s_archive" % instance.id

            if self.dry_run:
                LOG.info("\twould create archive %s (attempt %d/%d)" %
                         (archive_name, set_attempts, ARCHIVE_ATTEMPTS))
            else:
                try:
                    LOG.info("\tcreating archive %s (attempt %d/%d)" %
                             (archive_name, set_attempts, ARCHIVE_ATTEMPTS))
                    image_id = self.n_client.servers.create_image(instance.id,
                                                                  archive_name)
                    LOG.info("\tarchive image id: %s" % image_id)
                except Exception as e:
                    LOG.error("\tError creating archive: %s" % e)
        else:
            # Fail in an unknown state
            LOG.warning("\tinstance %s is %s (vm_state: %s)" %
                        (instance.id, instance.status, vm_state))


    def suspend_instance(self, instance):
        task_state = getattr(instance, 'OS-EXT-STS:task_state')
        bad_task_states = ['migrating']
        if task_state in bad_task_states:
            msg = "\tinstance %s is task_state %s" % (instance.id,
                                                      task_state)
            LOG.info("\t%s" % msg)
            raise ValueError(msg)
        else:
            if self.dry_run:
                LOG.info("\tinstance %s would be suspended" % instance.id)
            else:
                LOG.info("\tsuspending instance %s" % instance.id)
                instance.suspend()


    def stop_instance(self, instance):
        task_state = getattr(instance, 'OS-EXT-STS:task_state')
        vm_state = getattr(instance, 'OS-EXT-STS:vm_state')

        if instance.status == 'SHUTOFF':
            LOG.info("\tinstance %s already SHUTOFF" % instance.id)
        elif instance.status == 'ACTIVE':
            if task_state:
                LOG.info("\tcannot stop instance %s in task_state=%s" %
                         (instance.id, task_state))
            else:
                if self.dry_run:
                    LOG.info("\tinstance %s would be stopped" % instance.id)
                else:
                    LOG.info("\tstopping instance %s" % instance.id)
                    self.n_client.servers.stop(instance.id)
        else:
            task_state = getattr(instance, 'OS-EXT-STS:task_state')
            LOG.info("\tinstance %s is %s (task_state=%s vm_state=%s)" %
                     (instance.id, instance.status, task_state, vm_state))


    def lock_instance(self, instance):
        if self.dry_run:
            LOG.info("\tinstance %s would be locked" % instance.id)
        else:
            self.n_client.servers.lock(instance.id)

    def delete_instance(self, instance):
        if self.dry_run:
            LOG.info("\twould delete instance: %s" % instance.id)
        else:
            LOG.info("\tdeleting instance: %s" % instance.id)
            self.n_client.servers.delete(instance.id)

    def zero_quota(self):
        self.n_client.quotas.update(tenant_id=self.project.id,
                                    ram=0,
                                    instances=0,
                                    cores=0,
                                    force=True)

    def get_image_by_instance_id(self, instance_id):
        image_name = '%s_archive' % instance_id
        return self.get_image_by_name(image_name)

    def get_image_by_name(self, image_name):
        """ Get an image by a given name """
        images = [i for i in self.g_client.images.list(
            filters={'property-owner_id': self.project.id})]
        image_names = [i.name for i in images]
        if image_name in image_names:
            return [i for i in images if i.name == image_name][0]

    def is_image_in_progress(self, image):
        if image.status in ['saving', 'queued']:
            return True
        return False

    def is_image_successful(self, image):
        if image.status == 'active':
            return True
        return False
