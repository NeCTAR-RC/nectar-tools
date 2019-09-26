from nectar_tools.audit import base
from nectar_tools import auth


class IdentityAuditor(base.Auditor):

    def setup_clients(self):
        super().setup_clients()
        self.k_client = auth.get_keystone_client(sess=self.ks_session)
