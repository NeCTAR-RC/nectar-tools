#!/usr/bin/env python

import argparse
import csv
from datetime import datetime
from dateutil.relativedelta import relativedelta
from email.mime.text import MIMEText
import logging
import os
import re
import smtplib

from enum import Enum
from jinja2 import Environment, FileSystemLoader
from jinja2.exceptions import TemplateNotFound
import prettytable

from novaclient.v2.contrib import instance_action

from nectar_tools import auth
from nectar_tools import config
from nectar_tools import log

DRY_RUN = True
ARCHIVE_ATTEMPTS = 10
USAGE_LIMIT_HOURS = 4383  # 6 months in hours
EXPIRY_DATE_FORMAT = "%Y-%m-%d"
ACTION_DATE_FORMAT = '%Y-%m-%dT%H:%M:%S.%f'
TENANT_STATES = ['admin', 'quota warning', 'pending suspension', 'suspended',
                 'archiving', 'archived', 'archive error', 'OK']


class CPULimit(Enum):
    UNDER_LIMIT = 0
    NEAR_LIMIT = 1
    AT_LIMIT = 2
    OVER_LIMIT = 3


PT_RE = re.compile(r'^pt-\d+$')


LOG = logging.getLogger(__name__)
CONFIG = config.CONFIG


def main():
    parser = CONFIG.get_parser()
    add_args(parser)
    args = CONFIG.parse()

    log.setup()

    if args.no_dry_run:
        global DRY_RUN
        DRY_RUN = False
    else:
        LOG.info('DRY RUN')

    kc = auth.get_keystone_client()
    nc = auth.get_nova_client()

    tenants = []
    if args.tenant_id:
        tenant = kc.tenants.get(args.tenant_id)
        tenants.append(tenant)
    if not tenants:
        tenants = kc.tenants.list()
        if args.filename:
            wanted_tenants = read_csv(args.filename)[0]
            tenants = [t for t in tenants if t.id in wanted_tenants]
    tenants.sort(key=lambda t: t.name.split('-')[-1].zfill(5))

    if args.set_admin:
        if not args.filename and not args.tenant_id:
            parser.error("Can't specify set admin without list of tenants.")
        set_admin(kc, tenants)
    elif args.metadata:
        if not args.filename and not args.tenant_id:
            parser.error("Can't set metadata without list of specific "
                         "tenants.")
        kwargs = [tuple(meta.split('=', 1))
                  for meta in args.metadata.split(',')]
        kwargs = dict(kwargs)
        for tenant in tenants:
            kc.tenants.update(tenant.id, **kwargs)
    else:
        users = kc.users.list()
        link_tenants_to_users(tenants, users)
        if args.status:
            print_status(tenants)
        else:
            process_tenants(kc, nc, tenants, users, args.zone,
                            limit=args.limit, offset=args.offset,
                            action_state=args.action_state)


def print_status(tenants):
    pt = prettytable.PrettyTable(['Name', 'Tenant ID', 'Owner',
                                  'Status', 'Expiry date'])
    for tenant in tenants:
        tenant_set_defaults(tenant)
        if is_personal_tenant(tenant):
            pt.add_row([tenant.name, tenant.id,
                        getattr(tenant.owner, 'email', ''),
                        tenant.status, tenant.expires])
    print(pt)


def add_args(parser):
    """Handle command-line options"""
    parser.description = 'Updates tenant expiry date'
    parser.add_argument('-y', '--no-dry-run', action='store_true',
                        default=False,
                        help='Perform the actual actions, default is to \
                        only show what would happen')
    parser.add_argument('-f', '--filename',
                        type=argparse.FileType('r'),
                        help='File path with a list of tenants')
    parser.add_argument('-l', '--limit',
                        type=int,
                        default=0,
                        help='Only process this many eligible tenants.')
    parser.add_argument('-o', '--offset',
                        type=int,
                        default=None,
                        help='Skip this many tenants before processing.')
    parser.add_argument('-t', '--tenant-id',
                        help='Tenant ID to process')
    parser.add_argument('-a', '--set-admin', action='store_true',
                        help='Mark a list of tenants as admins')
    parser.add_argument('--action-state', action='store',
                        choices=TENANT_STATES,
                        default=None,
                        help='Only process tenants in this state')
    parser.add_argument('-m', '--metadata', action='store',
                        help='Set metadata on tenants as a comma-separated '
                             'list of key=value pairs.')
    parser.add_argument('-s', '--status', action='store_true',
                        help='Report current status of each tenant.')
    parser.add_argument('-z', '--zone', action='store',
                        help='Limit actions to tenants with instances only '
                             'in this zone.')


def link_tenants_to_users(tenants, users):
    tenants_dict = {tenant.id: tenant for tenant in tenants}
    for user in users:
        tenant_id = getattr(user, 'tenantId', None)
        if tenant_id:
            if tenant_id in tenants_dict:
                tenants_dict[tenant_id].owner = user


def tenant_instances_are_all_in_zone(nc, tenant, zone_prefix):
    def is_in_target_az(instance):
        az = instance.to_dict().get('OS-EXT-AZ:availability_zone') or ''
        return az.startswith(zone_prefix)

    try:
        instances = get_instances(nc, tenant.id)
    except Exception:
        LOG.exception('Nova list instances failed')
        return False
    return instances and all(map(is_in_target_az, instances))


def process_tenants(kc, nc, tenants, users, zone, limit=0, offset=None,
                    action_state=None):
    """Update tenant start and expiry dates in Keystone DB"""
    processed = 0
    offset_count = 0
    for tenant in tenants:
        tenant_set_defaults(tenant)
        offset_count += 1
        if offset is None or offset_count > offset:

            if should_process_tenant(tenant):
                if action_state:
                    tenant_status = getattr(tenant, 'status', None)
                    if (not tenant_status and action_state == 'OK') or \
                       action_state == tenant_status:
                            if process_tenant(kc, nc, tenant):
                                processed += 1

                else:
                    if zone and not tenant_instances_are_all_in_zone(nc,
                                                                     tenant,
                                                                     zone):
                        continue
                    did_something = process_tenant(kc, nc, tenant)
                    if did_something:
                        processed += 1

        if limit > 0 and processed >= limit:
            break


def tenant_set_defaults(tenant):
    tenant.status = getattr(tenant, 'status', '')
    tenant.expires = getattr(tenant, 'expires', '')
    tenant.owner = getattr(tenant, 'owner', None)


def should_process_tenant(tenant):
    personal = is_personal_tenant(tenant)
    has_owner = tenant_has_owner(tenant)
    if personal and not has_owner:
        LOG.debug("Tenant %s (%s) has no owner", tenant.id, tenant.name)
    return personal and has_owner and not is_ignored_tenant(tenant)


def is_personal_tenant(tenant):
    return PT_RE.match(tenant.name)


def is_ignored_tenant(tenant):
    status = getattr(tenant, 'status', None)
    if status is None:
        return False
    elif status == 'admin':
        LOG.debug('Tenant %s is admin. Will never expire', tenant.id)
        return True
    elif status.startswith('rt-'):
        url = ('https://support.rc.nectar.org.au'
               '/rt/Ticket/Display.html?id=%s') % status.rsplit('-', 1)[1]
        LOG.debug('Tenant %s is ignored. See %s', tenant.id, url)
        return True
    return False


def tenant_has_owner(tenant):
    return tenant.owner is not None


def print_instances(instances):
    LOG.info("\t%d instance(s) found", len(instances))
    for instance in instances:
        LOG.debug("\tinstance %s is %s (task_state=%s vm_state=%s)" %
                  (instance.id, instance.status,
                   getattr(instance, 'OS-EXT-STS:task_state'),
                   getattr(instance, 'OS-EXT-STS:vm_state')))


def list_instances(nc, tenant):
    instances = get_instances(nc, tenant.id)
    print_instances(instances)


def process_tenant(kc, nc, tenant):
    status = getattr(tenant, 'status', None)
    LOG.debug("Processing tenant %s (%s) status: %s" %
              (tenant.name, tenant.id, tenant.status or 'OK'))

    if status in ['archived', 'archive error']:
        if len(get_instances(nc, tenant.id)) > 0:
            if tenant_at_next_step_date(tenant):
                clean_up_tenant(kc, nc, tenant)
                return True
        return False
    elif status == 'suspended':
        if tenant_at_next_step_date(tenant):
            archive_tenant(kc, nc, tenant)
            return True
    elif status == 'archiving':
        LOG.debug('Checking archive status')
        is_archive_successful(kc, nc, tenant)
        return True
    else:
        try:
            limit = check_cpu_usage(kc, nc, tenant)
            return notify(kc, nc, tenant, limit)
        except Exception as e:
            LOG.error("Failed to get usage for tenant %s" % tenant.id)
            LOG.error("%s" % e)


def get_next_step_date(tenant):
    # We use 'expires' for legacy reasons
    if not tenant.expires:
        LOG.warning('No "next step" date set')
        return

    try:
        expires = datetime.strptime(tenant.expires, EXPIRY_DATE_FORMAT)
        return expires
    except ValueError:
        LOG.error('Invalid expires date: %s for tenant %s' %
                  (tenant.expires, tenant.id))
        return None


def tenant_at_next_step_date(tenant):
    expires = get_next_step_date(tenant)
    if expires and expires <= datetime.today():
        LOG.debug('Ready for next step (%s)' % expires)
        return True
    else:
        LOG.debug('Not ready for next step (%s)' % expires)
    return False


def check_cpu_usage(kc, nc, tenant):
    limit = USAGE_LIMIT_HOURS
    start = datetime(2011, 1, 1)
    end = datetime.now() + relativedelta(days=1)  # tomorrow
    usage = nc.usage.get(tenant.id, start, end)
    cpu_hours = getattr(usage, 'total_vcpus_usage', None)

    LOG.debug("Total VCPU hours: %s", cpu_hours)

    if cpu_hours < limit * 0.8:
        return CPULimit.UNDER_LIMIT
    elif cpu_hours < limit:
        return CPULimit.NEAR_LIMIT
    elif cpu_hours < limit * 1.2:
        return CPULimit.AT_LIMIT
    elif cpu_hours >= limit * 1.2:
        return CPULimit.OVER_LIMIT


def notify(kc, nc, tenant, event):
    limits = {
        CPULimit.UNDER_LIMIT: lambda *x: False,
        CPULimit.NEAR_LIMIT: notify_near_limit,
        CPULimit.AT_LIMIT: notify_at_limit,
        CPULimit.OVER_LIMIT: notify_over_limit
    }
    if event != CPULimit.UNDER_LIMIT:
        LOG.debug('\t%s', event)
    return limits[event](kc, nc, tenant)


def notify_near_limit(kc, nc, tenant):
    if tenant.status == 'quota warning':
        return False

    LOG.info("\t%s: Usage is over 80 - setting status "
             "to quota warning" % tenant.name)
    send_email(tenant, 'first')
    set_status(kc, tenant, 'quota warning')
    return True


def notify_at_limit(kc, nc, tenant):
    if tenant.status == 'pending suspension':
        LOG.debug("\tUsage OK for now, ignoring")
        return False

    LOG.info("\tusage is over 100%%, setting status to "
             "pending suspension for %s" % tenant.name)
    set_nova_quota(nc, tenant.id, ram=0, instances=0, cores=0)
    new_expiry = datetime.today() + relativedelta(months=1)
    new_expiry = new_expiry.strftime(EXPIRY_DATE_FORMAT)
    set_status(kc, tenant, 'pending suspension', new_expiry)
    send_email(tenant, 'second')
    return True


def notify_over_limit(kc, nc, tenant):
    if tenant.status != 'pending suspension':
        return notify_at_limit(kc, nc, tenant)

    if not tenant_at_next_step_date(tenant):
        return False

    LOG.info("\tusage is over 120%%, suspending tenant %s" % tenant.name)
    suspend_tenant(kc, nc, tenant)
    return True


def archive_tenant(kc, nc, tenant):
    if DRY_RUN:
        LOG.info('\twould archive tenant')
    else:
        if getattr(tenant, 'status', None) != 'archiving':
            LOG.info('\tarchiving tenant')
            new_expiry = datetime.today() + relativedelta(months=1)
            new_expiry = new_expiry.strftime(EXPIRY_DATE_FORMAT)
            set_status(kc, tenant, 'archiving', new_expiry)

    instances = get_instances(nc, tenant.id)
    if len(instances) == 0:
        LOG.debug('\tno instances found')
        archive_date = datetime.today().strftime(EXPIRY_DATE_FORMAT)
        set_status(kc, tenant, 'archived', archive_date)
    else:
        print_instances(instances)
        for instance in instances:
            attempts = int(instance.metadata.get('archive_attempts', 1))
            if attempts >= ARCHIVE_ATTEMPTS:
                LOG.error('\tlimit reached for archive '
                          'attempts of instance %s' % instance.id)
                new_expiry = datetime.today().strftime(EXPIRY_DATE_FORMAT)
                set_status(kc, tenant, 'archive error', new_expiry)
                break
            else:
                image = get_image_by_instance_id(kc, tenant, instance.id)
                if not image:
                    archive_instance(nc, instance)


def tenant_has_error(kc, nc, tenant):
    error = False
    instances = get_instances(nc, tenant.id)
    for instance in instances:
        vm_state = getattr(instance, 'OS-EXT-STS:vm_state')
        if vm_state == 'error' or instance.status == 'ERROR':
            error = True
    return error


def get_glance_client(kc):
    glance_endpoint = kc.service_catalog.url_for(service_type='image',
                                                 endpoint_type='publicURL')
    # TODO: Fix production hack
    glance_endpoint = glance_endpoint.replace('/v1', '')
    gc = auth.get_glance_client(glance_endpoint, kc.auth_token)
    return gc


def get_image_by_instance_id(kc, tenant, instance_id):
    image_name = '%s_archive' % instance_id
    return get_image_by_name(kc, tenant, image_name)


def get_image_by_name(kc, tenant, image_name):
    """ Get an image by a given name """
    gc = get_glance_client(kc)
    images = [i for i in gc.images.list(
              filters={'property-owner_id': tenant.id})]
    image_names = [i.name for i in images]
    if image_name in image_names:
        return [i for i in images if i.name == image_name][0]


def is_image_in_progress(image):
    if image.status in ['saving', 'queued']:
        return True
    return False


def is_image_successful(image):
    if image.status == 'active':
        return True
    return False


def is_archive_successful(kc, nc, tenant):
    LOG.debug('\tchecking if archive was successful')
    instances = get_instances(nc, tenant.id)
    if len(instances) == 0:
        # No instances found, go straight to archived
        LOG.debug('\tno instances found')
        archive_date = datetime.today().strftime(EXPIRY_DATE_FORMAT)
        set_status(kc, tenant, 'archived', archive_date)
        return True
    else:
        LOG.debug('\tfound %d instances' % len(instances))

        tenant_archive_success = True
        tenant_archive_in_progress = False

        for instance in instances:
            LOG.debug('\tchecking instance: %s (%s)' %
                      (instance.id, instance.status))

            image = get_image_by_instance_id(kc, tenant, instance.id)
            if image:
                if is_image_successful(image):
                    LOG.info('\tinstance %s archived successfully' %
                             instance.id)
                    if not image.properties.get('nectar_archive'):
                        LOG.debug('\tsetting nectar_archive property on image:'
                                  ' %s' % image.id)
                        image.update(properties={'nectar_archive': True})
                elif is_image_in_progress(image):
                    LOG.info("\tarchiving in progress (%s) for %s (image: %s)"
                             % (image.status, instance.id, image.id))
                    tenant_archive_success = False
                    tenant_archive_in_progress = True
                else:
                    LOG.warning('\timage found with status: %s' % image.status)
                    tenant_archive_success = False
            else:
                LOG.debug('\tarchive for instance %s not found' % instance.id)
                tenant_archive_success = False

        if tenant_archive_success:
            LOG.debug('\ttenant %s (%s) archive successful' %
                      (tenant.id, tenant.name))
            new_expiry = datetime.today() + relativedelta(months=1)
            new_expiry = new_expiry.strftime(EXPIRY_DATE_FORMAT)
            set_status(kc, tenant, 'archived', new_expiry)
            return True
        else:
            if tenant_at_next_step_date(tenant):
                # After 1 month of attempts, mark as error
                new_expiry = datetime.today() + relativedelta(months=1)
                set_status(kc, tenant, 'archive error', new_expiry)
            else:
                if tenant_archive_in_progress:
                    LOG.info('\ttenant %s (%s) archive in progress' %
                             (tenant.id, tenant.name))
                else:
                    LOG.debug('\tretrying archive for tenant %s (%s) ' %
                              (tenant.id, tenant.name))
                    archive_tenant(kc, nc, tenant)
        return False


def can_delete_shutoff(nc, instance):
    """ Check instance actions to see if an instance was shutdown by an admin
    over three months ago """
    try:
        actions = instance_action.InstanceActionManager(nc).list(instance.id)
    except Exception as e:
        LOG.error('Failed to get instance actions: %s' % e)
        return False

    if not actions:
        return False
    last_action = actions[0]
    three_months_ago = datetime.now() - relativedelta(days=90)
    action_date = datetime.strptime(last_action.start_time, ACTION_DATE_FORMAT)
    allowed_actions = ['stop', 'suspend', 'delete']
    admin_projects = ['1', '2', None]
    if last_action.action in allowed_actions and \
       last_action.project_id in admin_projects and \
       action_date < three_months_ago:
            LOG.debug("\tinstance %s has been shutdown >3 months ago"
                      % instance.id)
            return True
    if last_action.action not in allowed_actions:
        LOG.info("\tinstance %s: cannot delete, shutdown last action was %s" %
                 (instance.id, last_action.action))
    if last_action.project_id not in admin_projects:
        LOG.info("\tinstance %s: cannot delete, shutdown last action was by "
                 "project %s" % (instance.id, last_action.project_id))
    if action_date > three_months_ago:
        LOG.debug("\tinstance %s cannot delete, shutdown last action date "
                  "was %s" % (instance.id, action_date))
    return False


def archive_instance(nc, instance):

    # Increment the archive attempt counter
    attempts = int(instance.metadata.get('archive_attempts', 0))
    set_attempts = attempts + 1
    if not DRY_RUN:
        LOG.debug("\tsetting archive attempts counter to %d" % set_attempts)
        metadata = {'archive_attempts': str(set_attempts)}
        nc.servers.set_meta(instance.id, metadata)
    else:
        LOG.debug("\twould set archive attempts counter to %d" % set_attempts)

    task_state = getattr(instance, 'OS-EXT-STS:task_state')
    vm_state = getattr(instance, 'OS-EXT-STS:vm_state')

    if instance.status == 'ERROR':
        LOG.error("\tcan't snapshot due to instance status %s"
                  % instance.status)
        return

    if instance.status == 'DELETED' or task_state == 'deleting':
        clean_up_instance(instance)
        return

    if instance.status == 'ACTIVE':
        # Instance should be stopped when moving into suspended status
        # but we can stop for now and start archiving next run
        stop_instance(instance)
        return

    if task_state in ['suspending', 'image_snapshot_pending', 'deleting',
                      'image_snapshot', 'image_pending_upload']:
        LOG.error("\tcan't snapshot due to task_state %s" % task_state)
        return

    elif vm_state in ['stopped', 'suspended']:
        # We need to be in stopped or suspended state to create an image
        archive_name = "%s_archive" % instance.id

        if DRY_RUN:
            LOG.info("\twould create archive %s (attempt %d/%d)" %
                     (archive_name, set_attempts, ARCHIVE_ATTEMPTS))
        else:
            try:
                LOG.info("\tcreating archive %s (attempt %d/%d)" %
                         (archive_name, set_attempts, ARCHIVE_ATTEMPTS))
                image_id = instance.create_image(archive_name)
                LOG.info("\tarchive image id: %s" % image_id)
            except Exception as e:
                LOG.error("\tError creating archive: %s" % e)
    else:
        # Fail in an unknown state
        LOG.warning("\tinstance %s is %s (vm_state: %s)" %
                    (instance.id, instance.status, vm_state))


def clean_up_tenant(kc, nc, tenant):
    instances = get_instances(nc, tenant.id)
    LOG.info("\t%d instance(s) found", len(instances))
    for instance in instances:
        if can_delete_shutoff(nc, instance):
            clean_up_instance(instance)


def clean_up_instance(instance):
    if DRY_RUN:
        LOG.info("\twould delete instance: %s" % instance.id)
    else:
        LOG.info("\tdeleting instance: %s" % instance.id)
        instance.delete()


def suspend_tenant(kc, nc, tenant):
    set_nova_quota(nc, tenant.id, ram=0, instances=0, cores=0)
    instances = get_instances(nc, tenant.id)
    LOG.info("\t%d instance(s) found", len(instances))
    for instance in instances:
        stop_instance(instance)
        lock_instance(instance)
    new_expiry = datetime.today() + relativedelta(months=1)
    new_expiry = new_expiry.strftime(EXPIRY_DATE_FORMAT)
    set_status(kc, tenant, 'suspended', new_expiry)
    send_email(tenant, 'final')


def get_instances(nc, tenant_id):
    search_opts = {'tenant_id': tenant_id, 'all_tenants': 1}
    instances = nc.servers.list(search_opts=search_opts)
    return instances


def suspend_instance(instance):
    task_state = getattr(instance, 'OS-EXT-STS:task_state')
    bad_task_states = ['migrating']
    if task_state in bad_task_states:
        msg = "\tinstance %s is task_state %s" % (instance.id,
                                                  task_state)
        LOG.info("\t%s" % msg)
        raise ValueError(msg)
    else:
        if DRY_RUN:
            LOG.info("\tinstance %s would be suspended" % instance.id)
        else:
            LOG.info("\tsuspending instance %s" % instance.id)
            instance.suspend()


def stop_instance(instance):
    task_state = getattr(instance, 'OS-EXT-STS:task_state')
    vm_state = getattr(instance, 'OS-EXT-STS:vm_state')

    if instance.status == 'SHUTOFF':
        LOG.info("\tinstance %s already SHUTOFF" % instance.id)
    elif instance.status == 'ACTIVE':
        if task_state:
            LOG.info("\tcannot stop instance %s in task_state=%s" %
                     (instance.id, task_state))
        else:
            if DRY_RUN:
                LOG.info("\tinstance %s would be stopped" % instance.id)
            else:
                LOG.info("\tstopping instance %s" % instance.id)
                instance.stop()
    else:
        task_state = getattr(instance, 'OS-EXT-STS:task_state')
        LOG.info("\tinstance %s is %s (task_state=%s vm_state=%s)" %
                 (instance.id, instance.status, task_state, vm_state))


def lock_instance(instance):
    if DRY_RUN:
        LOG.info("\tinstance %s would be locked" % instance.id)
    else:
        instance.lock()


def set_nova_quota(nc, tenant_id, cores, instances, ram):

    if DRY_RUN:
        LOG.info("\twould set Nova quota to 0 (dry run)")
    else:
        LOG.info("\tsetting Nova quota to 0")
        nc.quotas.update(tenant_id=tenant_id,
                         ram=ram,
                         instances=instances,
                         cores=cores,
                         force=True)


def set_status(kc, tenant, status, expires=''):
    if DRY_RUN:
        if status is None:
            LOG.info("\twould set empty status")
        else:
            LOG.info("\twould set status to %s (next step: %s)" %
                     (status, expires))
    else:
        if status is None:
            LOG.info("\tsetting empty status")
        else:
            LOG.info("\tsetting status to %s (next step: %s)" %
                     (status, expires))
        kc.tenants.update(tenant.id, status=status, expires=expires)

    tenant.status = status
    tenant.expires = expires


def render_template(tenant, status):

    tmpl = ''
    if status == 'first':
        tmpl = 'first-notification.tmpl'
    elif status == 'second':
        tmpl = 'second-notification.tmpl'
    elif status == 'final':
        tmpl = 'final-notification.tmpl'
    template_dir = os.path.realpath(os.path.join(os.path.dirname(__file__),
                                                 'templates'))
    env = Environment(loader=FileSystemLoader(template_dir))
    try:
        template = env.get_template(tmpl)
    except TemplateNotFound:
        LOG.error('Template "%s" not found. '
                  'Make sure status is correct.' % tmpl)
        return None

    template = template.render({'project': tenant, 'user': tenant.owner})
    return template


def send_email(tenant, status):
    recipient = tenant.owner.email
    if not tenant.owner.enabled:
        LOG.warning('User %s is disabled. Not sending email.', recipient)
        return

    text = render_template(tenant, status)
    if text is None:
        return

    subject, text = text.split('----', 1)

    if DRY_RUN:
        LOG.info('\twould send email to %s: %s', recipient, subject.rstrip())
    else:
        LOG.info('\tsending email to %s: %s', recipient, subject.rstrip())

    do_email_send(subject, text, recipient)


def do_email_send(subject, text, recipient):
    msg = MIMEText(text)
    msg['From'] = 'NeCTAR Research Cloud <bounces@rc.nectar.org.au>'
    msg['To'] = recipient
    msg['Reply-to'] = 'support@rc.nectar.org.au'
    msg['Subject'] = subject

    if not DRY_RUN:
        try:
            s = smtplib.SMTP('smtp.unimelb.edu.au')
            s.sendmail(msg['From'], [recipient], msg.as_string())
        except smtplib.SMTPRecipientsRefused as err:
            LOG.error('Error sending email: %s', str(err))
        finally:
            s.quit()


def read_csv(filename=False):
    """ Get a list of UUIDs from either file.
        Can be tenant or user IDs
    """
    reader = csv.reader(filename)
    return list(reader)


def set_admin(kc, tenants):
    """Set status to admin for specified list of tenants.
    """
    for tenant in tenants:
        if hasattr(tenant, 'status') and tenant.status == 'admin':
            LOG.error("tenant %s is already admin" % tenant.id)
        else:
            if DRY_RUN:
                LOG.info("would set status admin for %s (dry run)" % tenant.id)
            else:
                LOG.info("setting status admin for %s" % tenant.id)
                kc.tenants.update(tenant.id, status='admin', expires='')


if __name__ == '__main__':
    main()
