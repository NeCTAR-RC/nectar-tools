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

    def _get_allocations(self, allocation_id=None, current=False):
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
        else:
            allocations = self.client.allocations.list(
                parent_request__isnull=True)
        LOG.debug('Auditing %d allocations', len(allocations))
        return allocations

    def check_allocation_basics(self, allocation_id=None):
        allocations = self._get_allocations(allocation_id, current=False)
        for a in allocations:
            if not a.status.isupper():
                LOG.info("Allocation %s status not uppercase", a.id)
            if a.status == allocation_states.APPROVED \
               and a.end_date is None:
                LOG.info("Allocation %s is approved with no end_date", a.id)

    def check_allocation_classification(self, allocation_id=None):
        allocations = self._get_allocations(allocation_id, current=True)
        for a in allocations:
            LOG.debug('Allocation: %s (%s)', a.id, a.project_name)
            grants = self.client.grants.list(allocation=a.id)
            if a.allocation_home == 'national':
                if not grants:
                    LOG.info("Allocation %s (%s): national allocation has no "
                             "grants", a.id, a.project_name)
            else:
                if grants:
                    LOG.info("Allocation %s (%s): local allocation (%s) has "
                             "grants", a.id, a.project_name,
                             a.allocation_home)
                    for g in grants:
                        LOG.info("  - type: %s", g.grant_type)
                        LOG.info("  - funding: %s",
                                 g.funding_body_scheme[:50])

    def check_allocation_history(self, allocation_id=None):
        FORMAT = "%Y-%m-%dT%H:%M:%SZ"
        allocations = self._get_allocations(allocation_id, current=False)
        count = 0
        for a in allocations:
            LOG.debug('Allocation: %s (%s)', a.id, a.project_name)
            if a.modified_time is None:
                LOG.info("Allocation %s has no modified time", a.id)
            history = self.client.allocations.list(parent_request=a.id)
            LOG.debug('Allocation: %s has %s history records', a.id,
                     len(history))
            # The most recent record should be the 'parent'.
            prev = a
            for h in sorted(history, key=lambda h: h.id, reverse=True):
                count += 1
                if h.modified_time is None:
                    LOG.info("Allocation %s history %s has no modified time",
                             a.id, h.id)
                elif prev.modified_time and h.modified_time:
                    prev_time = datetime.strptime(prev.modified_time, FORMAT)
                    hist_time = datetime.strptime(h.modified_time, FORMAT)
                    if prev_time == hist_time \
                       and (hist_time.hour != 0
                            or hist_time.minute != 0
                            or hist_time.second != 0
                            or hist_time.microsecond != 0):
                        # (Note: the modified_time was originally a date.
                        # Equal modified dates are not a problem.)
                        LOG.info("Records for allocation %s have the same "
                                 "mod time: %s %s (%s)",
                                 a.id, prev.id, h.id, h.modified_time)
                    elif prev_time < hist_time:
                        LOG.info("Records for allocation %s have out of order "
                                 "mod times: %s (%s), %s (%s)",
                                 a.id, prev.id, prev.modified_time,
                                 h.id, h.modified_time)
                prev = h
        LOG.info("Checked modified times of %s history records", count)
        if allocation_id is None:
            count = 0
            all_allocation_ids = frozenset(a.id for a in allocations)
            all_records = self.client.allocations.list()
            # Look for records whose parent_request no longer exists
            for r in all_records:
                if r.parent_request:
                    count += 1
                    if r.parent_request not in all_allocation_ids:
                        LOG.info("Detached history record %s for missing "
                                 "allocation %s", r.id, r.parent_request)
            LOG.info("Checked attachment of %s history records", count)
