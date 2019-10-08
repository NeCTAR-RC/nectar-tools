from nectar_tools.audit import base
from nectar_tools import auth


class ProjectAuditor(base.Auditor):

    def __init__(self, ks_session, project, repair=False):
        super().__init__(ks_session, repair)
        self.project = project

    def setup_clients(self):
        super().setup_clients()
        self.k_client = auth.get_keystone_client(sess=self.ks_session)
