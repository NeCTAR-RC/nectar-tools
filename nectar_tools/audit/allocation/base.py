from datetime import datetime
import logging

from nectarallocationclient import exceptions as allocation_exceptions
from nectarallocationclient import states as allocation_states

from nectar_tools.audit import base
from nectar_tools import auth


LOG = logging.getLogger(__name__)


class AllocationAuditorBase(base.Auditor):

    def setup_clients(self):
        super().setup_clients()
        self.client = auth.get_allocation_client(sess=self.ks_session)

    def _get_allocations(self, allocation_id=None, current=False,
                         pending=False):
        if allocation_id:
            try:
                allocation = self.client.allocations.get(allocation_id)
                allocations = [allocation]
            except allocation_exceptions.NotFound:
                LOG.error("%s: Allocation not found", allocation_id)
                return
        elif current:
            allocations = [a for a in self.client.allocations.list(
                parent_request__isnull=True,
                status=allocation_states.APPROVED)
                           if a.end_date is None  # in dev or test
                           or datetime.strptime(a.end_date, "%Y-%M-%d")
                           > datetime.today()]
        elif pending:
            allocations = self.client.allocations.list(
                parent_request__isnull=True,
                status__in=[allocation_states.NEW,
                            allocation_states.SUBMITTED,
                            allocation_states.UPDATE_PENDING])
        else:
            allocations = self.client.allocations.list(
                parent_request__isnull=True)
        LOG.debug('Auditing %d allocations', len(allocations))
        return allocations
