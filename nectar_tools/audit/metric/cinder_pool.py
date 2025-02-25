import logging

from nectar_tools.audit import common
from nectar_tools.audit.metric import base


LOG = logging.getLogger(__name__)


class CinderPoolAuditor(base.ResourceAuditor):
    def ensure_site(self):
        resources = self.g_client.resource.search(
            resource_type='cinder_pool', query='site=null'
        )

        for cinder_pool in resources:
            az = cinder_pool['availability_zone']
            LOG.error(
                "Cinder Pool %s with az %s has no site",
                cinder_pool['original_resource_id'],
                az,
            )
            site = common.AZ_SITE_MAP.get(az)
            id = cinder_pool['id']
            if site:
                self.repair(
                    f"Setting site for {id} and az={az} to {site}",
                    lambda: self.g_client.resource.update(
                        resource_type='cinder_pool',
                        resource_id=id,
                        resource={'site': site},
                    ),
                )
            else:
                LOG.info(
                    "To fix with: "
                    "gnocchi resource update "
                    "--type cinder_pool "
                    "-a 'site:<site>' %s",
                    cinder_pool['id'],
                )
