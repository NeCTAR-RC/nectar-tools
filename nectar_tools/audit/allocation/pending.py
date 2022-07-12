from datetime import date
from datetime import timedelta
import logging

from dateutil import parser

from nectar_tools.audit.allocation import base


LOG = logging.getLogger(__name__)


class PendingAllocationAuditor(base.AllocationAuditorBase):

    def check_pending(self, allocation_id=None):
        today = date.today()
        allocations = self._get_allocations(allocation_id, pending=True)
        for a in allocations:
            # This roughly corresponds to the 'urgency' classification
            # in the Pending Allocations page.  One difference is that
            # we are separating the expiry and age criteria.
            mod_date = parser.parse(a.modified_time).date()
            if a.end_date:
                end_date = parser.parse(a.end_date).date()
                if end_date < today:
                    if mod_date + timedelta(days=30 * 5) < today:
                        expiry = "Danger"
                    elif end_date + timedelta(days=28) < today:
                        expiry = "Archived"
                    elif end_date + timedelta(days=14) < today:
                        expiry = "Stopped"
                    else:
                        expiry = "Expiring"
                else:
                    expiry = "Not expiring"
            else:
                expiry = "Not provisioned"

            if mod_date + timedelta(days=21) < today:
                urgency = "Overdue"
            elif mod_date + timedelta(days=14) < today:
                urgency = "Warning"
            elif mod_date + timedelta(days=7) < today:
                urgency = "Attention"
            else:
                urgency = "New"
            if expiry in ("Danger", "Archived", "Stopped") \
               or urgency in ("Warning", "Overdue"):
                LOG.warning("Allocation %s: pending in status %s, "
                            "expiry state '%s', urgency '%s', "
                            "last mod date %s",
                            a.id, a.status, expiry, urgency, mod_date)
