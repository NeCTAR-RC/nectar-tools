from nectar_tools.audit import base
from nectar_tools import auth


class ResourceAuditor(base.Auditor):

    def setup_clients(self):
        super().setup_clients()
        self.g_client = auth.get_gnocchi_client(sess=self.ks_session)
