import logging


from nectar_tools.audit.metric import base


LOG = logging.getLogger(__name__)


class TempestTestAuditor(base.ResourceAuditor):

    def ensure_site(self):
        resources = self.g_client.resource.search(
            resource_type='tempest_test',
            query='site=null and flavor=null')

        for tt in resources:
            LOG.error("Tempest Test %s with AZ %s missing site",
                      tt['name'], tt['availability_zone'])
