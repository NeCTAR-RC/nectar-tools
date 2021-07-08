import logging


from nectar_tools.audit.metric import base


LOG = logging.getLogger(__name__)


class IDPAuditor(base.ResourceAuditor):

    def __init__(self, *args, **kwargs):
        kwargs['log'] = LOG
        super().__init__(*args, **kwargs)

    def ensure_country(self):
        resources = self.g_client.resource.search(
            resource_type='idp',
            query='country=null')

        for idp in resources:
            LOG.error("IDP %s has no country",
                      idp['original_resource_id'])
