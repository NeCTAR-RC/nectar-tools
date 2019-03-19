import logging

from nectarallocationclient import exceptions as allocation_exceptions

from nectar_tools.audit.projects import base
from nectar_tools import auth


LOG = logging.getLogger(__name__)


class ProjectAllocationAuditor(base.ProjectAuditor):

    def __init__(self, ks_session, project):
        super(ProjectAllocationAuditor, self).__init__(ks_session, project)
        self.a_client = auth.get_allocation_client(sess=ks_session)

    def check_allocation_id(self):
        print(self.project.name)
        allocation_id = getattr(self.project, 'allocation_id', None)
        if not allocation_id:
            LOG.info("%s: No allocation_id", self.project.id)
            return
        try:
            allocation = self.a_client.allocations.get(allocation_id)
        except allocation_exceptions.NotFound:
            LOG.info("%s: Linked allocation_id not found", self.project.id)
            return

        if allocation.project_id != self.project.id:
            LOG.info("%s: Linked allocation_id project mismatch",
                     self.project.id)
