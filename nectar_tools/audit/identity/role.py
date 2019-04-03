import logging

from nectar_tools.audit import base
from nectar_tools import auth


LOG = logging.getLogger(__name__)


class RoleAuditor(base.Auditor):

    def __init__(self, ks_session):
        self.k_client = auth.get_keystone_client(sess=ks_session)

    def check_unused_roles(self):
        roles = self.k_client.roles.list()
        for role in roles:
            assignments = self.k_client.role_assignments.list(role=role)
            if not assignments:
                LOG.info("Role %s is unused", role.name)
