from dateutil.relativedelta import relativedelta
import logging
import re

from nectarallocationclient import states as allocation_states

from nectar_tools.audit.projects import base
from nectar_tools import config
from nectar_tools.expiry import expiry_states


CONF = config.CONFIG
LOG = logging.getLogger(__name__)
TICKET_RE = re.compile(r'^ticket-.+$')


class ProjectTrialAuditor(base.ProjectAuditor):

    def check_owner(self):
        assignments = self.k_client.role_assignments.list(
            project=self.project,
            role=CONF.keystone.member_role_id)
        if len(assignments) > 1:
            LOG.info("%s: More than 1 user", self.project.id)
        if len(assignments) < 1:
            LOG.info("%s: No users", self.project.id)

    def _pending_allocations(self):
        if self.project.owner is None:
            return []
        six_months_ago = self.now - relativedelta(months=6)
        return self.a_client.allocations.list(
            contact_email=self.project.owner.name,
            status=allocation_states.SUBMITTED,
            modified_time__lt=six_months_ago.isoformat())

    def check_expiry(self):
        expiry_status = getattr(self.project, 'expiry_status', '')
        if not expiry_status:
            return
        expiry_next_step = getattr(self.project, 'expiry_next_step', None)
        if self._past_next_step(expiry_next_step):
            if expiry_status == expiry_states.DELETED:
                # There are a lot of PTs like this.  It is not noteworthy
                pass
            elif expiry_status in (expiry_states.WARNING,
                                 expiry_states.STOPPED,
                                 expiry_states.RESTRICTED,
                                 expiry_states.ARCHIVING,
                                 expiry_states.ARCHIVED):
                allocations = self._pending_allocations()
                if allocations:
                    LOG.info("%s: PT expiry blocked on approval "
                             "decision: expiry status %s",
                             self.project.id, expiry_status)
                else:
                    LOG.error("%s: PT expiry stuck: expiry status %s",
                              self.project.id, expiry_status)
            elif expiry_status in expiry_states.ALL_STATES:
                LOG.info("%s: PT expiry in unexpected state: "
                         "expiry status %s, next step %s",
                         self.project.id, expiry_status, expiry_next_step)
            elif TICKET_RE.match(expiry_status):
                LOG.warn("%s: PT expiry overdue in ticket hold: "
                         "expiry status %s",
                         self.project.id, expiry_status)
            else:
                LOG.error("%s: PT expiry in unknown state: "
                          "expiry_status %s",
                          self.project.id, expiry_status)
