import datetime
import logging

import placementclient

from nectar_tools.audit.metric import base
from nectar_tools import auth


LOG = logging.getLogger(__name__)


class ResourceProviderAuditor(base.ResourceAuditor):

    def setup_clients(self):
        super().setup_clients()
        self.p_client = auth.get_placement_client(sess=self.ks_session)

    def ensure_site(self):
        resources = self.g_client.resource.search(
            resource_type='resource_provider',
            query='site=null')

        domain_site_mapping = {
            'monash.edu.au': 'monash',
            'melbourne.nectar.org.au': 'melbourne',
            'unimelb.edu.au': 'melbourne',
            'qld.nectar.org.au': 'QRIScloud',
            'auckland': 'auckland',
            'intersect': 'intersect',
            'tpac.org.au': 'tasmania',
            'mgmt.sut': 'swinburne',
            'test.rc.nectar.org.au': 'coreservices',
        }

        for rp in resources:
            LOG.info("Processing %s", rp['name'])
            old_resources = self.g_client.resource.search(
                resource_type='resource_provider',
                query="site!=null and name='%s'" % rp['name'])
            if old_resources:
                LOG.warn("Recreated resource providers found %s",
                         rp['name'])
                if self.repair:
                    resource_data = {'site': old_resources[0]['site']}
                    scope = old_resource[0].get('scope')
                    if scope:
                        resource_data['scope'] = scope
                    for old in old_resources:
                        LOG.info("Deleting old RP %s", old['id'])
                        self.g_client.resource.delete(old['id'])
                    self.g_client.resource.update(
                        resource_type='resource_provider',
                        resource_id=rp['id'],
                        resource=resource_data)
            else:
                for domain_search, site in domain_site_mapping.items():
                    if domain_search in rp['name']:
                        if self.repair:
                            self.g_client.resource.update(
                                resource_type='resource_provider',
                                resource_id=rp['id'], resource={'site': site})
                            LOG.info("Set %s to %s", rp['name'], site)
                        else:
                            LOG.info("No site set for %s should be %s",
                                     rp['name'], site)
                        break
                else:
                    LOG.info("No old resource_provider so don't know which "
                             "site to assign to fix with: "
                             "gnocchi resource update "
                             "--type resource_provider "
                             "-a 'site:<site>' %s", rp['id'])

    def ensure_exists(self):
        now = datetime.datetime.now()
        resources = self.g_client.resource.search(
            resource_type='resource_provider', query='ended_at=null')
        for resource in resources:
            try:
                self.p_client.resource_providers.get(resource['id'])
            except placementclient.exceptions.NotFound:
                LOG.warn("Resource provider %s no longer exists",
                         resource['name'])
                if self.repair:
                    self.g_client.resource.update(
                        resource_type='resource_provider',
                        resource_id=resource['id'],
                        resource={'ended_at': str(now)})
                    LOG.info("Marked resource provider %s as ended",
                             resource['name'])

    def ensure_scope(self):
        resources = self.g_client.resource.search(
            resource_type='resource_provider',
            query='scope=null and ended_at=null')
        for rp in resources:
            LOG.info("Resource provider %s has no scope set. Scope should "
                     "be set to \"local\" or \"national\". Fix with: "
                     "gnocchi resource update --type resource_provider "
                     "-a 'scope:<local_or_national>' %s",
                     rp['name'], rp['id'])
