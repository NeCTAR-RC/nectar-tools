import logging

from nectar_tools.audit.identity import base


LOG = logging.getLogger(__name__)


class RoleAuditor(base.IdentityAuditor):

    def check_unused_roles(self):
        roles = self.k_client.roles.list()
        for role in roles:
            assignments = self.k_client.role_assignments.list(role=role)
            if not assignments:
                LOG.info("Role %s is unused", role.name)
