import datetime
import logging

import placementclient

from nectar_tools.audit.metric import base
from nectar_tools import auth


LOG = logging.getLogger(__name__)


domain_site_mapping = {
    'monash.edu.au': 'monash',
    'melbourne.nectar.org.au': 'melbourne',
    'unimelb.edu.au': 'melbourne',
    'qld.nectar.org.au': 'QRIScloud',
    'auckland': 'auckland',
    'intersect': 'intersect',
    'tpac.org.au': 'tasmania',
    'mgmt.sut': 'swinburne',
    'os.sut': 'swinburne',
    'mel-1.rc.nectar.org.au': 'ardc',
    'adelaide.nectar.org.au': 'adelaide',
    'test.rc.nectar.org.au': 'coreservices',
}


class ResourceProviderAuditor(base.ResourceAuditor):
    def setup_clients(self):
        super().setup_clients()
        self.p_client = auth.get_placement_client(sess=self.ks_session)

    def ensure_site(self):
        resources = self.g_client.resource.search(
            resource_type='resource_provider', query='site=null'
        )

        for rp in resources:
            LOG.info("Processing %s", rp['name'])
            old_resources = self.g_client.resource.search(
                resource_type='resource_provider',
                query="site!=null and name='{}'".format(rp['name']),
            )
            if old_resources:
                LOG.warning(
                    "Recreated resource providers found %s", rp['name']
                )

                resource_data = {'site': old_resources[0]['site']}
                scope = old_resources[0].get('scope')
                if scope:
                    resource_data['scope'] = scope
                    for old in old_resources:
                        self.repair(
                            f"Deleting old RP {old['id']}",
                            lambda: self.g_client.resource.delete(old['id']),
                        )
                    self.repair(
                        f"Updating resource providers for {rp['id']}",
                        lambda: self.g_client.resource.update(
                            resource_type='resource_provider',
                            resource_id=rp['id'],
                            resource=resource_data,
                        ),
                    )
            else:
                for domain_search, site in domain_site_mapping.items():
                    if domain_search in rp['name']:
                        self.repair(
                            f"Setting site for {rp['name']} to {site}",
                            lambda: self.g_client.resource.update(
                                resource_type='resource_provider',
                                resource_id=rp['id'],
                                resource={'site': site},
                            ),
                        )
                        break
                else:
                    LOG.info(
                        "No old resource_provider so don't know which "
                        "site to assign to fix with: "
                        "gnocchi resource update "
                        "--type resource_provider "
                        "-a 'site:<site>' %s",
                        rp['id'],
                    )

    def ensure_exists(self):
        now = datetime.datetime.now()
        resources = self.g_client.resource.search(
            resource_type='resource_provider', query='ended_at=null'
        )
        for resource in resources:
            try:
                self.p_client.resource_providers.get(resource['id'])
            except placementclient.exceptions.NotFound:
                LOG.warning(
                    "Resource provider %s no longer exists", resource['name']
                )
                self.repair(
                    f"Marking resource provider {resource['name']} "
                    "as ended",
                    lambda: self.g_client.resource.update(
                        resource_type='resource_provider',
                        resource_id=resource['id'],
                        resource={'ended_at': str(now)},
                    ),
                )

    def ensure_scope(self):
        resources = self.g_client.resource.search(
            resource_type='resource_provider',
            query='scope=null and ended_at=null',
        )
        for rp in resources:
            if 'auckland' in rp['name']:
                self.repair(
                    f"Setting scope for {rp['name']} to local",
                    self.g_client.resource.update,
                    resource_type='resource_provider',
                    resource_id=rp['id'],
                    resource={'scope': 'local'},
                )
            else:
                LOG.info(
                    "Resource provider %s has no scope set. Scope should "
                    "be set to \"local\" or \"national\". Fix with: "
                    "gnocchi resource update --type resource_provider "
                    "-a 'scope:<local_or_national>' %s",
                    rp['name'],
                    rp['id'],
                )
