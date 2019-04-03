from nectar_tools.audit import base
from nectar_tools import auth


class IdentityAuditor(base.Auditor):

    def __init__(self, ks_session):
        self.k_client = auth.get_keystone_client(sess=ks_session)
