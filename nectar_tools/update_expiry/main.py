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


from nectar_tools import auth
from nectar_tools import config
from nectar_tools import log


DRY_RUN = True
USAGE_LIMIT_HOURS = 4383  # 6 months in hours
EXPIRY_DATE_FORMAT = "%Y-%m-%d"


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
            process_tenants(kc, nc, tenants, users, args.zone, args.limit)


def print_status(tenants):
    pt = prettytable.PrettyTable(['Name', 'Tenant ID', 'Owner',
                                  'Status', 'Expiry date'])
    for tenant in tenants:
        tenant_set_defaults(tenant)
        if is_personal_tenant(tenant):
            pt.add_row([tenant.name, tenant.id,
                        getattr(tenant.owner, 'email', ''),
                        tenant.status, tenant.expires])
    print str(pt)


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
    parser.add_argument('-t', '--tenant-id',
                        help='Tenant ID to process')
    parser.add_argument('-a', '--set-admin', action='store_true',
                        help='Mark a list of tenants as admins')
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


def process_tenants(kc, nc, tenants, users, zone, limit=0):
    """Update tenant start and expiry dates in Keystone DB"""
    processed = 0
    for tenant in tenants:
        tenant_set_defaults(tenant)
        if should_process_tenant(tenant):
            if zone and not tenant_instances_are_all_in_zone(nc, tenant, zone):
                continue

            try:
                did_something = process_tenant(kc, nc, tenant)
                if did_something:
                    processed += 1
            except Exception as e:
                LOG.error('Failed processing tenant %s: %s', tenant.id, str(e))
            if limit > 0 and processed == limit:
                break


def tenant_set_defaults(tenant):
    tenant.status = getattr(tenant, 'status', '')
    tenant.expires = getattr(tenant, 'expires', '')
    tenant.owner = getattr(tenant, 'owner', None)


def should_process_tenant(tenant):
    personal = is_personal_tenant(tenant)
    has_owner = tenant_has_owner(tenant)
    if personal and not has_owner:
        LOG.debug("Tenant %s (%s) has no owner.", tenant.id, tenant.name)
    return personal and has_owner and not is_ignored_tenant(tenant)


def is_personal_tenant(tenant):
    return PT_RE.match(tenant.name)


def is_ignored_tenant(tenant):
    status = getattr(tenant, 'status', None)
    if status is None:
        return False
    elif status == 'admin':
        LOG.debug('%s tenant is admin. Will never expire', tenant.id)
        return True
    elif status.startswith('rt-'):
        url = ('https://support.rc.nectar.org.au'
               '/rt/Ticket/Display.html?id=%s') % status.rsplit('-', 1)[1]
        LOG.debug('%s tenant ignored. See %s', tenant.id, url)
        return True
    return False


def tenant_has_owner(tenant):
    return tenant.owner is not None


def process_tenant(kc, nc, tenant):
    LOG.debug("Processing tenant %s (%s)", tenant.name, tenant.id)

    status = getattr(tenant, 'status', None)
    if status == 'suspended':
        if tenant_at_next_step_date(tenant):
            archive_tenant(kc, nc, tenant)
    elif status == 'archiving':
        LOG.info('\tchecking archive status')
        is_archive_successful(kc, nc, tenant)
    elif status == 'archived':
        LOG.debug('\ttenant has been archived')
        clean_up_instances(kc, nc, tenant)
    else:
        limit = check_cpu_usage(kc, nc, tenant)
        return notify(kc, nc, tenant, limit)


def tenant_at_next_step_date(tenant):
    if not tenant.expires:
        return False

    try:
        expires = datetime.strptime(tenant.expires, EXPIRY_DATE_FORMAT)
    except ValueError:
        LOG.debug('\tInvalid expires value')
        return False
    return expires <= datetime.today()


def check_cpu_usage(kc, nc, tenant):
    limit = USAGE_LIMIT_HOURS
    start = datetime(2011, 1, 1)
    end = datetime.now() + relativedelta(days=1)  # tomorrow
    usage = nc.usage.get(tenant.id, start, end)
    cpu_hours = getattr(usage, 'total_vcpus_usage', None)

    LOG.debug("\tTotal VCPU hours: %s", cpu_hours)

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

    LOG.info('Tenant %s (%s)', tenant.name, tenant.id)
    LOG.info('\tUsage is over 80% - setting status '
             'to "quota warning"')
    send_email(tenant, 'first')
    set_status(kc, tenant, 'quota warning')
    return True


def notify_at_limit(kc, nc, tenant):
    if tenant.status == 'pending suspension':
        return False

    LOG.info('Tenant %s (%s)', tenant.name, tenant.id)
    LOG.info('\tUsage is over 100% - setting status to '
             '"pending suspension"')
    set_nova_quota(nc, tenant.id, ram=0, instances=0, cores=0)
    new_expiry = datetime.today() + relativedelta(months=1)
    new_expiry = new_expiry.strftime(EXPIRY_DATE_FORMAT)
    set_status(kc, tenant, 'pending suspension', new_expiry)
    send_email(tenant, 'second')
    return True


def notify_over_limit(kc, nc, tenant):
    LOG.info('Tenant %s (%s)', tenant.name, tenant.id)

    if tenant.status != 'pending suspension':
        return notify_at_limit(kc, nc, tenant)

    if not tenant_at_next_step_date(tenant):
        return False

    LOG.info('\tUsage is over 120% - suspending tenant')
    suspend_tenant(kc, nc, tenant)
    return True


def archive_tenant(kc, nc, tenant):
    if DRY_RUN:
        LOG.info('\twould archive tenant')
    else:
        if getattr(tenant, 'status', None) != 'archiving':
            LOG.info('\tarchiving tenant')
            snapshot_date = datetime.today().strftime(EXPIRY_DATE_FORMAT)
            set_status(kc, tenant, 'archiving', snapshot_date)

    instances = get_instances(nc, tenant.id)
    if len(instances) == 0:
        LOG.info('\tno instances found')
        archive_date = datetime.today().strftime(EXPIRY_DATE_FORMAT)
        set_status(kc, tenant, 'archived', archive_date)
    else:
        LOG.info('\tfound %d instance(s)' % len(instances))
        for instance in instances:
            archive_instance(instance)


def is_archive_successful(kc, nc, tenant):
    LOG.info('\tchecking if archive was successful')

    glance_endpoint = kc.service_catalog.url_for(service_type='image',
                                                 endpoint_type='publicURL')

    # TODO: Fix production hack
    glance_endpoint = glance_endpoint.replace('/v1', '')
    gc = auth.get_glance_client(glance_endpoint, kc.auth_token)

    instances = get_instances(nc, tenant.id)
    if len(instances) == 0:
        LOG.info('\tno instances found')
        archive_date = datetime.today().strftime(EXPIRY_DATE_FORMAT)
        set_status(kc, tenant, 'archived', archive_date)
        return True
    else:
        LOG.info('\tfound %d instances' % len(instances))
        images = [i for i in gc.images.list(
            filters={'property-owner_id': tenant.id})]
        image_names = [i.name for i in images]

        archive_failed = True
        archive_in_progress = False

        for instance in instances:
            LOG.info('\tchecking instance: %s' % instance.id)
            archive_name = "%s_archive" % instance.id
            if archive_name in image_names:

                image = [i for i in images if i.name == archive_name][0]
                if image.status == 'active':
                    LOG.info('\timage archived successfully')
                    image.update(properties={'nectar_archive': True})
                    archive_failed = False
                elif image.status in ['saving', 'queued']:
                    LOG.info("\timage archiving in progress (%s) for "
                             "%s" % (image.status, image.id))
                    archive_in_progress = True
                else:
                    LOG.warning('\timage found with status: %s' % image.status)
            else:
                LOG.error('\tarchive %s not found' % archive_name)

        if not DRY_RUN:
            if archive_failed:
                if not archive_in_progress:
                    LOG.error('\tretrying archive')
                    archive_tenant(kc, nc, tenant)
            else:
                archive_date = datetime.today().strftime(EXPIRY_DATE_FORMAT)
                set_status(kc, tenant, 'archived', archive_date)
                return True
        return False


def archive_instance(instance):
    archive_name = "%s_archive" % instance.id
    if instance.status == 'SHUTOFF':
        LOG.error("\tinstance %s is OFF (state=%s)" %
                  (instance.id, instance.status))
    elif getattr(instance, 'OS-EXT-STS:power_state') != 4:
        LOG.error("\tinstance %s is OFF (power_state=%d)" %
                  (instance.id, getattr(instance, 'OS-EXT-STS:power_state')))
    else:
        if DRY_RUN:
            LOG.warning("\twould create archive %s" % archive_name)
        else:
            LOG.info("\tcreating archive %s" % archive_name)
            instance.create_image(archive_name)


def clean_up_instances(kc, nc, tenant):
    instances = get_instances(nc, tenant.id)

    for instance in instances:
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
        suspend_instance(instance)
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
    if instance.status == 'SUSPENDED':
        LOG.info("\t%s - instance is already suspended" % instance.id)
    elif instance.status == 'SHUTOFF':
        LOG.info("\t%s - instance is off" % instance.id)
    else:
        if DRY_RUN:
            LOG.info("\t%s - would suspend instance (dry run)" % instance.id)
        else:
            instance.suspend()


def lock_instance(instance):

    if DRY_RUN:
        LOG.info("\t%s - would lock instance (dry run)" % instance.id)
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
            LOG.info("\twould set empty status (dry run)")
        else:
            LOG.info("\twould set status to %s (dry run)", status)
    else:
        if status is None:
            LOG.info("\tsetting empty status")
        else:
            LOG.info("\tsetting status to %s", status)
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

    LOG.info('\tSending an email to %s', recipient)

    subject, text = text.split('----', 1)
    do_email_send(subject, text, recipient)


def do_email_send(subject, text, recipient):
    msg = MIMEText(text)
    msg['From'] = 'NeCTAR Research Cloud <bounces@rc.nectar.org.au>'
    msg['To'] = recipient
    msg['Reply-to'] = 'support@rc.nectar.org.au'
    msg['Subject'] = subject

    s = smtplib.SMTP('smtp.unimelb.edu.au')

    LOG.debug('%s', msg.as_string())
    if not DRY_RUN:
        try:
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
            print tenant.id, "- tenant is already admin"
        else:
            if DRY_RUN:
                print tenant.id, "- would set status admin (dry run)"
            else:
                print tenant.id, "- setting status to admin"
                kc.tenants.update(tenant.id, status='admin', expires='')


if __name__ == '__main__':
    main()
