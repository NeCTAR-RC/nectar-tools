import logging


from nectar_tools.audit import common
from nectar_tools.audit.metric import base


LOG = logging.getLogger(__name__)


class TempestTestAuditor(base.ResourceAuditor):

    def ensure_site(self):
        resources = self.g_client.resource.search(
            resource_type='tempest_test',
            query='site=null and flavor=null')

        for tt in resources:
            az = tt['availability_zone']
            site = common.AZ_SITE_MAP.get(az)

            LOG.error("Tempest Test %s with AZ %s missing site",
                      tt['name'], tt['availability_zone'])
            if site:
                self.repair(f"Setting site for {tt['name']} and az={az} "
                            f"to {site}",
                            lambda: self.g_client.resource.update(
                                resource_type='tempest_test',
                                resource_id=tt['id'],
                                resource={'site': site}))
            else:
                LOG.info("To fix with: "
                         "gnocchi resource update "
                         "--type tempest_test "
                         "-a 'site:<site>' %s", tt['id'])
