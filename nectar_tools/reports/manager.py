import datetime
import logging

from nectar_tools import auth
from nectar_tools.common import service_units
from nectar_tools import exceptions
from nectar_tools.expiry import expiry_states
from nectar_tools.reports import notifier


DATE_FORMAT = '%Y-%m-%d'
LOG = logging.getLogger(__name__)


class SUReporter(object):

    def __init__(self, ks_session=None, noop=False, force=False,
                 *args, **kwargs):
        self.force = force
        self.noop = noop
        self.ks_session = ks_session
        self.a_client = auth.get_allocation_client(self.ks_session)
        self.k_client = auth.get_keystone_client(self.ks_session)

    def send_over_budget_report(self, allocation):
        n = notifier.AllocationNotifier(
            allocation=allocation, ks_session=self.ks_session, noop=self.noop)
        n.send_over_budget()

    def send_all_reports(self, skip_to=None):
        allocations = self.a_client.allocations.list(
            status='A', parent_request__isnull=True)

        if skip_to:
            LOG.info(f"Skipping to allocation {skip_to}")
        for allocation in allocations:
            if skip_to:
                if skip_to == allocation.id:
                    skip_to = None
                    LOG.info(f"Found allocation {allocation.id}, resuming")
                else:
                    continue
            try:
                self.send_reports(allocation)
            except exceptions.InvalidProjectAllocation as e:
                LOG.error(e)
                continue
            except Exception as e:
                LOG.error(f"Error processing allocation {allocation.id}")
                raise e
        if skip_to:
            LOG.error(f"Didn't find --skip-to-... allocation {skip_to}")

    def send_reports(self, allocation):
        if type(allocation) == int:
            allocation = self.a_client.allocations.get(allocation)

        if not allocation.project_id:
            raise exceptions.InvalidProjectAllocation(
                f"No project id for {allocation}")
        project = self.k_client.projects.get(allocation.project_id)
        expiry_status = getattr(project, 'expiry_status', None)
        if expiry_status in [expiry_states.WARNING,
                             expiry_states.RESTRICTED,
                             expiry_states.STOPPED,
                             expiry_states.ARCHIVING,
                             expiry_states.ARCHIVED]:
            LOG.debug(
                f"Skipping {allocation.id} expiry process in progress")
            return

        if not project.enabled:
            raise exceptions.InvalidProjectAllocation(
                f"Project {project.id} disabled")

        if not allocation.start_date or not allocation.end_date:
            raise exceptions.InvalidProjectAllocation(
                f"Project {project.id} start or end date missing")

        su_info = service_units.SUinfo(self.ks_session, allocation)

        if su_info.is_tracking_over():
            today = datetime.datetime.today()
            days_used = (today - su_info.allocation_start).days
            if (days_used / su_info.allocation_total_days) < 0.25:
                LOG.debug(f"{allocation.id}: Skipping, allocation less "
                          "than 25% through allocated period")
                return

            self.send_over_budget_report(allocation)
