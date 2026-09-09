import logging
import re

from nectar_tools.audit.identity import base
from nectar_tools import utils


LOG = logging.getLogger(__name__)

# This regex matches an RFC822 addr-spec with a 2 to 4 char TLD
EMAIL_RE = re.compile(r"^[\w.!#$%&'*+\-/=?^_`{|}~]+@([\w\-]+\.)+[\w\-]{2,4}$")


class UserAuditor(base.IdentityAuditor):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.users = utils.list_resources(
            self.k_client.users.list, domain='default'
        )

    def check_users_no_projects(self):
        # One bulk role assignment listing instead of a keystone call
        # per user; per-user calls take hours at our user count.
        assignments = self.k_client.role_assignments.list()
        users_with_roles = {
            a.user['id'] for a in assignments if hasattr(a, 'user')
        }
        for user in self.users:
            if not user.enabled:
                # Disabled user a/c's with no roles are not noteworthy.
                # For example, the procedure for closing a cores or
                # site operator a/c is to remove all roles and disable.
                continue
            if user.id not in users_with_roles:
                LOG.info("User %s has no roles assigned", user.name)

    def check_user_names(self):
        for user in self.users:
            if not hasattr(user, 'default_project_id') or not user.enabled:
                continue
            # Users with no "@" in the name are typically service or
            # cloud operator a/c's
            if "@" in user.name and not EMAIL_RE.match(user.name):
                LOG.error(
                    "User name '%s' is a malformed email address", user.name
                )

    def check_default_project_id(self):
        # One bulk project listing instead of a keystone call per user;
        # per-user calls take hours at our user count.
        projects = {
            p.id: p for p in utils.list_resources(self.k_client.projects.list)
        }
        for user in self.users:
            default_project_id = getattr(user, 'default_project_id', None)
            if not default_project_id:
                LOG.info("User %s has no default_project_id", user.name)
                continue
            project = projects.get(default_project_id)
            if project is None:
                LOG.warning(
                    "User %s default_project_id is a non-existent project",
                    user.name,
                )
                continue
            if getattr(project, 'expiry_status', None) == 'admin':
                # Ignore admin project
                continue
            if project.name + '_bot' == user.name:
                # Ignore bot accounts
                continue
            if not project.name.startswith('pt-'):
                LOG.warning(
                    "User %s default_project_id is not a PT", user.name
                )
