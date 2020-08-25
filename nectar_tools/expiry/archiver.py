import logging
import re

from designateclient import exceptions as designate_exc

from nectar_tools import auth
from nectar_tools import config
from nectar_tools import utils


EXPIRY_METADATA_KEY = 'expiry_locked'
ARCHIVE_ATTEMPTS = 10
CONF = config.CONFIG
LOG = logging.getLogger(__name__)


class Archiver(object):

    def __init__(self, ks_session=None, dry_run=False):
        self.k_client = auth.get_keystone_client(ks_session)
        self.g_client = auth.get_glance_client(ks_session)
        self.dry_run = dry_run
        self.ks_session = ks_session

    def is_archive_successful(self):
        return True

    def zero_quota(self):
        raise NotImplementedError

    def reset_quota(self):
        raise NotImplementedError

    def stop_resources(self):
        raise NotImplementedError

    def start_resources(self):
        raise NotImplementedError

    def archive_resources(self):
        raise NotImplementedError

    def delete_resources(self, force=False):
        raise NotImplementedError

    def delete_archives(self):
        raise NotImplementedError

    def enable_resources(self):
        raise NotImplementedError

    def create_resources(self):
        raise NotImplementedError


class ImageArchiver(Archiver):

    def __init__(self, image, ks_session=None, dry_run=False):
        super(ImageArchiver, self).__init__(ks_session, dry_run)
        self.image = image

    def _delete_image(self, image):
        LOG.debug("Found image %s", image.id)

        if image.protected:
            self._unprotect_image(image)

        if not self.dry_run:
            LOG.info("Deleting image %s", image.id)
            self.g_client.images.delete(image.id)
        else:
            LOG.info("Would delete image %s", image.id)

    def _restrict_image(self, image):
        LOG.debug("Found image %s", image.id)

        if image.protected:
            LOG.warn("Can't restrict protected image %s", image.id)
            return
        else:
            if image.visibility != 'private':
                if not self.dry_run:
                    LOG.info("Making image %s private", image.id)
                    self.g_client.images.update(
                        image.id, visibility='private')
                else:
                    LOG.info("Would make image %s private", image.id)
            else:
                LOG.info("Image %s was already private", image.id)

    def _hide_image(self, image):
        LOG.debug("Found image %s", image.id)

        if image.protected:
            self._unprotect_image(image)

        if image.os_hidden is False:
            if not self.dry_run:
                LOG.info("Making image %s hidden", image.id)
                self.g_client.images.update(
                    image.id, os_hidden=True)
            else:
                LOG.info("Would make image %s hidden", image.id)
        else:
            LOG.info("Image %s was already hidden", image.id)

    def _unhide_image(self, image):
        LOG.debug("Found image %s", image.id)

        if image.protected:
            self._unprotect_image(image)

        if image.os_hidden is True:
            if not self.dry_run:
                LOG.info("Making image %s unhidden", image.id)
                self.g_client.images.update(
                    image.id, os_hidden=False)
            else:
                LOG.info("Would make image %s unhidden", image.id)
        else:
            LOG.info("Image %s was already unhidden", image.id)

    def _unprotect_image(self, image):
        LOG.debug("Unprotected image %s", image.id)
        if not self.dry_run:
            LOG.info("Making image %s unprotected", image.id)
            self.g_client.images.update(image.id, protected=False)
        else:
            LOG.info("Would make image %s unprotected", image.id)

    def delete_resources(self, force=False):
        if not force:
            return
        self._delete_image(self.image)

    def restrict_resources(self):
        self._restrict_image(self.image)

    def stop_resources(self):
        self._hide_image(self.image)

    def start_resources(self):
        self._unhide_image(self.image)


class NovaArchiver(Archiver):

    def __init__(self, project, ks_session=None, dry_run=False):
        super(NovaArchiver, self).__init__(ks_session, dry_run)
        self.n_client = auth.get_nova_client(self.ks_session)
        self.project = project
        self.images = None
        self.instances = None

    def is_archive_successful(self):
        instances = self._all_instances()

        if len(instances) == 0:
            return True

        LOG.debug('Found %d instances', len(instances))

        project_archive_success = True

        for instance in instances:
            if not self._instance_has_archive(instance):
                project_archive_success = False
        return project_archive_success

    def _instance_has_archive(self, instance):
        LOG.debug('Checking instance: %s (%s)',
                  instance.id, instance.status)
        task_state = getattr(instance, 'OS-EXT-STS:task_state')
        if task_state in ['image_snapshot_pending',
                          'image_snapshot', 'image_pending_upload']:
            return False
        image = self._get_image_by_instance_id(instance.id)
        if image:
            if image.status == 'active':
                LOG.info('%s: Instance %s archived successfully',
                         self.project.id, instance.id)
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
        LOG.debug("%s: Zero nova quota", self.project.id)

    def stop_resources(self):
        instances = self._all_instances()
        for instance in instances:
            self._lock_instance(instance)
            self._stop_instance(instance)

    def archive_resources(self):
        instances = self._all_instances()
        for instance in instances:
            if self._instance_has_archive(instance):
                self._delete_instance(instance)
            else:
                self._archive_instance(instance)

    def delete_resources(self, force=False):
        instances = self._all_instances()
        for instance in instances:
            if force or self._instance_has_archive(instance):
                self._delete_instance(instance)
            else:
                LOG.warning("Instance %s has no archive", instance.id)

    def enable_resources(self):
        instances = self._all_instances()
        for instance in instances:
            # Don't unlock security locked instances
            security = instance.metadata.get('security_ticket')
            expiry_locked = instance.metadata.get(EXPIRY_METADATA_KEY)
            if not security and expiry_locked:
                self._unlock_instance(instance)

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

    def _all_instances(self):
        if self.instances is None:
            instances = []
            marker = None
            opts = {"all_tenants": True,
                    'tenant_id': self.project.id}

            while True:
                if marker:
                    opts["marker"] = marker
                result = self.n_client.servers.list(search_opts=opts)
                if not result:
                    break
                instances.extend(result)
                marker = instances[-1].id

            self.instances = instances
        return self.instances

    def _archive_instance(self, instance):
        # Increment the archive attempt counter
        attempts = int(instance.metadata.get('archive_attempts', 0))
        if attempts >= ARCHIVE_ATTEMPTS:
            LOG.debug('Limit reached for archive attempts of instance %s',
                      instance.id)
            return

        set_attempts = attempts + 1
        task_state = getattr(instance, 'OS-EXT-STS:task_state')
        vm_state = getattr(instance, 'OS-EXT-STS:vm_state')

        if instance.status in ('ERROR', 'BUILD'):
            host = getattr(instance, 'OS-EXT-SRV-ATTR:host')
            if not host:
                LOG.info("Instance %s in %s and no host", instance.id,
                         instance.status)
                self._delete_instance(instance)
                return
            LOG.debug("%s: Can't snapshot %s due to instance status %s",
                      self.project.id, instance.id, instance.status)
            return

        if instance.status == 'DELETED' or task_state == 'deleting':
            self._delete_instance(instance)
            return

        if instance.status == 'ACTIVE':
            # Instance should be stopped when moving into suspended status
            # but we can stop for now and start archiving next run
            LOG.warn("%s: Instance %s is running, expected it to be stopped",
                     self.project.id, instance.id)
            self._stop_instance(instance)
            return

        if task_state in ['suspending', 'image_snapshot_pending',
                          'image_snapshot', 'image_pending_upload',
                          'image_uploading', 'powering-off', 'powering-on']:
            LOG.debug("%s: Can't snapshot %s due to task_state %s",
                      self.project.id, instance.id, task_state)
            return

        if vm_state in ['stopped', 'suspended', 'paused']:
            # We need to be in stopped, suspended or paused state to
            # create an image
            archive_name = "%s_archive" % instance.id

            if self.dry_run:
                LOG.info("%s: Would create archive %s (attempt %d/%d)",
                         self.project.id, archive_name, set_attempts,
                         ARCHIVE_ATTEMPTS)
            else:
                metadata = {'archive_attempts': str(set_attempts)}
                self.n_client.servers.set_meta(instance.id, metadata)

                try:
                    LOG.info("%s: Creating archive %s (attempt %d/%d)",
                             self.project.id, archive_name, set_attempts,
                             ARCHIVE_ATTEMPTS)
                    image_id = self.n_client.servers.create_image(
                        instance.id, archive_name,
                        metadata={'nectar_archive': 'True'})
                    LOG.info("%s: Archived image id: %s", self.project.id,
                             image_id)
                except Exception as e:
                    LOG.error("%s: Error creating archive: %s",
                              self.project.id, e)
        else:
            # Fail in an unknown state
            LOG.warning("%s: Instance %s is %s (vm_state: %s)",
                        self.project.id, instance.id, instance.status,
                        vm_state)

    def _stop_instance(self, instance):
        task_state = getattr(instance, 'OS-EXT-STS:task_state')
        vm_state = getattr(instance, 'OS-EXT-STS:vm_state')

        if instance.status == 'SHUTOFF':
            LOG.debug("Instance %s already SHUTOFF", instance.id)
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
            LOG.info("Instance %s is %s (task_state=%s vm_state=%s)",
                     instance.id, instance.status, task_state, vm_state)

    def _lock_instance(self, instance):
        if self.dry_run:
            LOG.info("Instance %s would be locked", instance.id)
        else:
            self.n_client.servers.lock(instance.id)
            if instance.status != "ERROR":
                self.n_client.servers.set_meta(instance.id,
                                               {EXPIRY_METADATA_KEY: 'True'})
            LOG.info("%s: Locked instance %s", self.project.id, instance.id)

    def _unlock_instance(self, instance):
        if not instance.locked:
            return
        if self.dry_run:
            LOG.info("Instance %s would be unlocked", instance.id)
        else:
            self.n_client.servers.unlock(instance.id)
            self.n_client.servers.delete_meta(instance.id,
                                              [EXPIRY_METADATA_KEY])
            LOG.info("%s: Unlocked instance %s", self.project.id, instance.id)

    def _delete_instance(self, instance):
        if self.dry_run:
            LOG.info("%s: Would delete instance: %s",
                     self.project.id, instance.id)
        else:
            LOG.info("%s: Deleting instance: %s",
                     self.project.id, instance.id)
            self.n_client.servers.delete(instance.id)

    def _get_image_by_instance_id(self, instance_id):
        """Get an archive image by instance_id """
        image_name = '%s_archive' % instance_id
        images = self._get_project_images()
        for image in images:
            if image.name == image_name:
                return image

    def _get_project_images(self):
        if self.images is None:
            images = [i for i in self.g_client.images.list(
                filters={'owner_id': self.project.id,
                         'nectar_archive': 'True'})]
            self.images = images
        return self.images


class ZoneInstanceArchiver(NovaArchiver):

    def __init__(self, project, ks_session=None, dry_run=False):
        super(ZoneInstanceArchiver, self).__init__(project, ks_session,
                                                   dry_run)
        self.a_client = auth.get_allocation_client(ks_session)
        self.allocation = self.a_client.allocations.get(
            project.allocation_id)

    def _all_instances(self):
        instances = utils.get_out_of_zone_instances(
            self.ks_session, self.allocation, self.project)
        return instances

    def _get_project_images(self):
        if self.images is None:
            instances = self._all_instances()
            archived_images = []
            for instance in instances:
                images = self.g_client.images.list(
                    filters={'owner_id': self.project.id,
                             'nectar_archive': 'True',
                             'instance_uuid': instance.id})
                archived_images.extend(images)
            self.images = archived_images
        return self.images


class CinderArchiver(Archiver):

    def __init__(self, project, ks_session=None, dry_run=False):
        super(CinderArchiver, self).__init__(ks_session, dry_run)
        self.c_client = auth.get_cinder_client(ks_session)
        self.project = project
        self.volumes = None

    def delete_resources(self, force=False):
        if not force:
            return

        volumes = self._all_volumes()
        for volume in volumes:
            self._delete_volume(volume)

    def _all_volumes(self):
        if self.volumes is None:
            opts = {'all_tenants': True,
                    'project_id': self.project.id}
            volumes = self.c_client.volumes.list(search_opts=opts)
            volumes = [v for v in volumes if
                       getattr(v, 'os-vol-tenant-attr:tenant_id')
                       == self.project.id]
            self.volumes = volumes
        return self.volumes

    def _delete_volume(self, volume):
        if self.dry_run:
            LOG.info("%s: Would delete volume: %s",
                     self.project.id, volume.id)
        else:
            LOG.info("%s: Deleting volume: %s", self.project.id, volume.id)
            self.c_client.volumes.delete(volume.id, cascade=True)


class NeutronBasicArchiver(Archiver):

    def __init__(self, project, ks_session=None, dry_run=False):
        super(NeutronBasicArchiver, self).__init__(ks_session, dry_run)
        self.ne_client = auth.get_neutron_client(ks_session)
        self.project = project

    def zero_quota(self):
        body = {'quota': {'port': 0,
                          'security_group': 0,
                          'security_group_rule': 0,
                          'floatingip': 0,
                          'router': 0,
                          'network': 0,
                          'subnet': 0,
                      }
        }

        if not self.dry_run:
            self.ne_client.update_quota(self.project.id, body)
        LOG.debug("%s: Zero neutron quota", self.project.id)

    def delete_resources(self, force=False):
        # Because we can't archive only delete when forced
        if not force:
            return

        self._delete_neutron_resources('security_groups',
                                       self.ne_client.list_security_groups,
                                       self.ne_client.delete_security_group)

    def _delete_neutron_resources(self, name, list_method, delete_method,
                                  list_args={}, log_name=None):
        if not log_name:
            log_name = name
        resources = list_method(tenant_id=self.project.id, **list_args)[name]
        LOG.debug("%s: Found %s %s",
                  self.project.id, len(resources), log_name)
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

        self._delete_neutron_resources('floatingips',
                                       self.ne_client.list_floatingips,
                                       self.ne_client.delete_floatingip)
        self._delete_routers()

        self._delete_neutron_resources('ports',
                                       self.ne_client.list_ports,
                                       self.ne_client.delete_port)

        super(NeutronArchiver, self).delete_resources(force=force)

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
            body = {'router': {'routes': None}}
            self.ne_client.update_router(router['id'], body)
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


class OctaviaArchiver(Archiver):

    def __init__(self, project, ks_session=None, dry_run=False):
        super().__init__(ks_session, dry_run)
        self.lb_client = auth.get_openstacksdk(ks_session).load_balancer
        self.project = project

    def zero_quota(self):
        if not self.dry_run:
            LOG.info("%s: Zero octavia quota", self.project.id)
            self.lb_client.delete_quota(self.project.id)
        else:
            LOG.info("%s: Would zero octavia quota", self.project.id)

    def delete_resources(self, force=False):
        if not force:
            return
        lbs = self.lb_client.load_balancers(project_id=self.project.id)
        for lb in lbs:
            if not self.dry_run:
                LOG.info("%s: Deleting LB %s", self.project.id, lb.id)
                self.lb_client.delete_load_balancer(lb, cascade=True)
            else:
                LOG.info("%s: Would delete LB %s", self.project.id, lb.id)


class ProjectImagesArchiver(ImageArchiver):

    def __init__(self, project, ks_session=None, dry_run=False):
        Archiver.__init__(self, ks_session, dry_run)
        self.project = project

    def delete_resources(self, force=False):
        if not force:
            return

        images = list(self.g_client.images.list(
            filters={'owner': self.project.id}))
        for image in images:
            if image.visibility != 'private':
                LOG.warn("Can't delete image %s visibility=%s",
                         image.id, image.visibility)
            else:
                self._delete_image(image)

    def restrict_resources(self, force=False):
        if not force:
            return
        images = list(self.g_client.images.list(
            filters={'owner': self.project.id}))
        for image in images:
            self._restrict_image(image)

    def stop_resources(self):
        raise NotImplementedError


class SwiftArchiver(Archiver):

    SWIFT_QUOTA_KEY = 'x-account-meta-quota-bytes'

    def __init__(self, project, ks_session=None, dry_run=False):
        super(SwiftArchiver, self).__init__(ks_session, dry_run)
        self.project = project
        self.s_client = auth.get_swift_client(
            ks_session, project_id=self.project.id)

    def zero_quota(self):
        if not self.dry_run:
            self.s_client.post_account(
                headers={SwiftArchiver.SWIFT_QUOTA_KEY: 0})
        LOG.debug("%s: Zero swift quota", self.project.id)

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
                LOG.debug("%s: Deleting object %s/%s", self.project.id,
                          container['name'], obj['name'])
                try:
                    self.s_client.delete_object(container['name'], obj['name'])
                except Exception:
                    LOG.info("%s: Failed to delete object %s/%s",
                             self.project.id, container['name'], obj['name'])
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


class DesignateArchiver(Archiver):

    def __init__(self, project, ks_session=None, dry_run=False):
        super(DesignateArchiver, self).__init__(ks_session, dry_run)
        self.project = project
        if not dry_run:
            self.d_client = auth.get_designate_client(
                ks_session, project_id=self.project.id)

    def delete_resources(self, force=False):
        if not force:
            return

        zones = self.d_client.zones.list()
        for zone in zones:
            self._delete_zone(zone)

    def _delete_zone(self, zone):
        if self.dry_run:
            LOG.info("%s: Would delete zone: %s", self.project.id, zone.id)
        else:
            LOG.info("%s: Deleting zone: %s", self.project.id, zone.id)
            self.d_client.zones.delete(zone['id'])

    def _clean_zone_name(self, name):
        name = name.lower()
        name = name.replace('_', '-')  # convert all underscores to dashes
        name = re.sub(r'[^a-z0-9-]+', '', name)  # only alpha-numeric & dashes
        name = re.sub(r'(-)\1+', r'\1', name)  # remove duplicate dashes
        name = re.sub(r'^[^a-z0-9]', '', name)  # no leading dash
        name = name[:62]  # limit to 62 chars
        name = re.sub(r'[^a-z0-9]$', '', name)  # no trailing dash
        return name

    def create_resources(self):
        if self.dry_run:
            if self.project:
                LOG.info("%s: Would create designate zone", self.project.id)
            else:
                LOG.info("Would create designate zone for project")
        else:
            sub_name = self._clean_zone_name(self.project.name)
            zone_name = "%s.%s" % (sub_name, CONF.designate.user_domain)

            try:
                self.d_client.zones.get(zone_name)
                LOG.debug("%s: Zone already exists: %s", self.project.id,
                         zone_name)
            except designate_exc.NotFound:
                self._create_zone(zone_name)

    def _create_zone(self, name):
        if self.dry_run:
            LOG.info("%s: Would create designate zone %s", self.project.id,
                     name)
        else:
            self.d_client.session.sudo_project_id = None  # admin
            LOG.debug("%s: Creating new zone %s", self.project.id, name)
            try:
                zone = self.d_client.zones.get(name)
            except designate_exc.NotFound:
                zone = self.d_client.zones.create(
                    name, email=CONF.designate.zone_email)

            LOG.debug("%s: Transferring zone %s to project", self.project.id,
                      zone['name'])
            create_req = self.d_client.zone_transfers.create_request(
                name, self.project.id)

            self.d_client.session.sudo_project_id = self.project.id  # noadmin
            accept_req = self.d_client.zone_transfers.accept_request(
                create_req['id'], create_req['key'])

            if accept_req['status'] == 'COMPLETE':
                LOG.info("%s: Zone %s transfer to project %s is complete",
                         self.project.id, zone['name'], self.project.id)
                return zone
            else:
                LOG.error("%s: Zone %s transfer to project %s is: %s",
                          self.project.id, zone['name'], self.project.id,
                          accept_req['status'])


class MagnumArchiver(Archiver):

    def __init__(self, project, ks_session=None, dry_run=False):
        super().__init__(ks_session, dry_run)
        self.project = project
        self.m_client = auth.get_magnum_client(ks_session)

    def delete_resources(self, force=False):
        if not force:
            return

        clusters = self.m_client.clusters.list(detail=True)
        for cluster in clusters:
            if cluster.project_id == self.project.id:
                if self.dry_run:
                    LOG.info("%s: Would delete COE cluster %s",
                             self.project.id, cluster.uuid)
                else:
                    LOG.info("%s: Deleting COE cluster %s",
                             self.project.id, cluster.uuid)
                    self.m_client.clusters.delete(cluster)


class ResourceArchiver(object):

    def __init__(self, project, archivers, ks_session=None, dry_run=False):
        enabled = []
        # project scope archiver, could be multiple archivers
        # Ordering here can matter (eg. octavia goes before neutron)
        if 'magnum' in archivers:
            enabled.append(MagnumArchiver(project, ks_session, dry_run))
        if 'nova' in archivers:
            enabled.append(NovaArchiver(project, ks_session, dry_run))
        if 'zoneinstance' in archivers:
            enabled.append(ZoneInstanceArchiver(project, ks_session, dry_run))
        if 'cinder' in archivers:
            enabled.append(CinderArchiver(project, ks_session, dry_run))
        if 'octavia' in archivers:
            enabled.append(OctaviaArchiver(project, ks_session, dry_run))
        if 'neutron_basic' in archivers:
            enabled.append(NeutronBasicArchiver(project, ks_session, dry_run))
        if 'neutron' in archivers:
            enabled.append(NeutronArchiver(project, ks_session, dry_run))
        if 'projectimages' in archivers:
            enabled.append(ProjectImagesArchiver(project, ks_session, dry_run))
        if 'swift' in archivers:
            enabled.append(SwiftArchiver(project, ks_session, dry_run))
        if 'designate' in archivers:
            enabled.append(DesignateArchiver(project, ks_session, dry_run))
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

    def reset_quota(self):
        for archiver in self.archivers:
            try:
                archiver.reset_quota()
            except NotImplementedError:
                continue

    def start_resources(self):
        for archiver in self.archivers:
            try:
                archiver.start_resources()
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

    def create_resources(self):
        for archiver in self.archivers:
            try:
                archiver.create_resources()
            except NotImplementedError:
                continue

    def restrict_resources(self):
        for archiver in self.archivers:
            try:
                archiver.restrict_resources()
            except NotImplementedError:
                continue
