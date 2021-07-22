import logging

import glanceclient.exc as glance_exc

from nectar_tools.audit import base
from nectar_tools import auth
from nectar_tools import config


CONF = config.CONFIG
LOG = logging.getLogger(__name__)


class ImageAuditor(base.Auditor):

    def setup_clients(self):
        super().setup_clients()
        self.g_client = auth.get_glance_client(sess=self.ks_session)
        self.n_client = auth.get_nova_client(sess=self.ks_session)
        self.t_client = auth.get_trove_client(sess=self.ks_session)

    def _is_image_unused(self, image_id):
        search_opts = {'image': image_id,
                       'all_tenants': True}
        try:
            instances = self.n_client.servers.list(search_opts=search_opts)
            if not instances:
                return True
            LOG.debug("Image %s is in use by %s instances", image_id,
                     len(instances))
        except Exception as e:
            LOG.error(
                "Image %s: Can't get related instance", image_id)
            LOG.error(e)
        return False

    def _get_images(self, project_id):
        images = list(self.g_client.images.list(
            filters={'owner': project_id}))
        LOG.debug("Found %s images owned by %s", len(images), project_id)
        return images

    def _delete_unused(self, image_id):
        if self.repair:
            LOG.info("Image %s is unused, deleting", image_id)
            try:
                self.g_client.images.delete(image_id)
            except glance_exc.HTTPNotFound:
                LOG.debug('Image is already deleted')
        else:
            LOG.warn("Image %s is unused and can be deleted", image_id)

    def check_octavia_images(self):
        project_id = CONF.octavia.project_id
        images = self._get_images(project_id)
        LOG.debug("Found %s images owned by octavia", len(images))
        for image in images:
            if self._is_image_unused(image.id):
                self._delete_unused(image.id)

    def check_trove_images(self):
        active_images = []
        datastores = self.t_client.datastores.list()
        for datastore in datastores:
            ds_versions = self.t_client.datastore_versions.list(datastore.id)
            for dsv in ds_versions:
                if dsv.active:
                    active_images.append(dsv.image)

        project_id = CONF.trove.project_id
        images = self._get_images(project_id)
        for image in images:
            if image.id not in active_images and self._is_image_unused(
                    image.id):
                self._delete_unused(image.id)
