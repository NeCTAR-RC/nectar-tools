from nectar_tools.audit import base
from nectar_tools import auth


class IdentityAuditor(base.Auditor):

    def __init__(self, ks_session, repair=False):
        super().__init__(ks_session, repair)
        self.k_client = auth.get_keystone_client(sess=ks_session)
