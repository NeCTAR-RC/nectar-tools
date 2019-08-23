from datetime import datetime
import logging

from nectarallocationclient import exceptions as allocation_exceptions
from nectarallocationclient import states as allocation_states

from nectar_tools.audit import base
from nectar_tools import auth


LOG = logging.getLogger(__name__)


class AllocationAuditor(base.Auditor):

    def __init__(self, ks_session):
        super(AllocationAuditor, self).__init__(ks_session=ks_session)
        self.client = auth.get_allocation_client(sess=ks_session)

    def check_allocation_category(self, allocation_id=None):
        if allocation_id:
            try:
                allocation = self.client.allocations.get(allocation_id)
                allocations = [allocation]
            except allocation_exceptions.NotFound:
                LOG.error("%s: Allocation not found", allocation_id)
                return
        else:
            allocations = [a for a in self.client.allocations.list(
                parent_request__isnull=True,
                status=allocation_states.APPROVED)
                           if datetime.strptime(a.end_date, "%Y-%M-%d")
                           > datetime.today()]
        LOG.debug('Auditing %d allocations', len(allocations))

        for allocation in allocations:
            LOG.debug('Allocation: %s (%s)', allocation.id,
                      allocation.project_name)
            grants = self.client.grants.list(allocation=allocation.id)
            if allocation.allocation_home == 'national':
                if not grants:
                    LOG.info("Allocation %s (%s): national allocation has no "
                             "grants", allocation.id, allocation.project_name)
            else:
                if grants:
                    LOG.info("Allocation %s (%s): local allocation (%s) has "
                             "grants", allocation.id, allocation.project_name,
                             allocation.allocation_home)
                    for grant in grants:
                        LOG.info("  - type: %s", grant.grant_type)
                        LOG.info("  - funding: %s",
                                 grant.funding_body_scheme[:50])
