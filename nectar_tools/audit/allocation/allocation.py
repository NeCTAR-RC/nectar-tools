from datetime import datetime
import logging

from nectarallocationclient import exceptions as allocation_exceptions
from nectarallocationclient import states as allocation_states

from nectar_tools.audit import base
from nectar_tools import auth


LOG = logging.getLogger(__name__)


class AllocationAuditor(base.Auditor):

    def setup_clients(self):
        super().setup_clients()
        self.client = auth.get_allocation_client(sess=self.ks_session)

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
               and a.provisioned and a.end_date is None:
                LOG.info("Allocation %s is approved and provisioned with"
                         " no end_date", a.id)
            if a.status == allocation_states.APPROVED \
               and a.associated_site is None:
                LOG.info("Allocation %s is approved with no associated site",
                         a.id)

    def check_allocation_classification(self, allocation_id=None):
        allocations = self._get_allocations(allocation_id, current=True)
        for a in allocations:
            LOG.debug('Allocation: %s (%s)', a.id, a.project_name)
            if a.associated_site in ('swinburne', 'auckland'):
                continue
            grants = self.client.grants.list(allocation=a.id)

            # This does not take account of whether the grants were
            # current at the last approval.
            has_competitive_grant = any(
                [g.grant_type in ('arc', 'nhmrc', 'comp') for g in grants])

            # We can't tell if the Allocations ctty has made an exception or
            # if the allocation has an international competitive grant.
            qualifies = has_competitive_grant \
                        or a.nectar_support \
                        or a.ncris_support
            if a.national and not qualifies:
                LOG.info("Allocation %s (%s): national allocation (%s) has no "
                         "national competitive grants, and no ARDC or "
                         "NCRIS support",
                         a.id, a.project_name, a.associated_site)
            elif qualifies and not a.national:
                LOG.info("Allocation %s (%s): local allocation (%s) qualifies "
                         "for national funding",
                         a.id, a.project_name, a.associated_site)

    def check_allocation_history(self, allocation_id=None):
        FORMAT = "%Y-%m-%dT%H:%M:%SZ"
        allocations = self._get_allocations(allocation_id, current=False)
        for a in allocations:
            LOG.debug('Allocation: %s (%s)', a.id, a.project_name)
            history = self.client.allocations.list(parent_request=a.id)
            LOG.debug('Allocation: %s has %s history records', a.id,
                     len(history))
            # The most recent record should be the 'parent'.  Hence ...
            prev = a
            for h in sorted(history, key=lambda h: h.id, reverse=True):
                prev_time = datetime.strptime(prev.modified_time, FORMAT)
                hist_time = datetime.strptime(h.modified_time, FORMAT)
                if prev_time == hist_time \
                   and not (hist_time.hour == 0 and hist_time.minute == 0
                            and hist_time.second == 0
                            and hist_time.microsecond == 0):
                    # Concerning the above test: the modified_time was
                    # originally a date, and some old records will have
                    # a mod time that was converted from a date.  We don't
                    # want to report those.  Hence the tests for 00:00:00.0
                    LOG.info("Records for allocation %s have the same "
                             "mod time: %s %s (%s)",
                             a.id, prev.id, h.id, h.modified_time)
                elif prev_time < hist_time:
                    LOG.info("Records for allocation %s have out of order "
                             "mod times: %s (%s), %s (%s)",
                             a.id, prev.id, prev.modified_time,
                             h.id, h.modified_time)
                prev = h
        if allocation_id is None:
            all_allocation_ids = frozenset(a.id for a in allocations)
            all_records = self.client.allocations.list()
            # Look for records whose parent_request no longer exists
            for r in all_records:
                if r.parent_request:
                    if r.parent_request not in all_allocation_ids:
                        LOG.info("Detached history record %s for missing "
                                 "allocation %s", r.id, r.parent_request)

    def _check_percent(self, id, code, percent, ordinal):
        if percent < 0 or percent > 100:
            LOG.info("Allocation %s: FoR percent #%d is invalid (%d)",
                     id, ordinal, percent)
        elif code and not percent:
            LOG.info("Allocation %s: FoR percent #%d should be non-zero",
                     id, ordinal)
        elif not code and percent:
            LOG.info("Allocation %s: FoR percent #%d should be zero (is %d)",
                     id, ordinal, percent)

    def check_for_codes(self, allocation_id=None):
        allocations = self._get_allocations(allocation_id, current=True)
        for a in allocations:
            self._check_percent(a.id, a.field_of_research_1,
                                a.for_percentage_1, 1)
            self._check_percent(a.id, a.field_of_research_2,
                                a.for_percentage_2, 2)
            self._check_percent(a.id, a.field_of_research_3,
                                a.for_percentage_3, 3)
            sum = a.for_percentage_1 + a.for_percentage_2 + a.for_percentage_3
            if sum != 0 and sum != 100:
                LOG.info("Allocation %s: FoR percent sum is incorrect (%d)",
                         a.id, sum)
