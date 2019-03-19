import logging

from nectar_tools.audit.projects import base
from nectar_tools import auth


LOG = logging.getLogger(__name__)


class ProjectAllocationAuditor(base.ProjectAuditor):

    def __init__(self, ks_session, project):
        super(ProjectAllocationAuditor, self).__init__(ks_session, project)
        self.a_client = auth.get_allocation_client(sess=ks_session)

    def check_allocation_id(self):
        allocation_id = getattr(self.project, 'allocation_id', None)
        if allocation_id is None:
            LOG.info("%s: No allocation_id", self.project.id)
