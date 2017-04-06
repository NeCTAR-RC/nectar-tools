import datetime
from dateutil.relativedelta import relativedelta
import enum
import logging
import re

from nectar_tools import auth
from nectar_tools import config

from nectar_tools.expiry import allocation_states
from nectar_tools.expiry import allocations
from nectar_tools.expiry import archiver
from nectar_tools.expiry import exceptions
from nectar_tools.expiry import expiry_states
from nectar_tools.expiry import notifier


CONF = config.CONFIG
LOG = logging.getLogger(__name__)

DATE_FORMAT = '%Y-%m-%d'
PT_RE = re.compile(r'^pt-\d+$')
USAGE_LIMIT_HOURS = 4383  # 6 months in hours


class CPULimit(enum.Enum):
    UNDER_LIMIT = 0
    NEAR_LIMIT = 1
    AT_LIMIT = 2
    OVER_LIMIT = 3


class Expirer(object):

    def __init__(self, project, ks_session=None, dry_run=False):
        self.k_client = auth.get_keystone_client(ks_session)
        self.project = project
        self.project_set_defaults()
        self.dry_run = dry_run
        self.ks_session = ks_session
        self.now = datetime.datetime.now()
        self.archiver = archiver.ResourceArchiver(project=project,
                                                  ks_session=ks_session,
                                                  dry_run=dry_run)

    def project_set_defaults(self):
        self.project.owner = getattr(self.project, 'owner', None)
        self.project.expiry_status = getattr(self.project, 'expiry_status', '')
        self.project.expiry_next_step = getattr(self.project,
                                                'expiry_next_step', '')
        self.project.status = getattr(self.project, 'status', '')
        self.project.expires = getattr(self.project, 'expires', '')

    def _update_project(self, **kwargs):
        today = self.now.strftime(DATE_FORMAT)
        kwargs.update({'expiry_updated_at': today})
        if not self.dry_run:
            self.k_client.projects.update(self.project.id, **kwargs)
        if 'expiry_status' in kwargs.keys():
            self.project.expiry_status = kwargs['expiry_status']
        if 'expiry_next_step' in kwargs.keys():
            self.project.expiry_next_step = kwargs['expiry_next_step']
        msg = '%s: Updating %s' % (self.project.id, kwargs)
        LOG.debug(msg)

    def check_archiving_status(self):
        LOG.debug("%s: Checking archive status", self.project.id)
        if self.archiver.is_archive_successful():
            LOG.info("%s: Archive successful", self.project.id)
            self._update_project(expiry_status=expiry_states.ARCHIVED)
        else:
            LOG.debug("%s: Retrying archiving", self.project.id)
            self.archive_project()

    def archive_project(self):
        LOG.info("%s: Archiving project", self.project.id)
        self.archiver.archive_resources()

    def delete_resources(self):
        resources = self.archiver.delete_resources()
        return resources

    def get_status(self):
        status = self.project.expiry_status
        if not status:
            status = self.project.status
            if status:
                LOG.debug("%s: Converting legacy 'status' variable",
                          self.project.id)
                self._update_project(status='',
                                     expiry_status=self.project.status)
                self.project.expiry_status = status
            else:
                self.project.expiry_status = expiry_states.ACTIVE
        return self.project.expiry_status

    def get_next_step_date(self):
        expiry_next_step = self.project.expiry_next_step
        if not expiry_next_step:
            LOG.debug("%s: Converting legacy 'expires' variable",
                      self.project.id)
            expiry_next_step = self.project.expires
            if expiry_next_step:
                self._update_project(expiry_next_step=self.project.expires,
                                     expires='')

        if not expiry_next_step:
            LOG.debug('No "next step" date set')
            return None
        try:
            return datetime.datetime.strptime(expiry_next_step,
                                              DATE_FORMAT)
        except ValueError:
            LOG.error('Invalid expiry_next_step date: %s for project %s',
                      expiry_next_step, self.project.id)
        return None

    def at_next_step(self):
        expires = self.get_next_step_date()
        if expires and expires <= self.now:
            LOG.debug('%s: Ready for next step (%s)', self.project.id, expires)
            return True
        else:
            LOG.debug('%s: Not yet ready for next step (%s)',
                      self.project.id, expires)
            return False

    def delete_project(self):
        LOG.info("%s: Deleting project", self.project.id)
        self.archiver.delete_resources(force=True)
        self.archiver.delete_archives()
        today = self.now.strftime(DATE_FORMAT)
        self._update_project(expiry_status=expiry_states.DELETED,
                             expiry_next_step='',
                             expiry_deleted_at=today)


class AllocationExpirer(Expirer):

    def __init__(self, project, ks_session=None, dry_run=False,
                 force_no_allocation=False, force_delete=False):
        super(AllocationExpirer, self).__init__(project, ks_session, dry_run)
        self.allocation_api = allocations.NectarAllocationSession(
            CONF.allocations.api_url,
            CONF.allocations.username,
            CONF.allocations.password)
        self.allocation = None
        self.force_no_allocation = force_no_allocation
        self.force_delete = force_delete
        self.notifier = notifier.FreshDeskNotifier(
            project=project, template_dir='allocations',
            group_id=CONF.freshdesk.allocation_group,
            subject="Nectar Project Allocation Renewal - %s" % project.name,
            ks_session=ks_session, dry_run=dry_run)

    def process(self):
        if not self.should_process_project():
            raise exceptions.InvalidProjectAllocation()
        try:
            allocation = self.allocation_api.get_current_allocation(
                self.project.id)
            self.allocation = allocation
        except exceptions.AllocationDoesNotExist:
            LOG.warn("%s: Allocation can not be found", self.project.id)
            if self.force_no_allocation:
                allocation = {'status': 'A',
                              'start_date': '1970-01-01',
                              'end_date': '1970-01-01'}
            else:
                raise exceptions.AllocationDoesNotExist(
                    project_id=self.project.id)

        allocation_status = allocation['status']

        allocation_start = datetime.datetime.strptime(
            allocation['start_date'], DATE_FORMAT)
        allocation_end = datetime.datetime.strptime(
            allocation['end_date'], DATE_FORMAT)

        expiry_status = self.get_status()
        expiry_next_step = self.get_next_step_date()

        LOG.debug("%s: expiry_status: %s, expiry_next_step: %s",
                  self.project.id, expiry_status, expiry_next_step)

        if self.force_delete:
            LOG.info("%s: Force deleting project", self.project.id)
            self.delete_project()
            return True

        if allocation_status != allocation_states.APPROVED:
            return False

        if expiry_status == expiry_states.ADMIN:
            LOG.debug("%s Ignoring, project is admin", self.project.id)
            return False
        elif expiry_status == expiry_states.ACTIVE:
            allocation_days = (allocation_end - allocation_start).days
            warning_date = allocation_start + datetime.timedelta(
                days=allocation_days * 0.8)
            month_out = allocation_end - datetime.timedelta(days=30)
            if warning_date < month_out:
                warning_date = month_out

            if warning_date < self.now:
                self.send_warning()
                return True

        elif expiry_status == expiry_states.WARNING:
            if self.at_next_step():
                self.restrict_project()
                return True

        elif expiry_status == expiry_states.RESTRICTED:
            if self.at_next_step():
                self.stop_project()
                return True

        elif expiry_status == expiry_states.STOPPED:
            if self.at_next_step():
                three_months = (
                    self.now + datetime.timedelta(days=90)).strftime(
                        DATE_FORMAT)
                self._update_project(expiry_status=expiry_states.ARCHIVING,
                                     expiry_next_step=three_months)
                self.archive_project()
                return True

        elif expiry_status == expiry_states.ARCHIVING:
            if self.at_next_step():
                LOG.debug("%s: Archiving longer than next step, move on",
                          self.project.id)
                self._update_project(expiry_status=expiry_states.ARCHIVED)
                return True
            else:
                self.check_archiving_status()

        elif expiry_status == expiry_states.ARCHIVED:
            if self.at_next_step():
                self.delete_project()
            else:
                self.delete_resources()
            return True
        else:
            try:
                new_status = expiry_states.DEPRECATED_STATE_MAP[expiry_status]
                LOG.warn("%s: Converting deprecated status %s",
                         self.project.id, expiry_status)
            except KeyError:
                LOG.error("%s: Invalid status %s setting to active",
                          self.project.id, expiry_status)
                new_status = expiry_states.ACTIVE
            self._update_project(expiry_status=new_status)
            LOG.info("%s: Retrying with new status", self.project.id)
            self.process()

    def should_process_project(self):
        return not PT_RE.match(self.project.name)

    def send_warning(self):
        LOG.info("%s: Sending warning", self.project.id)
        one_month = (self.now +
                     datetime.timedelta(days=30)).strftime(DATE_FORMAT)

        self._update_project(expiry_status=expiry_states.WARNING,
                             expiry_next_step=one_month)
        self.notifier.send_message(
            'first', extra_context={'expiry_date': one_month,
                                    'allocation': self.allocation})

    def restrict_project(self):
        LOG.info("%s: Restricting project", self.project.id)
        self.archiver.zero_quota()

        one_month = (self.now + datetime.timedelta(days=30)).strftime(
            DATE_FORMAT)
        self._update_project(expiry_status=expiry_states.RESTRICTED,
                             expiry_next_step=one_month)
        self.notifier.send_message('final')

    def stop_project(self):
        LOG.info("%s: Stopping project", self.project.id)
        self.archiver.stop_resources()
        one_month = (self.now + datetime.timedelta(days=30)).strftime(
            DATE_FORMAT)
        self._update_project(expiry_status=expiry_states.STOPPED,
                             expiry_next_step=one_month)


class PTExpirer(Expirer):

    def __init__(self, project, ks_session=None, dry_run=False):
        super(PTExpirer, self).__init__(project, ks_session, dry_run)
        self.project_set_defaults()
        self.n_client = auth.get_nova_client(ks_session)
        self.notifier = notifier.FreshDeskNotifier(
            project=project, template_dir='pts',
            group_id=CONF.freshdesk.pt_group,
            subject="Nectar Project Trial Expiry - %s" % project.name,
            ks_session=ks_session, dry_run=dry_run)

    def should_process_project(self):
        has_owner = self.project.owner is not None
        personal = self.is_personal_project()
        if personal and not has_owner:
            LOG.warn("%s: Project has no owner", self.project.id)
        return personal and has_owner and not self.is_ignored_project()

    def is_personal_project(self):
        return PT_RE.match(self.project.name)

    def is_ignored_project(self):
        status = self.get_status()
        if status is None:
            return False
        elif status == expiry_states.ADMIN:
            LOG.debug('Project %s is admin. Will never expire',
                      self.project.id)
            return True
        elif status.startswith('ticket-'):
            url = 'https://support.ehelp.edu.au/helpdesk/tickets/%s' \
                  % status.rsplit('-', 1)[1]
            LOG.warn('Project %s is ignored. See %s', self.project.id, url)
            return True
        return False

    def process(self):
        if not self.should_process_project():
            raise exceptions.InvalidProjectTrial()

        status = self.get_status()
        LOG.debug("%s: Processing project %s status: %s",
                  self.project.id, self.project.name, status)

        if status in [expiry_states.ARCHIVED, expiry_states.ARCHIVE_ERROR]:
            if self.at_next_step():
                self.delete_project()
                return True
            else:
                resources = self.delete_resources()
                if resources:
                    return True

        elif status == expiry_states.SUSPENED:
            if self.at_next_step():
                self.archive_project()

        elif status == expiry_states.ARCHIVING:
            self.check_archiving_status()

        elif status == expiry_states.DELETED:
            return False

        else:
            try:
                limit = self.check_cpu_usage()
                return self.notify(limit)
            except exceptions.NoUsageError:
                LOG.debug("%s: Usage is None", self.project.id)
            except Exception as e:
                LOG.error("Failed to get usage for project %s",
                          self.project.id)
                LOG.error(e)

    def check_cpu_usage(self):
        limit = USAGE_LIMIT_HOURS
        start = datetime.datetime(2011, 1, 1)
        end = self.now + relativedelta(days=1)
        usage = self.n_client.usage.get(self.project.id, start, end)
        cpu_hours = getattr(usage, 'total_vcpus_usage', None)

        if cpu_hours is None:
            raise exceptions.NoUsageError()

        LOG.debug("%s: Total VCPU hours: %s", self.project.id, cpu_hours)

        if cpu_hours < limit * 0.8:
            return CPULimit.UNDER_LIMIT
        elif cpu_hours < limit:
            return CPULimit.NEAR_LIMIT
        elif cpu_hours < limit * 1.2:
            return CPULimit.AT_LIMIT
        elif cpu_hours >= limit * 1.2:
            return CPULimit.OVER_LIMIT

    def notify(self, event):
        limits = {
            CPULimit.UNDER_LIMIT: lambda *x: False,
            CPULimit.NEAR_LIMIT: self.notify_near_limit,
            CPULimit.AT_LIMIT: self.notify_at_limit,
            CPULimit.OVER_LIMIT: self.notify_over_limit
        }
        if event != CPULimit.UNDER_LIMIT:
            LOG.debug(event)
        return limits[event]()

    def notify_near_limit(self):
        if self.get_status() == expiry_states.QUOTA_WARNING:
            return False

        LOG.info("%s: Usage is over 80%% - setting status to quota warning",
                 self.project.id)
        self.notifier.send_message('first')
        # 18 days minium time for 2 cores usage 80% -> 100%
        next_step = (self.now + relativedelta(days=18)).strftime(DATE_FORMAT)
        self._update_project(expiry_status=expiry_states.QUOTA_WARNING,
                             expiry_next_step=next_step)
        return True

    def notify_at_limit(self):
        if self.get_status() == expiry_states.PENDING_SUSPENSION:
            LOG.debug("Usage OK for now, ignoring")
            return False

        LOG.info("%s: Usage is over 100%%, setting status to "
                 "pending suspension", self.project.id)
        self.archiver.zero_quota()
        new_expiry = self.now + relativedelta(months=1)
        new_expiry = new_expiry.strftime(DATE_FORMAT)
        self._update_project(expiry_status=expiry_states.PENDING_SUSPENSION,
                             expiry_next_step=new_expiry)
        self.notifier.send_message('second')
        return True

    def notify_over_limit(self):
        if self.get_status() != expiry_states.PENDING_SUSPENSION:
            return self.notify_at_limit()
        if not self.at_next_step():
            return False

        LOG.info("%s: Usage is over 120%%, suspending project",
                 self.project.id)

        self.archiver.zero_quota()
        self.archiver.stop_resources()
        new_expiry = self.now + relativedelta(months=1)
        new_expiry = new_expiry.strftime(DATE_FORMAT)
        self._update_project(expiry_status=expiry_states.SUSPENED,
                             expiry_next_step=new_expiry)
        self.notifier.send_message('final')
        return True
