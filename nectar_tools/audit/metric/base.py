from nectar_tools.audit import base
from nectar_tools import auth


class ResourceAuditor(base.Auditor):

    def __init__(self, ks_session, repair=False):
        super().__init__(ks_session, repair)
        self.g_client = auth.get_gnocchi_client(sess=ks_session)
