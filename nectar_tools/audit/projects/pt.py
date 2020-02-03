import logging

from nectar_tools.audit.projects import base
from nectar_tools import config


CONF = config.CONFIG
LOG = logging.getLogger(__name__)


class ProjectTrialAuditor(base.ProjectAuditor):

    def check_owner(self):
        assignments = self.k_client.role_assignments.list(
            project=self.project,
            role=CONF.keystone.member_role_id)
        if len(assignments) > 1:
            LOG.info("%s: More than 1 user", self.project.id)
        if len(assignments) < 1:
            LOG.info("%s: No users", self.project.id)