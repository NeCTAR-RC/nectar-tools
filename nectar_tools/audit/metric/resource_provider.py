import logging


from nectar_tools.audit.metric import base


LOG = logging.getLogger(__name__)


class ResourceProviderAuditor(base.ResourceAuditor):

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
        }

        for rp in resources:
            LOG.info("Processing %s", rp['name'])
            old_resources = self.g_client.resource.search(
                resource_type='resource_provider',
                query="site!=null and name='%s'" % rp['name'])
            if old_resources:
                site = old_resources[0]['site']
                LOG.info("Site should be %s", site)
                for old in old_resources:
                    LOG.info("Deleting old RP %s", old['id'])
                    self.g_client.resource.delete(old['id'])
                self.g_client.resource.update(
                    resource_type='resource_provider',
                    resource_id=rp['id'],
                    resource={'site': site})
            else:
                for domain_search, site in domain_site_mapping.items():
                    if domain_search in rp['name']:
                        self.g_client.resource.update(
                            resource_type='resource_provider',
                            resource_id=rp['id'], resource={'site': site})
                        LOG.info("Set %s to %s", rp['name'], site)
                        break
                else:
                    LOG.info("No old resource_provider so don't know which "
                             "site to assign to fix with: "
                             "self.g_client resource update "
                             "--type resource_provider"
                             "-a 'site:<site>' %s", rp['id'])
