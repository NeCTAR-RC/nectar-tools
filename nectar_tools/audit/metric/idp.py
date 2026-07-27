import logging


from nectar_tools.audit.metric import base


LOG = logging.getLogger(__name__)


class IDPAuditor(base.ResourceAuditor):
    def ensure_country(self):
        resources = self.g_client.resource.search(
            resource_type='idp', query='country=null'
        )

        for idp in resources:
            domain = idp['original_resource_id']
            if domain.endswith('_au'):
                country = 'AU'
            elif domain.endswith('_nz'):
                country = 'NZ'
            else:
                LOG.error("IDP %s has no country", domain)
                LOG.info(
                    "To fix with: "
                    "gnocchi resource update "
                    "--type idp "
                    "-a 'country:<AU or NZ>' %s",
                    idp['id'],
                )
                continue

            self.repair(
                f"{domain}: Setting country to {country}",
                lambda: self.g_client.resource.update(
                    'idp', idp['id'], {'country': country}
                ),
            )
