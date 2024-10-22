import logging

import keystoneauth1

from nectar_tools.audit.allocation import base
from nectar_tools import auth
from nectar_tools.expiry import expiry_states


LOG = logging.getLogger(__name__)


class PendingAllocationAuditor(base.AllocationAuditorBase):
    def setup_clients(self):
        super().setup_clients()
        self.k_client = auth.get_keystone_client(sess=self.ks_session)

    def check_pending(self, allocation_id=None):
        allocations = self._get_allocations(allocation_id, pending=True)
        for a in allocations:
            approver_info = a.get_approver_info()
            if a.project_id:
                try:
                    p = self.k_client.projects.get(a.project_id)
                    expiry_status = getattr(p, 'expiry_status', '')
                except keystoneauth1.exceptions.http.NotFound:
                    LOG.warning(
                        "Allocation %s: allocation's project (%s) "
                        "is missing",
                        a.id,
                        a.project_id,
                    )
                    expiry_status = "Unknown (missing project!)"
            else:
                expiry_status = "N/A"
            for site in approver_info['concerned_sites']:
                if (
                    approver_info['expiry_state']
                    in ("Danger", "Archived", "Stopped", "Expired")
                    or approver_info["approval_urgency"]
                    in ("Warning", "Overdue")
                    or expiry_status
                    in (
                        expiry_states.STOPPED,
                        expiry_states.RESTRICTED,
                        expiry_states.ARCHIVING,
                        expiry_states.ARCHIVED,
                    )
                ):
                    level = logging.WARN
                else:
                    level = logging.INFO
                LOG.log(
                    level,
                    "Allocation %s: pending in status %s, urgency '%s', "
                    "last update %s, real expiry status %s, "
                    "inferred expiry state %s",
                    a.id,
                    a.status,
                    approver_info['approval_urgency'],
                    a.modified_time,
                    expiry_status,
                    approver_info['expiry_state'],
                    extra={'extra': {'site': site}},
                )
