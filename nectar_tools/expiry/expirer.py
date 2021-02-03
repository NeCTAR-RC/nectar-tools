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
THREE_YEARS_IN_DAYS = 1095  # 3 years in days


class CPULimit(enum.Enum):
    UNDER_LIMIT = 0
    NEAR_LIMIT = 1
    AT_LIMIT = 2
    OVER_LIMIT = 3


class ResourceRollback(object):

    def __init__(self, expirer):
        self.expirer = expirer
        self.resource = expirer.resource
        self.kwargs = dict([
            (expirer.STATUS_KEY, getattr(self.resource,
                                         expirer.STATUS_KEY)),
            (expirer.NEXT_STEP_KEY, getattr(self.resource,
                                            expirer.NEXT_STEP_KEY))])

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.rollback()
        # return false to propagate the exception
        return False

    def rollback(self):
        self.expirer._update_resource(**self.kwargs)


class Expirer(object):

    STATUS_KEY = 'expiry_status'
    NEXT_STEP_KEY = 'expiry_next_step'
    TICKET_ID_KEY = 'expiry_ticket_id'
    UPDATED_AT_KEY = 'expiry_updated_at'

    def __init__(self, resource_type, resource, notifier,
                 ks_session=None, dry_run=False):
        self.k_client = auth.get_keystone_client(ks_session)
        self.g_client = auth.get_glance_client(ks_session)
        self.dry_run = dry_run
        self.ks_session = ks_session
        self.now = datetime.datetime.now()
        self.notifier = notifier
        self.managers = None
        self.members = None
        self.resource_type = resource_type
        self.resource = resource
        self._project = None

        transport = oslo_messaging.get_notification_transport(OSLO_CONF)
        self.event_notifier = oslo_messaging.Notifier(transport, 'expiry')
        target = oslo_messaging.Target(exchange='openstack',
                                       topic='notifications')
        for queue in CONF.events.notifier_queues.split(','):
            transport._driver.listen_for_notifications([(target, 'audit')],
                                                       queue, 1, 1)

    @property
    def project(self):
        if self._project is None:
            self._project = self.get_project()
        return self._project

    def _get_project_managers(self):
        if self.managers is None:
            role = CONF.keystone.manager_role_id
            self.managers = self._get_users_by_role(self.project, role)
        return self.managers

    def _get_project_members(self):
        if self.members is None:
            role = CONF.keystone.member_role_id
            self.members = self._get_users_by_role(self.project, role)
        return self.members

    def _get_users_by_role(self, project, role):
        members = self.k_client.role_assignments.list(
            project=project, role=role)
        users = []
        for member in members:
            users.append(self.k_client.users.get(member.user['id']))
        return users

    @staticmethod
    def get_project():
        raise NotImplementedError

    def _get_notification_context(self):
        return {}

    def _get_recipients(self):
        managers = self._get_project_managers()
        members = self._get_project_members()
        manager_emails = []
        member_emails = []
        for manager in managers:
            if manager.enabled and hasattr(manager, 'email') \
               and utils.is_email_address(manager.email):
                manager_emails.append(manager.email.lower())
        for member in members:
            if member.enabled and hasattr(member, 'email') \
               and utils.is_email_address(member.email):
                member_emails.append(member.email.lower())

        extra_emails = list(set(manager_emails + member_emails))
        if not extra_emails:
            return (None, [])

        # By default, recipient will be set as the first project manager
        # or first project member. It will be passed into "to" field of the
        # notification email, while extra_emails will be into 'cc' field
        recipient = manager_emails[0] if manager_emails else member_emails[0]
        extra_emails.remove(recipient)
        return (recipient, extra_emails)

    def _send_notification(self, stage, extra_context={}):
        context = self._get_notification_context()
        context.update(extra_context)
        recipient, extras = self._get_recipients()
        if recipient:
            self.notifier.send_message(stage, recipient, extra_context=context,
                                       extra_recipients=extras)
        else:
            LOG.warn("%s: No valid recipient, skip notification!",
                     self.resource.id)

    def send_event(self, event, extra_context={}):
        return

    def _send_event(self, event_type, payload):
        if self.dry_run:
            LOG.info('%s: Would send event %s', self.resource.id, event_type)
            return
        self.event_notifier.audit(OSLO_CONTEXT, event_type, payload)

    def delete_resources(self, force=False):
        resources = self.archiver.delete_resources(force=force)
        return resources

    def get_status(self):
        if not hasattr(self.resource, self.STATUS_KEY) or \
           not getattr(self.resource, self.STATUS_KEY):
            setattr(self.resource, self.STATUS_KEY, expiry_states.ACTIVE)
        return getattr(self.resource, self.STATUS_KEY)

    def get_next_step_date(self):
        if not hasattr(self.resource, self.NEXT_STEP_KEY) or \
           not getattr(self.resource, self.NEXT_STEP_KEY):
            return None
        try:
            expiry_next_step = getattr(self.resource, self.NEXT_STEP_KEY)
            return datetime.datetime.strptime(expiry_next_step, DATE_FORMAT)
        except ValueError:
            LOG.error('%s: Invalid %s date: %s',
                      self.resource.id, self.NEXT_STEP_KEY, expiry_next_step)
        return None

    def at_next_step(self):
        next_step = self.get_next_step_date()
        if not next_step:
            return True
        if next_step <= datetime.datetime.now():
            LOG.debug('%s: Ready for next step (%s)', self.resource.id,
                      next_step)
            return True
        else:
            LOG.debug('%s: Not yet ready for next step (%s)',
                      self.resource.id, next_step)
            return False

    @staticmethod
    def make_next_step_date(now, days=14):
        # If date within 15 December and 31 January, allow more 16 days
        if (now.month == 12 and now.day >= 15) or now.month == 1:
            next_step_date = now + relativedelta(days=days + 16)
        else:
            next_step_date = now + relativedelta(days=days)
        return next_step_date.strftime(DATE_FORMAT)

    def ready_for_warning(self):
        warning_date = self.get_warning_date()
        return warning_date < self.now

    def get_warning_date(self):
        raise NotImplementedError

    def _update_resource(self, **kwargs):
        today = self.now.strftime(DATE_FORMAT)
        kwargs.update({self.UPDATED_AT_KEY: today})
        if not self.dry_run:
            if self.resource_type == 'project':
                self.k_client.projects.update(self.resource.id, **kwargs)
            if self.resource_type == 'image':
                self.g_client.images.update(self.resource.id, **kwargs)
            msg = '%s - %s: Updating %s' % (self.resource_type,
                                            self.resource.id, kwargs)
        else:
            msg = '%s - %s: Would update %s' % (self.resource_type,
                                                self.resource.id, kwargs)
        LOG.debug(msg)

        if self.STATUS_KEY in kwargs.keys():
            setattr(self.resource, self.STATUS_KEY,
                    kwargs[self.STATUS_KEY])
        if self.NEXT_STEP_KEY in kwargs.keys():
            setattr(self.resource, self.NEXT_STEP_KEY,
                    kwargs[self.NEXT_STEP_KEY])

    def finish_expiry(self, message='Expiry work flow is complete'):
        try:
            self.notifier.finish(message=message)
        except Exception:
            pass

        update = {}
        if hasattr(self.resource, self.STATUS_KEY):
            update[self.STATUS_KEY] = ''
        if hasattr(self.resource, self.NEXT_STEP_KEY):
            update[self.NEXT_STEP_KEY] = ''
        if hasattr(self.resource, self.TICKET_ID_KEY):
            update[self.TICKET_ID_KEY] = '0'
        if update:
            self._update_resource(**update)

    def stop_resource(self):
        LOG.info("%s: Stopping %s", self.resource.id, self.resource_type)
        self.archiver.stop_resources()
        expiry_date = self.make_next_step_date(self.now)
        update_kwargs = {self.STATUS_KEY: expiry_states.STOPPED,
                         self.NEXT_STEP_KEY: expiry_date}
        with ResourceRollback(self):
            self._update_resource(**update_kwargs)
            self._send_notification('stop')
        self.send_event('stop')

    def send_warning(self):
        LOG.info("%s: Sending warning", self.resource.id)
        next_step_date = self.get_expiry_date()

        update_kwargs = {self.STATUS_KEY: expiry_states.WARNING,
                         self.NEXT_STEP_KEY: next_step_date}

        extra_context = {'expiry_date': next_step_date}
        with ResourceRollback(self):
            self._update_resource(**update_kwargs)
            self._send_notification('first-warning',
                                    extra_context=extra_context)
        self.send_event('first-warning', extra_context=extra_context)

    def get_expiry_date(self):
        return self.make_next_step_date(self.now, days=30)


class ProjectExpirer(Expirer):

    def __init__(self, project, archivers, notifier, ks_session=None,
                 dry_run=False, disable_project=False):
        super(ProjectExpirer, self).__init__(
            'project', project, notifier, ks_session, dry_run)
        self.project_set_defaults()
        self.disable_project = disable_project
        self.archiver = archiver.ResourceArchiver(project,
                                                  archivers=archivers,
                                                  ks_session=ks_session,
                                                  dry_run=dry_run)
        self.a_client = auth.get_allocation_client(ks_session)

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

        if not self.should_process():
            raise exceptions.InvalidProject()

        if expiry_status == expiry_states.RENEWED:
            self.revert_expiry()
            return True

        if expiry_status == expiry_states.DELETED:
            return False

        elif expiry_status == expiry_states.ACTIVE:
            if self.ready_for_warning():
                self.send_warning()
                return True

        elif expiry_status == expiry_states.WARNING:
            if self.at_next_step():
                self.restrict_project()
                return True

        elif expiry_status == expiry_states.RESTRICTED:
            if self.at_next_step():
                self.stop_resource()
                return True

        elif expiry_status == expiry_states.STOPPED:
            if self.at_next_step():
                self.archive_project()
                return True

        elif expiry_status == expiry_states.ARCHIVING:
            if self.at_next_step():
                LOG.warn("%s: Archiving longer than next step, move on",
                         self.project.id)
                self.set_project_archived()
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

    def get_project(self):
        return self.resource

    def project_set_defaults(self):
        self.project.owner = getattr(self.project, 'owner', None)
        self.project.expiry_status = getattr(self.project, 'expiry_status', '')
        self.project.expiry_next_step = getattr(self.project,
                                                'expiry_next_step', '')
        self.project.expiry_ticket_id = getattr(self.project,
                                                'expiry_ticket_id', '0')

    def check_archiving_status(self):
        LOG.debug("%s: Checking archive status", self.project.id)
        if self.archiver.is_archive_successful():
            LOG.info("%s: Archive successful", self.project.id)
            self.set_project_archived()
        else:
            LOG.debug("%s: Retrying archiving", self.project.id)
            self.archive_project()

    def restrict_project(self):
        LOG.info("%s: Restricting project", self.project.id)
        self.archiver.zero_quota()

        expiry_date = self.make_next_step_date(self.now)
        restrict_kwargs = {self.STATUS_KEY: expiry_states.RESTRICTED,
                           self.NEXT_STEP_KEY: expiry_date}
        with ResourceRollback(self):
            self._update_resource(**restrict_kwargs)
            self._send_notification('restrict')
        self.send_event('restrict')

    def archive_project(self, duration=90):
        """Archive a project's resources. Keep archive for `duration` days"""
        status = self.get_status()
        if status != expiry_states.ARCHIVING:
            LOG.info("%s: Archiving project", self.project.id)
            next_step = (self.now
                         + datetime.timedelta(days=duration)).strftime(
                    DATE_FORMAT)
            update_kwargs = {self.STATUS_KEY: expiry_states.ARCHIVING,
                             self.NEXT_STEP_KEY: next_step}
            self._update_resource(**update_kwargs)

        self.archiver.archive_resources()

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

    def set_project_archived(self):
        update_kwargs = {self.STATUS_KEY: expiry_states.ARCHIVED}
        self._update_resource(**update_kwargs)
        self.send_event('archived')

    def delete_project(self):
        LOG.info("%s: Deleting project resources", self.project.id)
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
        self._update_resource(**delete_kwargs)

        if self.disable_project:
            LOG.info("%s: Disabling project", self.project.id)
            self._update_resource(enabled=False)
        self.send_event('delete')


class AllocationExpirer(ProjectExpirer):

    EVENT_PREFIX = 'expiry.allocation'

    def __init__(self, project, ks_session=None, dry_run=False,
                 force_no_allocation=False, force_delete=False,
                 disable_project=True,
                 archivers=['nova', 'cinder', 'octavia', 'neutron',
                            'projectimages', 'swift', 'magnum', 'manila'],
                 template_dir='allocations',
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

        self.force_no_allocation = force_no_allocation
        self.force_delete = force_delete
        self.allocation = self.get_allocation()

    def get_current_allocation(self):
        return self.a_client.allocations.get_current(
            project_id=self.project.id)

    def get_allocation(self):
        try:
            allocation = self.get_current_allocation()
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

    def revert_expiry(self):
        status = self.get_status()
        if status == expiry_states.ACTIVE:
            return

        LOG.info("%s: Allocation has been renewed, reverting expiry",
                 self.project.id)

        self.archiver.enable_resources()

        if status in [expiry_states.STOPPED, expiry_states.RESTRICTED,
                      expiry_states.RENEWED]:
            self.archiver.reset_quota()

        self.finish_expiry(message='Allocation has been renewed')

    def should_process(self):

        if not self.project.enabled:
            LOG.debug("%s: Project is disabled", self.project.id)
            return False
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
            LOG.debug("%s: Can't process allocation, state='%s'",
                      self.project.id,
                      allocation_states.STATES[allocation_status])
            return False

        return True

    def _get_recipients(self):
        # For allocation case, the 'to' field of the notification email
        # should be the project allocation owner
        owner_email = self.allocation.contact_email.lower()
        approver_email = self.allocation.approver_email.lower()

        recipient, extra_emails = super(AllocationExpirer,
                                        self)._get_recipients()
        if recipient:
            extra_emails.append(recipient)

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
        else:
            LOG.info("%s: Skipping notification due to allocation "
                     "notifications being set False", self.project.id)

    def delete_project(self):
        super(AllocationExpirer, self).delete_project()

        # Refetch the project's current allocation record.  (At this point
        # self.allocation may be a history record which cannot be deleted.)
        allocation = self.get_current_allocation()
        if allocation.id != self.allocation.id:
            LOG.debug("%s: Change allocation back to %s for deletion",
                      self.project.id, allocation.id)

        LOG.info("%s: Deleting allocation", allocation.id)
        if self.dry_run or self.force_no_allocation:
            LOG.info("%s: Would delete allocation", allocation.id)
        else:
            allocation.delete()


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
        self.m_client = auth.get_manuka_client(ks_session)
        self.force_delete = force_delete

    def should_process(self):
        has_owner = self.project.owner is not None
        personal = self.is_personal_project()
        if personal and not has_owner:
            LOG.warn("%s: Project has no owner", self.project.id)
        allocations = self.pending_allocations()
        if allocations:
            LOG.warn("%s: Skipping expiry due to pending allocations %s",
                     self.project.id, [a.id for a in allocations])
            return False
        return personal and has_owner and not self.is_ignored_project()

    def is_personal_project(self):
        return PT_RE.match(self.project.name)

    def pending_allocations(self):
        if self.project.owner is None:
            return []
        six_months_ago = self.now - relativedelta(months=6)
        return self.a_client.allocations.list(
            contact_email=self.project.owner.name,
            status=allocation_states.SUBMITTED,
            modified_time__lt=six_months_ago.isoformat())

    def ready_for_warning(self):
        limit = None
        try:
            limit = self.check_cpu_usage()
        except exceptions.NoUsageError:
            LOG.debug("%s: Usage is None", self.project.id)
        except Exception as e:
            LOG.error("Failed to get usage for project %s",
                      self.project.id)
            LOG.error(e)

        return limit == CPULimit.OVER_LIMIT or self.is_pt_too_old()

    def is_pt_too_old(self):
        user_id = self.project.owner.id
        account = self.m_client.users.get(user_id)
        six_months_ago = self.now - relativedelta(months=6)
        return account.registered_at < six_months_ago

    def process(self):
        status = self.get_status()
        self.get_next_step_date()

        LOG.debug("%s: Processing project %s status: %s",
                  self.project.id, self.project.name, status)

        # Support deprecated PT states while still around
        if status == expiry_states.SUSPENDED:
            if self.at_next_step():
                self.archive_project()
                return True

        elif status == expiry_states.QUOTA_WARNING:
            if self.at_next_step():
                self.notify_at_limit()

        elif status == expiry_states.PENDING_SUSPENSION:
            if self.at_next_step():
                self.notify_over_limit()

        else:
            return super().process()

    def check_cpu_usage(self):
        limit = USAGE_LIMIT_HOURS
        start = datetime.datetime(2011, 1, 1)
        end = (self.now + relativedelta(days=1))
        usage = self.n_client.usage.get(self.project.id, start, end)
        cpu_hours = getattr(usage, 'total_vcpus_usage', None)

        if cpu_hours is None:
            raise exceptions.NoUsageError()

        LOG.debug("%s: Total VCPU hours: %s", self.project.id, cpu_hours)

        if cpu_hours > limit:
            return CPULimit.OVER_LIMIT
        return CPULimit.UNDER_LIMIT

    def notify_at_limit(self):
        if self.get_status() == expiry_states.PENDING_SUSPENSION:
            LOG.debug("Usage OK for now, ignoring")
            return False

        LOG.info("%s: Usage is over 100%%, setting status to "
                 "pending suspension", self.project.id)
        self.archiver.zero_quota()

        expiry_date = self.make_next_step_date(self.now)
        with ResourceRollback(self):
            self._update_resource(
                expiry_status=expiry_states.PENDING_SUSPENSION,
                expiry_next_step=expiry_date)
            self._send_notification('second-warning')
        self.send_event('second-warning')
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

        expiry_date = self.make_next_step_date(self.now)
        with ResourceRollback(self):
            self._update_resource(expiry_status=expiry_states.SUSPENDED,
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


class AllocationInstanceExpirer(AllocationExpirer):

    STATUS_KEY = 'zone_expiry_status'
    NEXT_STEP_KEY = 'zone_expiry_next_step'
    TICKET_ID_KEY = 'zone_expiry_ticket_id'
    UPDATED_AT_KEY = 'zone_expiry_updated_at'
    EVENT_PREFIX = 'expiry.allocation.instance'

    def __init__(self, project, ks_session=None, dry_run=False,
                 force_delete=False):
        archivers = ['zoneinstance']

        super(AllocationInstanceExpirer, self).__init__(
            project, ks_session=ks_session, dry_run=dry_run,
            force_delete=force_delete, archivers=archivers,
            template_dir='allocation_instances',
            subject="Nectar Allocation Instances Expiry - ")

        self._instances = None

    @property
    def instances(self):
        if self._instances is None:
            self._instances = utils.get_out_of_zone_instances(
                self.ks_session, self.allocation, self.project)
        return self._instances

    def project_set_defaults(self):
        super(AllocationInstanceExpirer, self).project_set_defaults()
        self.project.compute_zones = getattr(self.project,
            'compute_zones', '')
        self.project.zone_expiry_status = getattr(self.project,
            'zone_expiry_status', '')
        self.project.zone_expiry_next_step = getattr(self.project,
            'zone_expiry_next_step', '')
        self.project.zone_expiry_ticket_id = getattr(self.project,
            'zone_expiry_ticket_id', '0')

    def _get_notification_context(self):
        context = super(AllocationInstanceExpirer,
                        self)._get_notification_context()
        extra_context = {'compute_zones': self.project.compute_zones,
                         'out_of_zone_instances': [
                             i.to_dict() for i in self.instances]}
        context.update(extra_context)
        return context

    def get_expiry_date(self):
        return super(ProjectExpirer, self).get_expiry_date()

    def get_warning_date(self):
        start_date = datetime.datetime.strptime(self.allocation.start_date,
                                                DATE_FORMAT)
        return start_date + relativedelta(days=60)

    def should_process(self):
        # if allocation changes to national, expiry should not continue
        # if there is ongoing expiry process, finish it up
        if not self.project.compute_zones:
            if self.project.zone_expiry_status != expiry_states.ACTIVE or \
               self.project.zone_expiry_ticket_id != '0' or \
               self.project.zone_expiry_next_step != '':
                self.finish_expiry(
                    message='Out-of-zone instances expiry is complete')
            return False

        # (rocky) if user moves instances away when the project in 'archiving'
        # or 'archived' we should continue to delete the archives.
        if not self.instances and \
           self.project.zone_expiry_status not in [expiry_states.ARCHIVING,
                                                   expiry_states.ARCHIVED]:
            if self.project.zone_expiry_status != expiry_states.ACTIVE or \
               self.project.zone_expiry_ticket_id != '0' or \
               self.project.zone_expiry_next_step != '':
                self.finish_expiry(
                    message='Out-of-zone instances expiry is complete')
            return False
        return True

    def process(self):

        zone_expiry_status = self.get_status()
        zone_expiry_next_step = self.get_next_step_date()

        if self.force_delete:
            LOG.info("%s: Force deleting out of zone instances=%s",
                     self.project.id, self.instances)
            self.delete_resources(force=True)
            return True

        if not self.should_process():
            return False

        LOG.debug("%s: Processing out of zone instances project=%s "
                  "status=%s next_step=%s number_of_instances=%s",
                  self.project.id, self.project.name, zone_expiry_status,
                  zone_expiry_next_step, len(self.instances))

        if zone_expiry_status == expiry_states.ACTIVE:
            if self.ready_for_warning():
                self.send_warning()
                return True
            return False
        elif zone_expiry_status == expiry_states.WARNING:
            if self.at_next_step():
                self.stop_resource()
                return True
            return False
        elif zone_expiry_status == expiry_states.STOPPED:
            if self.at_next_step():
                self.archive_project()
                return True
            return False
        elif zone_expiry_status == expiry_states.ARCHIVING:
            if self.at_next_step():
                LOG.debug("%s: Archiving longer than next step, move on",
                          self.project.id)
                self.set_project_archived()
            else:
                self.check_archiving_status()
            return True
        elif zone_expiry_status == expiry_states.ARCHIVED:
            if self.at_next_step():
                self.archiver.delete_archives()
                self.delete_resources(force=True)
                self.finish_expiry(
                    message='Out-of-zone instances expiry is complete')
                return True
            return False


class ImageExpirer(Expirer):

    STATUS_KEY = 'nectar_expiry_status'
    NEXT_STEP_KEY = 'nectar_expiry_next_step'
    TICKET_ID_KEY = 'nectar_expiry_ticket_id'
    UPDATED_AT_KEY = 'nectar_expiry_updated_at'
    EVENT_PREFIX = 'expiry.image'

    def __init__(self, image, ks_session=None, dry_run=False,
                 force_delete=False):

        notifier = expiry_notifier.ExpiryNotifier(
            resource_type='image', resource=image, template_dir='images',
            group_id=CONF.freshdesk.image_group,
            subject="Nectar Image Expiry - %s" % image.name,
            ks_session=ks_session, dry_run=dry_run,
            ticket_id_key=self.TICKET_ID_KEY)

        self.archiver = archiver.ImageArchiver(image, ks_session=ks_session,
                                               dry_run=dry_run)

        self.image = image
        self.force_delete = force_delete
        self.image_set_defaults()
        self.g_client = auth.get_glance_client(ks_session)
        self.n_client = auth.get_nova_client(ks_session)
        super(ImageExpirer, self).__init__('image', image, notifier,
                                           ks_session, dry_run)

    def get_project(self):
        if not hasattr(self.image, 'owner'):
            raise exceptions.InvalidImage
        return self.k_client.projects.get(self.image.owner)

    def image_set_defaults(self):
        self.image.nectar_expiry_status = getattr(
            self.image, self.STATUS_KEY, '')
        self.image.nectar_expiry_next_step = getattr(
            self.image, self.NEXT_STEP_KEY, '')
        self.image.nectar_expiry_ticket_id = getattr(
            self.image, self.TICKET_ID_KEY, '0')

    def _get_notification_context(self):
        managers = self._get_project_managers()
        members = self._get_project_members()
        context = {'managers': [i.to_dict() for i in managers],
                   'members': [i.to_dict() for i in members],
                   'project': self.project.to_dict(),
                   'image': dict(self.image.items()),
                   'expiry_date': self.make_next_step_date(self.now)}
        return context

    def _is_ignored_image(self):
        official_projects = CONF.image_expiry.official_project_ids.split(',')
        if self.image.owner in official_projects:
            LOG.debug("Image %s: Ignoring official image", self.image.id)
            return True
        return False

    def _has_no_running_instance(self):
        search_opts = {'image': self.image.id,
                       'all_tenants': True}
        try:
            instances = self.n_client.servers.list(search_opts=search_opts)
            if len(instances):
                LOG.info("Image %s: Has running instances", self.image.id)
                return False
            return True
        except Exception as e:
            LOG.error(
                "Image %s: Can't get related instance", self.image.id)
            LOG.error(e)
            return False

    def _has_no_recent_boot(self, days=THREE_YEARS_IN_DAYS):
        changes_since = self.now - relativedelta(days=days)
        # changes_since needs ISO 8061 formatted time
        changes_since = changes_since.isoformat()
        search_opts = {'image': self.image.id,
                       'all_tenants': True,
                       'deleted': True,
                       'limit': 1,  # aviod too many returns
                       'changes_since': changes_since}
        try:
            instances = self.n_client.servers.list(search_opts=search_opts)
            if len(instances):
                LOG.info("Image %s: Has been booted recently", self.image.id)
                return False
            return True
        except Exception as e:
            LOG.error("Image %s: Can't get related instance", self.image.id)
            LOG.error(e)
            return False

    def get_warning_date(self):
        created_at = datetime.datetime.strptime(
            self.image.created_at, DATETIME_FORMAT)
        return created_at + datetime.timedelta(days=THREE_YEARS_IN_DAYS)

    def should_process(self):

        if self.ready_for_warning() \
            and self.project.enabled \
            and not self._is_ignored_image() \
            and self._has_no_running_instance() \
            and self._has_no_recent_boot():

            LOG.info("Image %s: Expiry process is in progress!", self.image.id)
            return True

        LOG.debug("Image %s: Expiry process is not triggered", self.image.id)
        return False

    def process(self):
        if self.force_delete:
            LOG.info("Image %s: Force deleting image", self.image.id)
            self.delete_resources(force=True)
            return True
        expiry_status = self.get_status()
        expiry_next_step = self.get_next_step_date()

        LOG.debug("Image %s: Processing image=%s status=%s next_step=%s",
                  self.image.id, self.image.name, expiry_status,
                  expiry_next_step)

        if not self.should_process():
            if self.image.nectar_expiry_status != expiry_states.ACTIVE or \
               self.image.nectar_expiry_ticket_id != '0' or \
               self.image.nectar_expiry_next_step != '':
                if self.image.os_hidden:
                    self.archiver.start_resources()
                self.finish_expiry(
                    'Reset status, expiry work flow is complete')
            return False

        if expiry_status == expiry_states.ACTIVE:
            self.send_warning()
            return True
        elif expiry_status == expiry_states.WARNING:
            if self.at_next_step():
                self.stop_resource()
                return True
            return False
        elif expiry_status == expiry_states.STOPPED:
            if self.image.os_hidden is not True:
                self.archiver.stop_resources()
                return True
            elif self.at_next_step():
                self.finish_expiry()
                self.delete_resources(force=True)
                return True
            return False
        else:
            LOG.warn("Image %s: Unspecified status %s",
                     self.image.id, expiry_status)
            return False
