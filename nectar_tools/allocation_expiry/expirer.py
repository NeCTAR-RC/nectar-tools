import logging
import datetime

from nectar_tools import auth
from nectar_tools.allocation_expiry.allocations import NectarAllocationSession
from nectar_tools.allocation_expiry import archiver


LOG = logging.getLogger(__name__)

DATE_FORMAT = '%Y-%m-%d'


class NectarExpirer(object):

    def __init__(self, now=datetime.datetime.now()):
        url = 'https://dashboard.test.rc.nectar.org.au'
        username = 'sam'
        password = 'nectar'
        self.session = NectarAllocationSession(url, username, password)
        self.k_client = auth.get_keystone_client()
        self.now = now
        self.month_ago = self.now - datetime.timedelta(days=30)
        self.three_months_ago = self.now - datetime.timedelta(days=90)

    def get_allocations_for_project(self, project):
        pass

    def has_pending_allocation(self, allocations):
        pass

    def get_latest_approved_allocation(self, allcations):
        pass

    def handle_project(self, project):
        allocation = self.session.get_pending_allocation(project.id)
        allocation_status = allocation['status']
        
        allocation_start = datetime.datetime.strptime(allocation['start_date'], DATE_FORMAT)
        allocation_end = datetime.datetime.strptime(allocation['end_date'], DATE_FORMAT)

        expiry_status = getattr(project, 'expiry_status', 'active')
        next_step = getattr(project, 'next_step', None)
        if next_step:
            next_step = datetime.datetime.strptime(next_step, DATE_FORMAT)
            if next_step > self.now:
                LOG.debug("Skipping, not ready for next step")
                return

        if allocation_status != 'A':
            return
        if expiry_status == 'active':
            allocation_days = (allocation_end - allocation_start).days
            warning_date = allocation_start + datetime.timedelta(days=allocation_days * 0.8)
            month_out = allocation_end - datetime.timedelta(days=30)
            if warning_date < month_out:
                warning_date = month_out

            if warning_date < self.now:
                LOG.error("Sending warning")
                self.send_warning(project, allocation_end)
            else:
                LOG.debug("%s - Not ready for warning end_date:%s warning_date:%s" % (project.id, allocation_end, warning_date))

        elif expiry_status == 'warning':
            if next_step > self.now:
                LOG.debug("Skipping, not ready for next step")
                return
            self.restrict_project(project)

        elif expiry_status == 'restricted':
            if next_step > self.now:
                LOG.debug("Skipping, not ready for next step")
                return
            self.stop_project(project)

        elif expiry_status == 'stopped':
            if next_step > self.now:
                LOG.debug("Skipping, not ready for next step")
                return
            self.archive_project(project)

        elif expiry_status == 'archiving':
            if next_step > self.now:
                self.check_archiving_status(project)
            else:
                LOG.debug("Project archiving longer than next step, move on")
                self._update_project(project.id, expiry_status='archived')

        elif expiry_status == 'archived':
            if next_step > self.now:
                LOG.debug("Skipping, not ready for next step")
                return
            self.delete_project(project)

    def _update_project(self, project_id, **kwargs):
        self.k_client.projects.update(project_id, **kwargs)

    def send_warning(self, project, allocation_end):
        #send email
        next_step = allocation_end.strftime(DATE_FORMAT)
        self._update_project(project.id, expiry_status='warning', next_step=next_step)

    def restrict_project(self, project):
        #send email
        nova_archiver = archiver.NovaArchiver(project=project)
        nova_archiver.zero_quota()
        # Cinder quota
        # Swift quota

        one_month = (self.now + datetime.timedelta(days=30)).strftime(DATE_FORMAT)
        self._update_project(project.id, expiry_status='restricted', next_step=one_month)

    def stop_project(self, project):
        nova_archiver = archiver.NovaArchiver(project=project)
        nova_archiver.stop_instances()
        one_month = (self.now + datetime.timedelta(days=30)).strftime(DATE_FORMAT)
        self._update_project(project.id, expiry_status='stopped', next_step=one_month)

    def archive_project(self, project):
        # Archive all resources
        three_months = (self.now + datetime.timedelta(days=90)).strftime(DATE_FORMAT)
        self._update_project(project.id, expiry_status='archiving', next_step=three_months)
        nova_archiver = archiver.NovaArchiver(project=project)
        nova_archiver.archive_instances()

    def check_archiving_status(self, project):
        nova_archiver = archiver.NovaArchiver(project=project)
        if nova_archiver.is_archive_successful():
            self._update_project(project.id, expiry_status='archived')
            #delete all resources that have been archived

    def delete_project(self, project):
        # Delete all resources and archives
        # update_expiry_status to deleted
        pass
