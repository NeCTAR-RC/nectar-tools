import logging


from nectar_tools.audit.metric import base


LOG = logging.getLogger(__name__)


class ResourceProviderAuditor(base.ResourceAuditor):

    def ensure_site(self):
        resources = self.g_client.resource.search(
            resource_type='resource_provider',
            query='site=null')

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
                if 'monash.edu.au' in rp['name']:
                    self.g_client.resource.update(
                        resource_type='resource_provider',
                        resource_id=rp['id'], resource={'site': 'monash'})
                    LOG.info("Set %s to monash", rp['name'])
                    continue
                if 'melbourne.nectar.org.au' in rp['name']:
                    self.g_client.resource.update(
                        resource_type='resource_provider',
                        resource_id=rp['id'], resource={'site': 'melbourne'})
                    LOG.info("Set %s to melbourne", rp['name'])
                    continue
                if 'unimelb.edu.au' in rp['name']:
                    self.g_client.resource.update(
                        resource_type='resource_provider',
                        resource_id=rp['id'], resource={'site': 'melbourne'})
                    LOG.info("Set %s to melbourne", rp['name'])
                    continue
                if 'qld.nectar.org.au' in rp['name']:
                    self.g_client.resource.update(
                        resource_type='resource_provider',
                        resource_id=rp['id'], resource={'site': 'QRIScloud'})
                    LOG.info("Set %s to QRIScloud", rp['name'])
                    continue
                if 'auckland' in rp['name']:
                    self.g_client.resource.update(
                        resource_type='resource_provider',
                        resource_id=rp['id'], resource={'site': 'auckland'})
                    LOG.info("Set %s to auckland", rp['name'])
                    continue
                if 'intersect' in rp['name']:
                    self.g_client.resource.update(
                        resource_type='resource_provider',
                        resource_id=rp['id'], resource={'site': 'intersect'})
                    LOG.info("Set %s to intersect", rp['name'])
                    continue
                LOG.info("No old resource_provider so don't know which "
                         "site to assign to fix with: "
                         "self.g_client resource update "
                         "--type resource_provider"
                         "-a 'site:<site>' %s", rp['id'])
