import logging

from nectarallocationclient import exceptions as allocation_exceptions

from nectar_tools.audit.projects import base
from nectar_tools.expiry import expiry_states
from nectar_tools import auth


LOG = logging.getLogger(__name__)


class ProjectAllocationAuditor(base.ProjectAuditor):

    def __init__(self, ks_session, project):
        super(ProjectAllocationAuditor, self).__init__(ks_session, project)
        self.a_client = auth.get_allocation_client(sess=ks_session)

    def check_allocation_id(self):
        allocation_id = getattr(self.project, 'allocation_id', None)
        expiry_status = getattr(self.project, 'expiry_status', '')
        if expiry_status == expiry_state.ADMIN:
            return
        if not allocation_id:
            LOG.info("%s: No allocation_id", self.project.id)
            try:
                allocation = self.a_client.allocations.get_current(
                    project_id=self.project.id)
            except allocation_exceptions.AllocationDoesNotExist:
                LOG.error("%s: Can't find allocation for project",
                          self.project.id)
                return
            if self.repair:
                if not self.dry_run:
                    LOG.info("%s: Setting allocation_id = %s",
                             self.project.id, allocation.id)
                    self.k_client.projects.update(self.project.id,
                                                  allocation_id=allocation.id)
                else:
                    LOG.info("%s: Would set allocation_id = %s",
                             self.project.id, allocation.id)
            return
        try:
            allocation = self.a_client.allocations.get(allocation_id)
        except allocation_exceptions.NotFound:
            LOG.info("%s: Linked allocation_id not found", self.project.id)
            return

        if allocation.project_id is None or allocation.project_id == '':
            LOG.info("%s: Linked allocation not linked back to project",
                     self.project.id)
        elif allocation.project_id != self.project.id:
            LOG.info("%s: Linked allocation_id project mismatch",
                     self.project.id)

        if allocation.status == 'D' \
           and expiry_status != expiry_states.DELETED:
            LOG.info("%s: Live project linked to deleted allocation",
                     self.project.id)
        elif allocation.status != 'D' \
             and expiry_status == expiry_states.DELETED:
            LOG.info("%s: Deleted project linked to live allocation",
                     self.project.id)
            
