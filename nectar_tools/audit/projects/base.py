from nectar_tools.audit import base
from nectar_tools import auth


class ProjectAuditor(base.Auditor):

    def __init__(self, ks_session, project, repair=False):
        super().__init__(ks_session, repair)
        self.project = project
        self.k_client = auth.get_keystone_client(sess=ks_session)
