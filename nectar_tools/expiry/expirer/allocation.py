import datetime
import logging

from nectar_tools import config
from nectar_tools.expiry import allocation_states
from nectar_tools.expiry import allocations
from nectar_tools.expiry import expiry_states
from nectar_tools.expiry import notifier

from nectar_tools.expiry.expirer import base

CONF = config.CONFIG
LOG = logging.getLogger(__name__)


class AllocationExpirer(base.Expirer):

    def __init__(self, project, ks_session=None, now=datetime.datetime.now(),
                 dry_run=False):
        super(AllocationExpirer, self).__init__(project, ks_session, now,
                                                dry_run)
        self.session = allocations.NectarAllocationSession(
            CONF.allocations.api_url,
            CONF.allocations.username,
            CONF.allocations.password)
        self.notifier = notifier.FreshDeskNotifier(project, ks_session,
                                                   dry_run)

    def process(self):
        allocation = self.session.get_current_allocation(self.project.id)

        allocation_status = allocation['status']

        allocation_start = datetime.datetime.strptime(
            allocation['start_date'], base.DATE_FORMAT)
        allocation_end = datetime.datetime.strptime(
            allocation['end_date'], base.DATE_FORMAT)

        expiry_status = getattr(self.project, 'expiry_status',
                                expiry_states.ACTIVE)
        expiry_next_step = getattr(self.project, 'expiry_next_step', None)
        LOG.debug("%s: expiry_status: %s, expiry_next_step: %s",
                  (self.project.id, expiry_status, expiry_next_step))
        if expiry_next_step:
            expiry_next_step = datetime.datetime.strptime(expiry_next_step,
                                                          base.DATE_FORMAT)

        if allocation_status != allocation_states.APPROVED:
            return

        if expiry_status == expiry_states.ACTIVE:
            allocation_days = (allocation_end - allocation_start).days
            warning_date = allocation_start + datetime.timedelta(
                days=allocation_days * 0.8)
            month_out = allocation_end - datetime.timedelta(days=30)
            if warning_date < month_out:
                warning_date = month_out

            if warning_date < self.now:
                LOG.error("Sending warning")
                self.send_warning()

        elif expiry_status == expiry_states.WARNING:
            if expiry_next_step > self.now:
                LOG.debug("Skipping, not ready for next step")
                return
            self.restrict_project()

        elif expiry_status == expiry_states.RESTRICTED:
            if expiry_next_step > self.now:
                LOG.debug("Skipping, not ready for next step")
                return
            self.stop_project()

        elif expiry_status == expiry_states.STOPPED:
            if expiry_next_step > self.now:
                LOG.debug("Skipping, not ready for next step")
                return
            three_months = (
                self.now + datetime.timedelta(days=90)).strftime(
                    base.DATE_FORMAT)
            self._update_project(expiry_status=expiry_states.ARCHIVING,
                                 expiry_next_step=three_months)
            self.archive_project()

        elif expiry_status == expiry_states.ARCHIVING:
            if expiry_next_step > self.now:
                self.check_archiving_status()
            else:
                LOG.debug("Project archiving longer than next step, move on")
                self._update_project(expiry_status=expiry_states.ARCHIVED)

        elif expiry_status == expiry_states.ARCHIVED:
            if expiry_next_step > self.now:
                self.delete_resources()
            else:
                self.delete_project()

    def send_warning(self):
        LOG.info("%s: Sending warning", self.project.id)
        one_month = (self.now +
                     datetime.timedelta(days=30)).strftime(base.DATE_FORMAT)

        self._update_project(expiry_status=expiry_states.WARNING,
                             expiry_next_step=one_month)
        self.notifier.send_message('first',
                                   extra_context={'expiry_date': one_month})

    def restrict_project(self):
        LOG.info("%s: Restricting project", self.project.id)
        self.nova_archiver.zero_quota()
        self.cinder_archiver.zero_quota()
        # Swift quota

        one_month = (self.now + datetime.timedelta(days=30)).strftime(
            base.DATE_FORMAT)
        self._update_project(expiry_status=expiry_states.RESTRICTED,
                             expiry_next_step=one_month)
        self.notifier.send_message('final')

    def stop_project(self):
        LOG.info("%s: Stopping project", self.project.id)
        self.nova_archiver.stop_resources()
        one_month = (self.now + datetime.timedelta(days=30)).strftime(
            base.DATE_FORMAT)
        self._update_project(expiry_status=expiry_states.STOPPED,
                             expiry_next_step=one_month)

    def delete_project(self):
        LOG.info("%s: Deleting project", self.project.id)
        self.nova_archiver.delete_resources(force=True)
        self.nova_archiver.delete_archives()
        self._update_project(expiry_status=expiry_states.DELETED)
