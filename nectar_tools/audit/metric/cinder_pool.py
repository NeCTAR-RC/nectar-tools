import logging


from nectar_tools.audit.metric import base


LOG = logging.getLogger(__name__)


class CinderPoolAuditor(base.ResourceAuditor):

    def ensure_site(self):
        resources = self.g_client.resource.search(
            resource_type='cinder_pool',
            query='site=null')

        for cinder_pool in resources:
            LOG.error("Cinder Pool %s has no site",
                      cinder_pool['original_resource_id'])
            LOG.info(cinder_pool['availability_zone'])
            LOG.info("To fix with: "
                     "gnocchi resource update "
                     "--type cinder_pool "
                     "-a 'site:<site>' %s", cinder_pool['id'])
