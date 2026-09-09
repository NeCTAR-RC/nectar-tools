import logging

from nectar_tools.audit.identity import base
from nectar_tools import utils


LOG = logging.getLogger(__name__)


class RoleAuditor(base.IdentityAuditor):
    def check_unused_roles(self):
        roles = utils.list_resources(self.k_client.roles.list)
        # One bulk role assignment listing instead of a keystone call
        # per role; listing by role returns every assignment of that
        # role anyway, so this is no bigger a response.
        assignments = self.k_client.role_assignments.list()
        used_roles = {a.role['id'] for a in assignments}
        for role in roles:
            if role.id not in used_roles:
                LOG.info("Role %s is unused", role.name)
