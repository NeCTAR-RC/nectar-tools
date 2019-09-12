import datetime
from dateutil.relativedelta import relativedelta
import enum
import logging
from oslo_context import context
import oslo_messaging
import re

from nectarallocationclient import exceptions as allocation_exceptions
from nectarallocationclient import states as allocation_states
from nectarallocationclient.v1 import allocations

from nectar_tools import auth
from nectar_tools import config
from nectar_tools import exceptions
from nectar_tools import utils

from nectar_tools.expiry import archiver
from nectar_tools.expiry import expiry_states
from nectar_tools.expiry import notifier as expiry_notifier


CONF = config.CONFIG
LOG = logging.getLogger(__name__)
OSLO_CONF = config.OSLO_CONF
OSLO_CONTEXT = context.RequestContext()

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

    STATUS_KEY = 'expiry_status'
    NEXT_STEP_KEY = 'expiry_next_step'
    TICKET_ID_KEY = 'expiry_ticket_id'
    UPDATED_AT_KEY = 'expiry_updated_at'

    def __init__(self, resource_type, resource, notifier,
                 ks_session=None, dry_run=False):
        self.k_client = auth.get_keystone_client(ks_session)
        self.dry_run = dry_run
        self.ks_session = ks_session
        self.now = datetime.datetime.now()
        self.notifier = notifier
        self.managers = None
        self.members = None
        self.resource_type = resource_type
        self.resource = resource

        transport = oslo_messaging.get_notification_transport(OSLO_CONF)
        self.event_notifier = oslo_messaging.Notifier(transport, 'expiry')
        target = oslo_messaging.Target(exchange='openstack',
                                       topic='notifications')
        for queue in CONF.events.notifier_queues.split(','):
            transport._driver.listen_for_notifications([(target, 'audit')],
                                                       queue, 1, 1)

    def _get_project_managers(self):
        if self.managers is None:
            role = CONF.keystone.manager_role_id
            project = self.get_project()
            self.managers = self._get_users_by_role(project, role)
        return self.managers

    def _get_project_members(self):
        if self.members is None:
            role = CONF.keystone.member_role_id
            project = self.get_project()
            self.members = self._get_users_by_role(project, role)
        return self.members

    def _get_users_by_role(self, project, role):
        members = self.k_client.role_assignments.list(
            project=project, role=role)
        users = []
        for member in members:
            users.append(self.k_client.users.get(member.user['id']))
        return users

    def get_project(self):
        raise NotImplementedError

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

    def send_event(self, event, extra_context={}):
        return

    def _send_event(self, event_type, payload):
        if self.dry_run:
            LOG.info('%s: Would send event %s' % (self.resource.id,
                                                  event_type))
            return
        self.event_notifier.audit(OSLO_CONTEXT, event_type, payload)

    def delete_resources(self):
        resources = self.archiver.delete_resources()
        return resources

    def get_status(self, resource):
        if not hasattr(resource, self.STATUS_KEY) or \
           not getattr(resource, self.STATUS_KEY):
            setattr(resource, self.STATUS_KEY, expiry_states.ACTIVE)
        return getattr(resource, self.STATUS_KEY)

    def get_next_step_date(self, resource):
        if not hasattr(resource, self.NEXT_STEP_KEY) or \
           not getattr(resource, self.NEXT_STEP_KEY):
            return None
        try:
            expiry_next_step = getattr(resource, self.NEXT_STEP_KEY)
            return datetime.datetime.strptime(expiry_next_step, DATE_FORMAT)
        except ValueError:
            LOG.error('%s: Invalid %s date: %s',
                      resource.id, self.NEXT_STEP_KEY, expiry_next_step)
        return None

    def at_next_step(self, resource):
        next_step = self.get_next_step_date(resource)
        if not next_step:
            return True
        if next_step <= datetime.datetime.now():
            LOG.debug('%s: Ready for next step (%s)', resource.id,
                      next_step)
            return True
        else:
            LOG.debug('%s: Not yet ready for next step (%s)',
                      resource.id, next_step)
            return False

    @staticmethod
    def make_next_step_date(now, days=14):
        # If date within 15 December and 31 January, allow more 16 days
        if (now.month == 12 and now.day >= 15) or now.month == 1:
            next_step_date = now + relativedelta(days=days + 16)
        else:
            next_step_date = now + relativedelta(days=days)
        return next_step_date.strftime(DATE_FORMAT)


class ProjectExpirer(Expirer):

    def __init__(self, project, archivers, notifier, ks_session=None,
                 dry_run=False, disable_project=False):
        super(ProjectExpirer, self).__init__(
            'project', project, notifier, ks_session, dry_run)
        self.project = project
        self.project_set_defaults()
        self.disable_project = disable_project
        self.archiver = archiver.ResourceArchiver(project,
                                                  archivers=archivers,
                                                  ks_session=ks_session,
                                                  dry_run=dry_run)

    def get_project(self):
        return self.project

    def project_set_defaults(self):
        self.project.owner = getattr(self.project, 'owner', None)
        self.project.expiry_status = getattr(self.project, 'expiry_status', '')
        self.project.expiry_next_step = getattr(self.project,
                                                'expiry_next_step', '')
        self.project.expiry_ticket_id = getattr(self.project,
                                                'expiry_ticket_id', 0)

    def _update_project(self, **kwargs):
        today = self.now.strftime(DATE_FORMAT)
        kwargs.update({self.UPDATED_AT_KEY: today})
        if not self.dry_run:
            self.k_client.projects.update(self.project.id, **kwargs)
        if self.STATUS_KEY in kwargs.keys():
            setattr(self.project, self.STATUS_KEY,
                    kwargs[self.STATUS_KEY])
        if self.NEXT_STEP_KEY in kwargs.keys():
            setattr(self.project, self.NEXT_STEP_KEY,
                    kwargs[self.NEXT_STEP_KEY])
        msg = '%s: Updating %s' % (self.project.id, kwargs)
        LOG.debug(msg)

    def check_archiving_status(self):
        LOG.debug("%s: Checking archive status", self.project.id)
        if self.archiver.is_archive_successful():
            LOG.info("%s: Archive successful", self.project.id)
            self.set_project_archived()
        else:
            LOG.debug("%s: Retrying archiving", self.project.id)
            self.archive_project()

    def archive_project(self, duration=90):
        """Archive a project's resources. Keep archive for `duration` days"""
        status = self.get_status(self.project)
        if status != expiry_states.ARCHIVING:
            LOG.info("%s: Archiving project", self.project.id)
            next_step = (self.now
                         + datetime.timedelta(days=duration)).strftime(
                    DATE_FORMAT)
            update_kwargs = {self.STATUS_KEY: expiry_states.ARCHIVING,
                             self.NEXT_STEP_KEY: next_step}
            self._update_project(**update_kwargs)

        self.archiver.archive_resources()

    def is_ignored_project(self):
        status = self.get_status(self.project)
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

    def set_project_archived(self):
        update_kwargs = {self.STATUS_KEY: expiry_states.ARCHIVED}
        self._update_project(**update_kwargs)

    def delete_project(self):
        LOG.info("%s: Deleting project", self.project.id)
        self.archiver.delete_resources(force=True)
        self.archiver.delete_archives()
        try:
            self.notifier.finish(message="Project deleted")
        except Exception:
            pass
        today = self.now.strftime(DATE_FORMAT)
        delete_kwargs = {self.STATUS_KEY: expiry_states.DELETED,
                         self.NEXT_STEP_KEY: '',
                         'expiry_deleted_at': today}
        self._update_project(**delete_kwargs)

        if self.disable_project:
            LOG.info("%s: Disabling project", self.project.id)
            self._update_project(enabled=False)
        self.send_event('delete')


class AllocationExpirer(ProjectExpirer):

    EVENT_PREFIX = 'expiry.allocation'

    def __init__(self, project, ks_session=None, dry_run=False,
                 force_no_allocation=False, force_delete=False,
                 disable_project=True, archivers=['nova', 'cinder', 'neutron',
                 'projectimages', 'swift'], template_dir='allocations',
                 subject='Nectar Project Allocation Renewal - '):

        notifier = expiry_notifier.ExpiryNotifier(
            resource_type='project', resource=project,
            template_dir=template_dir,
            group_id=CONF.freshdesk.allocation_group,
            subject=subject + project.name,
            ks_session=ks_session, dry_run=dry_run,
            ticket_id_key=self.TICKET_ID_KEY)

        super(AllocationExpirer, self).__init__(
            project, archivers, notifier, ks_session, dry_run, disable_project)

        self.a_client = auth.get_allocation_client(ks_session)
        self.force_no_allocation = force_no_allocation
        self.force_delete = force_delete
        self.allocation = self.get_allocation()

    def get_allocation(self):
        try:
            allocation = self.a_client.allocations.get_current(
                project_id=self.project.id)
        except allocation_exceptions.AllocationDoesNotExist:
            if self.is_ignored_project():
                return
            LOG.warn("%s: Allocation can not be found", self.project.id)
            if self.force_no_allocation:
                allocation = allocations.Allocation(
                    None,
                    {'id': 'NO-ALLOCATION',
                     'status': allocation_states.APPROVED,
                     'quotas': [],
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

            six_months_ago = self.now - relativedelta(months=6)
            mod_time = datetime.datetime.strptime(
                allocation.modified_time, DATETIME_FORMAT)
            if mod_time < six_months_ago:
                approved = self.a_client.allocations.get_last_approved(
                    project_id=self.project.id)
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

        expiry_status = self.get_status(self.project)
        expiry_next_step = self.get_next_step_date(self.project)

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
            if self.at_next_step(self.project):
                self.restrict_project()
                return True

        elif expiry_status == expiry_states.RESTRICTED:
            if self.at_next_step(self.project):
                self.stop_project()
                return True

        elif expiry_status == expiry_states.STOPPED:
            if self.at_next_step(self.project):
                self.archive_project()
                return True

        elif expiry_status == expiry_states.ARCHIVING:
            if self.at_next_step(self.project):
                LOG.debug("%s: Archiving longer than next step, move on",
                          self.project.id)
                self.set_project_archived()
            else:
                self.check_archiving_status()
            return True

        elif expiry_status == expiry_states.ARCHIVED:
            if self.at_next_step(self.project):
                self.delete_project()
            else:
                self.delete_resources()
            return True
        else:
            LOG.error("%s: Invalid status %s", self.project.id, expiry_status)

    def get_notice_period_days(self):
        """Get notice period in days.

        The notice period is either 30 days, or the number of days from 80% of
        the length of the allocation until the end -- whichever is shorter.
        """
        allocation_start = datetime.datetime.strptime(
            self.allocation.start_date, DATE_FORMAT)
        allocation_end = datetime.datetime.strptime(
            self.allocation.end_date, DATE_FORMAT)

        allocation_days = (allocation_end - allocation_start).days
        notice_days = int(allocation_days - (allocation_days * 0.8))

        if notice_days > 30:
            return 30

        return notice_days

    def get_expiry_date(self):
        allocation_end = datetime.datetime.strptime(
            self.allocation.end_date, DATE_FORMAT)
        notice_days = self.get_notice_period_days()
        next_step_date = self.now + datetime.timedelta(days=notice_days)
        if allocation_end > next_step_date:
            next_step_date = allocation_end
        return next_step_date.strftime(DATE_FORMAT)

    def get_warning_date(self):
        notice_period = self.get_notice_period_days()
        allocation_end = datetime.datetime.strptime(
            self.allocation.end_date, DATE_FORMAT)
        return allocation_end - datetime.timedelta(days=notice_period)

    def allocation_ready_for_warning(self):
        warning_date = self.get_warning_date()
        return warning_date < self.now

    def revert_expiry(self):
        status = self.get_status(self.project)
        if status == expiry_states.ACTIVE:
            return

        LOG.info("%s: Allocation has been renewed, reverting expiry",
                 self.project.id)

        self.archiver.enable_resources()

        if status in [expiry_states.STOPPED, expiry_states.RESTRICTED,
                      expiry_states.RENEWED]:
            self.archiver.reset_quota()

        self.finish_expiry()

    def finish_expiry(self, message='Allocation has been renewed'):
        try:
            self.notifier.finish(message=message)
        except Exception:
            pass

        update = {}
        if hasattr(self.project, self.STATUS_KEY):
            update[self.STATUS_KEY] = ''
        if hasattr(self.project, self.NEXT_STEP_KEY):
            update[self.NEXT_STEP_KEY] = ''
        if hasattr(self.project, self.TICKET_ID_KEY):
            update[self.TICKET_ID_KEY] = 0
        if update:
            self._update_project(**update)

    def should_process_project(self):

        if not self.project.enabled:
            LOG.debug("%s: Project is disabled", self.project.id)
            return False
        if PT_RE.match(self.project.name):
            return False

        if self.is_ignored_project():
            return False

        if self.get_status(self.project) == expiry_states.RENEWED:
            return True

        allocation_status = self.allocation.status
        if allocation_status == allocation_states.APPROVED:
            return True
        elif allocation_status == allocation_states.UPDATE_PENDING:
            LOG.debug("%s: Skipping, allocation is pending modified=%s",
                      self.project.id, self.allocation.modified_time)
            return False
        else:
            LOG.debug("%s: Can't process allocation, state='%s'",
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
            if manager.enabled and utils.is_email_address(manager.email):
                manager_emails.append(manager.email.lower())

        members = self._get_project_members()
        for member in members:
            if member.enabled and utils.is_email_address(member.email):
                member_emails.append(member.email.lower())

        extra_emails = list(set(manager_emails + member_emails))
        if utils.is_email_address(approver_email) \
            and approver_email not in extra_emails:
            extra_emails.append(approver_email)
        if owner_email in extra_emails:
            extra_emails.remove(owner_email)
        return (owner_email, extra_emails)

    def _get_notification_context(self):
        managers = self._get_project_managers()
        members = self._get_project_members()
        context = {'managers': [i.to_dict() for i in managers],
                   'members': [i.to_dict() for i in members],
                   'allocation': self.allocation.to_dict()}
        return context

    def send_warning(self):
        LOG.info("%s: Sending warning", self.project.id)
        next_step_date = self.get_expiry_date()

        update_kwargs = {self.STATUS_KEY: expiry_states.WARNING,
                         self.NEXT_STEP_KEY: next_step_date}
        self._update_project(**update_kwargs)
        extra_context = {'expiry_date': next_step_date}
        self._send_notification('first-warning', extra_context=extra_context)
        self.send_event('first-warning', extra_context=extra_context)

    def send_event(self, event, extra_context={}):
        event_type = '%s.%s' % (self.EVENT_PREFIX, event)
        event_notification = self._get_notification_context()
        event_notification.update(extra_context)
        self._send_event(event_type, event_notification)

    def _send_notification(self, stage, extra_context={}):
        if self.force_no_allocation:
            LOG.info("%s: Skipping notification due to force no "
                        "allocation being set", self.project.id)
        elif self.allocation.notifications:
            super(AllocationExpirer, self)._send_notification(
                stage, extra_context)

    def restrict_project(self):
        LOG.info("%s: Restricting project", self.project.id)
        self.archiver.zero_quota()

        expiry_date = self.make_next_step_date(self.now)
        restrict_kwargs = {self.STATUS_KEY: expiry_states.RESTRICTED,
                           self.NEXT_STEP_KEY: expiry_date}
        self._update_project(**restrict_kwargs)
        self._send_notification('restrict')
        self.send_event('restrict')

    def stop_project(self):
        LOG.info("%s: Stopping project", self.project.id)
        self.archiver.stop_resources()
        expiry_date = self.make_next_step_date(self.now)
        update_kwargs = {self.STATUS_KEY: expiry_states.STOPPED,
                         self.NEXT_STEP_KEY: expiry_date}
        self._update_project(**update_kwargs)
        self.send_event('stop')

    def set_project_archived(self):
        super(AllocationExpirer, self).set_project_archived()
        self._send_notification('archived')
        self.send_event('archived')

    def delete_project(self):
        super(AllocationExpirer, self).delete_project()
        LOG.info("%s: Deleting allocation", self.allocation.id)
        if self.dry_run or self.force_no_allocation:
            LOG.info("%s: Would delete allocation", self.allocation.id)
        else:
            self.allocation.delete()


class PTExpirer(ProjectExpirer):

    def __init__(self, project, ks_session=None, dry_run=False,
                 disable_project=False, force_delete=False):
        archivers = ['nova', 'neutron_basic', 'swift']
        notifier = expiry_notifier.ExpiryNotifier(
            resource_type='project', resource=project, template_dir='pts',
            group_id=CONF.freshdesk.pt_group,
            subject="Nectar Project Trial Expiry - %s" % project.name,
            ks_session=ks_session, dry_run=dry_run)

        super(PTExpirer, self).__init__(project, archivers, notifier,
                                        ks_session, dry_run, disable_project)
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

        status = self.get_status(self.project)
        self.get_next_step_date(self.project)

        LOG.debug("%s: Processing project %s status: %s",
                  self.project.id, self.project.name, status)

        if status in [expiry_states.ARCHIVED, expiry_states.ARCHIVE_ERROR]:
            if self.at_next_step(self.project):
                self.delete_project()
                return True
            else:
                self.delete_resources()
                return False

        elif status == expiry_states.SUSPENDED:
            if self.at_next_step(self.project):
                self.archive_project()
                return True

        elif status == expiry_states.ARCHIVING:
            if self.at_next_step(self.project):
                LOG.debug("%s: Archiving longer than next step, move on",
                          self.project.id)
                self.set_project_archived()
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
        if self.get_status(self.project) == expiry_states.QUOTA_WARNING:
            return False

        LOG.info("%s: Usage is over 80%% - setting status to quota warning",
                 self.project.id)
        self._send_notification('first-warning')
        self.send_event('first-warning')
        # 18 days minimum time for 2 cores usage 80% -> 100%
        next_step = (self.now + relativedelta(days=18)).strftime(DATE_FORMAT)
        self._update_project(expiry_status=expiry_states.QUOTA_WARNING,
                             expiry_next_step=next_step)
        return True

    def notify_at_limit(self):
        if self.get_status(self.project) == expiry_states.PENDING_SUSPENSION:
            LOG.debug("Usage OK for now, ignoring")
            return False

        LOG.info("%s: Usage is over 100%%, setting status to "
                 "pending suspension", self.project.id)
        self.archiver.zero_quota()

        expiry_date = self.make_next_step_date(self.now)
        self._update_project(expiry_status=expiry_states.PENDING_SUSPENSION,
                             expiry_next_step=expiry_date)
        self._send_notification('second-warning')
        self.send_event('second-warning')
        return True

    def notify_over_limit(self):
        if self.get_status(self.project) != expiry_states.PENDING_SUSPENSION:
            return self.notify_at_limit()
        if not self.at_next_step(self.project):
            return False

        LOG.info("%s: Usage is over 120%%, suspending project",
                 self.project.id)

        self.archiver.zero_quota()
        self.archiver.stop_resources()

        expiry_date = self.make_next_step_date(self.now)
        self._update_project(expiry_status=expiry_states.SUSPENDED,
                             expiry_next_step=expiry_date)
        self._send_notification('suspended')
        self.send_event('suspended')
        return True

    def _get_recipients(self):
        return (self.project.owner.email, [])

    def _get_notification_context(self):
        return {}

    def send_event(self, event, extra_context={}):
        event_type = 'expiry.pt.%s' % event
        event_notification = {'project': self.project.to_dict()}
        event_notification.update(extra_context)
        self._send_event(event_type, event_notification)
