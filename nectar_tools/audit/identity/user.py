import logging
import re

import keystoneauth1

from nectar_tools.audit.identity import base


LOG = logging.getLogger(__name__)

# This regex matches an RFC822 addr-spec with a 2 to 4 char TLD
EMAIL_RE = re.compile(r"^[\w.!#$%&'*+\-/=?^_`{|}~]+@([\w\-]+\.)+[\w\-]{2,4}$")


class UserAuditor(base.IdentityAuditor):

    def __init__(self, ks_session, repair=False, dry_run=True):
        super().__init__(ks_session, repair, dry_run)
        self.users = self.k_client.users.list(domain='default')

    def check_users_no_projects(self):
        for user in self.users:
            assignments = self.k_client.role_assignments.list(user=user)
            if not assignments:
                LOG.info("User %s has no roles assigned", user.name)

    def check_user_names(self):
        for user in self.users:
            if not hasattr(user, 'default_project_id') or not user.enabled:
                continue
            # Users with no "@" in the name are typically service or
            # cloud operator a/c's
            if "@" in user.name and not EMAIL_RE.match(user.name):
                LOG.error("User name '%s' is a malformed email address",
                          user.name)

    def check_default_project_id(self):
        for user in self.users:
            default_project_id = getattr(user, 'default_project_id', None)
            if not default_project_id:
                LOG.info("User %s has no default_project_id", user.name)
                continue
            try:
                project = self.k_client.projects.get(default_project_id)
            except keystoneauth1.exceptions.http.NotFound:
                LOG.warn("User %s default_project_id points to non existant"
                         "project", user.name)
                continue
            if getattr(project, 'expiry_status', None) == 'admin':
                # Ignore admin project
                continue
            if project.name + '_bot' == user.name:
                # Ignore bot accounts
                continue
            if not project.name.startswith('pt-'):
                LOG.warn("User %s default_project_id is not a Project Trial",
                         user.name)
