import datetime
from dateutil.relativedelta import relativedelta
import enum
import logging
import re

from nectar_tools import auth
from nectar_tools import config

from nectar_tools import allocations
from nectar_tools.allocations import states as allocation_states
from nectar_tools import exceptions
from nectar_tools.expiry import archiver
from nectar_tools.expiry import expiry_states
from nectar_tools import notifier as expiry_notifier


CONF = config.CONFIG
LOG = logging.getLogger(__name__)

DATE_FORMAT = '%Y-%m-%d'
DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%SZ'

PT_RE = re.compile(r'^pt-\d+$')
USAGE_LIMIT_HOURS = 4383  # 6 months in hours


class CPULimit(enum.Enum):
    UNDER_LIMIT = 0
    NEAR_LIMIT = 1
    AT_LIMIT = 2
    OVER_LIMIT = 3


class Expirer(object):

    def __init__(self, project, archivers, notifier, ks_session=None,
                 dry_run=False, disable_project=False):
        self.k_client = auth.get_keystone_client(ks_session)
        self.project = project
        self.project_set_defaults()
        self.dry_run = dry_run
        self.ks_session = ks_session
        self.now = datetime.datetime.now()
        self.disable_project = disable_project
        self.archiver = archiver.ResourceArchiver(project=project,
                                                  archivers=archivers,
                                                  ks_session=ks_session,
                                                  dry_run=dry_run)
        self.notifier = notifier
        self.managers = None
        self.members = None

    def project_set_defaults(self):
        self.project.owner = getattr(self.project, 'owner', None)
        self.project.expiry_status = getattr(self.project, 'expiry_status', '')
        self.project.expiry_next_step = getattr(self.project,
                                                'expiry_next_step', '')
        self.project.expiry_ticket_id = getattr(self.project,
                                                'expiry_ticket_id', 0)

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

    def _get_project_managers(self):
        if self.managers is None:
            role = CONF.keystone.manager_role_id
            self.managers = self._get_users_by_role(role)
        return self.managers

    def _get_project_members(self):
        if self.members is None:
            role = CONF.keystone.member_role_id
            self.members = self._get_users_by_role(role)
        return self.members

    def _get_users_by_role(self, role):
        members = self.k_client.role_assignments.list(
            project=self.project, role=role)
        users = []
        for member in members:
            users.append(self.k_client.users.get(member.user['id']))
        return users

    def check_archiving_status(self):
        LOG.debug("%s: Checking archive status", self.project.id)
        if self.archiver.is_archive_successful():
            LOG.info("%s: Archive successful", self.project.id)
            self._update_project(expiry_status=expiry_states.ARCHIVED)
        else:
            LOG.debug("%s: Retrying archiving", self.project.id)
            self.archive_project()

    def archive_project(self):
        if self.project.expiry_status != expiry_states.ARCHIVING:
            LOG.info("%s: Archiving project", self.project.id)
            three_months = (
                self.now + datetime.timedelta(days=90)).strftime(
                    DATE_FORMAT)
            self._update_project(expiry_status=expiry_states.ARCHIVING,
                                 expiry_next_step=three_months)

        self.archiver.archive_resources()

    def delete_resources(self):
        resources = self.archiver.delete_resources()
        return resources

    def get_status(self):
        status = self.project.expiry_status
        if not status:
            self.project.expiry_status = expiry_states.ACTIVE
        return self.project.expiry_status

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

    def get_next_step_date(self):
        expiry_next_step = self.project.expiry_next_step

        if not expiry_next_step:
            return None
        try:
            return datetime.datetime.strptime(expiry_next_step, DATE_FORMAT)
        except ValueError:
            LOG.error('%s: Invalid expiry_next_step date: %s',
                      self.project.id, expiry_next_step)
        return None

    def at_next_step(self):
        next_step = self.get_next_step_date()
        if not next_step:
            return True
        if next_step <= self.now:
            LOG.debug('%s: Ready for next step (%s)', self.project.id,
                      next_step)
            return True
        else:
            LOG.debug('%s: Not yet ready for next step (%s)',
                      self.project.id, next_step)
            return False

    def delete_project(self):
        LOG.info("%s: Deleting project", self.project.id)
        self.archiver.delete_resources(force=True)
        self.archiver.delete_archives()
        self.notifier.finish(message="Project deleted")
        today = self.now.strftime(DATE_FORMAT)
        self._update_project(expiry_status=expiry_states.DELETED,
                             expiry_next_step='',
                             expiry_deleted_at=today)

        if self.disable_project:
            LOG.info("%s: Disabling project", self.project.id)
            self._update_project(enabled=False)

    def _get_notification_context(self):
        return {}

    def _get_recipients(self):
        return (None, [])

    def _send_notification(self, stage, extra_context={}):
        context = self._get_notification_context()
        context.update(extra_context)
        recipient, extras = self._get_recipients()
        self.notifier.send_message(stage, recipient, extra_context=context,
                                   extra_recipients=extras)


class AllocationExpirer(Expirer):

    def __init__(self, project, ks_session=None, dry_run=False,
                 force_no_allocation=False, force_delete=False,
                 disable_project=False):
        archivers = ['nova', 'cinder', 'neutron', 'glance', 'swift']

        notifier = expiry_notifier.FreshDeskNotifier(
            project=project, template_dir='allocations',
            group_id=CONF.freshdesk.allocation_group,
            subject="Nectar Project Allocation Renewal - %s" % project.name,
            ks_session=ks_session, dry_run=dry_run)

        super(AllocationExpirer, self).__init__(
            project, archivers, notifier, ks_session, dry_run, disable_project)

        self.allocation_api = allocations.AllocationManager(
            CONF.allocations.api_url,
            CONF.allocations.username,
            CONF.allocations.password)
        self.force_no_allocation = force_no_allocation
        self.force_delete = force_delete
        self.allocation = self.get_allocation()

    def get_allocation(self):
        try:
            allocation = self.allocation_api.get_current_allocation(
                self.project.id)
        except exceptions.AllocationDoesNotExist:
            if self.is_ignored_project():
                return
            LOG.warn("%s: Allocation can not be found", self.project.id)
            if self.force_no_allocation:
                allocation = allocations.Allocation(
                    None,
                    {'id': 'NO-ALLOCATION',
                     'status': allocation_states.APPROVED,
                     'start_date': '1970-01-01',
                     'end_date': '1970-01-01'},
                    None)
            else:
                raise exceptions.AllocationDoesNotExist(
                    project_id=self.project.id)

        allocation_status = allocation.status

        if allocation_status in (allocation_states.UPDATE_DECLINED,
                                 allocation_states.UPDATE_PENDING,
                                 allocation_states.DECLINED):

            two_months_ago = self.now - relativedelta(months=2)
            mod_time = datetime.datetime.strptime(
                allocation.modified_time, DATETIME_FORMAT)
            if mod_time < two_months_ago:
                approved = self.allocation_api.get_last_approved_allocation(
                    self.project.id)
                if approved:
                    LOG.debug("%s: Allocation has old unapproved application, "
                              "using last approved allocation",
                              self.project.id)
                    LOG.debug("%s: Changing allocation from %s to %s",
                              self.project.id, allocation.id,
                              approved.id)
                    allocation = approved

        allocation_status = allocation.status
        allocation_start = datetime.datetime.strptime(
            allocation.start_date, DATE_FORMAT)
        allocation_end = datetime.datetime.strptime(
            allocation.end_date, DATE_FORMAT)
        LOG.debug("%s: Allocation id=%s, status='%s', start=%s, end=%s",
                  self.project.id, allocation.id,
                  allocation_states.STATES[allocation_status],
                  allocation_start.date(), allocation_end.date())
        return allocation

    def process(self):

        expiry_status = self.get_status()
        expiry_next_step = self.get_next_step_date()

        LOG.debug("%s: Processing project=%s status=%s next_step=%s",
                  self.project.id, self.project.name, expiry_status,
                  expiry_next_step)

        if self.force_delete:
            LOG.info("%s: Force deleting project", self.project.id)
            self.delete_project()
            return True

        if not self.should_process_project():
            raise exceptions.InvalidProjectAllocation()

        if expiry_status == expiry_states.RENEWED:
            self.revert_expiry()
            return True

        if expiry_status == expiry_states.DELETED:
            return False

        elif expiry_status == expiry_states.ACTIVE:
            if self.allocation_ready_for_warning():
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
                self.archive_project()
                return True

        elif expiry_status == expiry_states.ARCHIVING:
            if self.at_next_step():
                LOG.debug("%s: Archiving longer than next step, move on",
                          self.project.id)
                self._update_project(expiry_status=expiry_states.ARCHIVED)
            else:
                self.check_archiving_status()
            return True

        elif expiry_status == expiry_states.ARCHIVED:
            if self.at_next_step():
                self.delete_project()
            else:
                self.delete_resources()
            return True
        else:
            LOG.error("%s: Invalid status %s", self.project.id, expiry_status)

    def allocation_ready_for_warning(self):

        allocation_start = datetime.datetime.strptime(
            self.allocation.start_date, DATE_FORMAT)
        allocation_end = datetime.datetime.strptime(
            self.allocation.end_date, DATE_FORMAT)

        allocation_days = (allocation_end - allocation_start).days
        warning_date = allocation_start + datetime.timedelta(
            days=allocation_days * 0.8)
        month_out = allocation_end - datetime.timedelta(days=30)
        if warning_date < month_out:
            warning_date = month_out

        return warning_date < self.now

    def revert_expiry(self):
        LOG.info("%s: Allocation has been renewed, reverting expiry",
                 self.project.id)

        self.archiver.reset_quota()
        self.archiver.enable_resources()

        self.notifier.finish(message="Allocation has been renewed")

        update = {}
        if self.project.expiry_status:
            update['expiry_status'] = ''
        if self.project.expiry_next_step:
            update['expiry_next_step'] = ''
        if self.project.expiry_ticket_id:
            update['expiry_ticket_id'] = 0
        if update:
            self._update_project(**update)

    def should_process_project(self):
        if PT_RE.match(self.project.name):
            return False

        if self.is_ignored_project():
            return False

        if self.get_status() == expiry_states.RENEWED:
            return True

        allocation_status = self.allocation.status
        if allocation_status == allocation_states.APPROVED:
            return True
        elif allocation_status == allocation_states.UPDATE_PENDING:
            LOG.debug("%s: Skipping, allocation is pending modified=%s",
                      self.project.id, self.allocation.modified_time)
            return False
        else:
            LOG.error("%s: Can't process allocation, state='%s'",
                      self.project.id,
                      allocation_states.STATES[allocation_status])
            return False

        return True

    def _get_recipients(self):
        owner_email = self.allocation.contact_email.lower()
        approver_email = self.allocation.approver_email.lower()
        managers = self._get_project_managers()

        manager_emails = []
        member_emails = []
        for manager in managers:
            if manager.enabled and manager.email:
                manager_emails.append(manager.email.lower())

        members = self._get_project_members()
        for member in members:
            if member.enabled and member.email:
                member_emails.append(member.email.lower())

        extra_emails = list(set(manager_emails + member_emails))
        if approver_email and approver_email not in extra_emails:
            extra_emails.append(approver_email)
        if owner_email in extra_emails:
            extra_emails.remove(owner_email)
        return (owner_email, extra_emails)

    def _get_notification_context(self):
        managers = self._get_project_managers()
        members = self._get_project_members()
        context = {'managers': managers,
                   'members': members,
                   'allocation': self.allocation}
        return context

    def send_warning(self):
        LOG.info("%s: Sending warning", self.project.id)
        one_month = (self.now +
                     datetime.timedelta(days=30)).strftime(DATE_FORMAT)

        self._update_project(expiry_status=expiry_states.WARNING,
                             expiry_next_step=one_month)
        self._send_notification(
            'first', extra_context={'expiry_date': one_month})

    def restrict_project(self):
        LOG.info("%s: Restricting project", self.project.id)
        self.archiver.zero_quota()

        one_month = (self.now + datetime.timedelta(days=30)).strftime(
            DATE_FORMAT)
        self._update_project(expiry_status=expiry_states.RESTRICTED,
                             expiry_next_step=one_month)
        self._send_notification('final')

    def stop_project(self):
        LOG.info("%s: Stopping project", self.project.id)
        self.archiver.stop_resources()
        one_month = (self.now + datetime.timedelta(days=30)).strftime(
            DATE_FORMAT)
        self._update_project(expiry_status=expiry_states.STOPPED,
                             expiry_next_step=one_month)


class PTExpirer(Expirer):

    def __init__(self, project, ks_session=None, dry_run=False,
                 disable_project=False, force_delete=False):
        archivers = ['nova', 'neutron_basic', 'swift']
        notifier = expiry_notifier.FreshDeskNotifier(
            project=project, template_dir='pts',
            group_id=CONF.freshdesk.pt_group,
            subject="Nectar Project Trial Expiry - %s" % project.name,
            ks_session=ks_session, dry_run=dry_run)

        super(PTExpirer, self).__init__(project, archivers, notifier,
                                        ks_session, dry_run, disable_project)
        self.project_set_defaults()
        self.n_client = auth.get_nova_client(ks_session)
        self.force_delete = force_delete

    def should_process_project(self):
        has_owner = self.project.owner is not None
        personal = self.is_personal_project()
        if personal and not has_owner:
            LOG.warn("%s: Project has no owner", self.project.id)
        return personal and has_owner and not self.is_ignored_project()

    def is_personal_project(self):
        return PT_RE.match(self.project.name)

    def process(self):
        if self.force_delete:
            self.delete_project()
            return True

        if not self.should_process_project():
            raise exceptions.InvalidProjectTrial()

        status = self.get_status()
        self.get_next_step_date()

        LOG.debug("%s: Processing project %s status: %s",
                  self.project.id, self.project.name, status)

        if status in [expiry_states.ARCHIVED, expiry_states.ARCHIVE_ERROR]:
            if self.at_next_step():
                self.delete_project()
                return True
            else:
                self.delete_resources()
                return False

        elif status == expiry_states.SUSPENDED:
            if self.at_next_step():
                self.archive_project()
                return True

        elif status == expiry_states.ARCHIVING:
            if self.at_next_step():
                LOG.debug("%s: Archiving longer than next step, move on",
                          self.project.id)
                self._update_project(expiry_status=expiry_states.ARCHIVED)
            else:
                self.check_archiving_status()
            return True

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
        end = (self.now + relativedelta(days=1))
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
        self._send_notification('first')
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
        self._send_notification('second')
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
        self._update_project(expiry_status=expiry_states.SUSPENDED,
                             expiry_next_step=new_expiry)
        self._send_notification('final')
        return True

    def _get_recipients(self):
        return (self.project.owner.email, [])

    def _get_notification_context(self):
        return {}
