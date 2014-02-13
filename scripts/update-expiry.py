#!/usr/bin/env python

import os
import re
import sys
import argparse
import auth
import csv
import smtplib
from ConfigParser import SafeConfigParser
from datetime import datetime
from dateutil.relativedelta import relativedelta

from jinja2 import Environment, FileSystemLoader
from keystoneclient.exceptions import NotFound

DRY_RUN = True

PT_RE = re.compile(r'^pt-\d+$')


def parse_config(section, filename='update-expiry.conf'):
    """Read configuration settings from config file"""

    options = {}
    config_file = os.path.join(os.getcwd(), filename)

    try:
        with open(config_file):
            parser = SafeConfigParser()
            parser.read(config_file)
    except IOError as err:
        sys.stderr.write('%s\n' % str(err))
        raise SystemExit

    for name, value in parser.items(section):
        options[name] = value

    return options


def collect_args():
    """Handle command-line options"""

    parser = argparse.ArgumentParser(description='Updates tenant expiry date')
    parser.add_argument('-y', '--no-dry-run', action='store_true',
                        default=False,
                        help='Perform the actual actions, default is to \
                        only show what would happen')
    parser.add_argument('-f', '--filename',
                        type=argparse.FileType('r'),
                        help='File path with a list of users')
    parser.add_argument('-c', '--config',
                        help='Path of configuration file')
    parser.add_argument('-a', '--set-admin', action='store_true',
                        help='Mark a list of tenants as admins')

    return parser


def update(kc, nc, users):
    """Update tenant start and expiry dates in Keystone DB"""

    dateformat = "%Y-%m-%d"
    limit = 4383  # 6 months in hours
    end = datetime.now() + relativedelta(days=1)  # tomorrow
    new_expiry = datetime.today() + relativedelta(months=1)
    new_expiry = new_expiry.strftime(dateformat)  # string
    tenants = suspended = errors = 0
    start = datetime(2011, 1, 1)

    for user in users:
        try:
            if isinstance(user, (str, unicode)):
                user = kc.users.get(user)
        except NotFound as err:
            sys.stderr.write('%s\n' % str(err))
            errors += 1
            continue

        # skip users that have no tenant
        if not getattr(user, "tenantId", None):
            continue

        tenant = kc.tenants.get(user.tenantId)
        if not PT_RE.match(tenant.name):
            continue

        tenants += 1

        usage = nc.usage.get(user.tenantId, start, end)
        cpu_hours = getattr(usage, 'total_vcpus_usage', None)

        if not hasattr(tenant, 'status'):
            print tenant.id, "updating tenant's status"
            if not DRY_RUN:
                kc.tenants.update(user.tenantId, status=None)
        elif tenant.status == 'suspended':
            print tenant.id, 'tenant is suspended'
            suspended += 1
        elif tenant.status == 'admin':
            print tenant.id, 'tenant is admin. Will never expire'
        elif hasattr(tenant, 'expires') and tenant.expires is not None:
            # Convert expires string to datetime object for comparison
            expires = datetime.strptime(tenant.expires, dateformat)
            if expires <= datetime.today():
                print tenant.id, 'tenant expired! Suspending instances...'
                if not DRY_RUN:
                    # Suspend any instances and set status to suspended
                    get_instances(nc, tenant.id)
                    kc.tenants.update(user.tenantId, status='suspended')
                    set_nova_quota(nc, tenant.id, ram=0, instances=0, cores=0)
            else:
                print tenant.id, 'will expire on', tenant.expires
        elif cpu_hours < limit*0.8:
            print tenant.id, 'tenant is under 80%'
        elif cpu_hours <= limit:
            print tenant.id, 'tenant is over 80% - setting status to first'
            if tenant.status != 'first':
                if not DRY_RUN:
                    # Inform the tenant of allocation process
                    send_email(user.email, tenant.name)
                    kc.tenants.update(user.tenantId, status='first')
        elif cpu_hours <= limit*1.2:
            print tenant.id, 'tenant is over 100% - setting status to second'
            if tenant.status != 'second':
                if not DRY_RUN:
                    # Inform the tenant, set quota to 0 and update the status
                    send_email(user.email, tenant.name)
                    set_nova_quota(nc, tenant.id, ram=0, instances=0, cores=0)
                    kc.tenants.update(user.tenantId, status='second')
        elif cpu_hours > limit*1.2:
            print tenant.id, 'tenant is over 120% - setting status to third'
            if tenant.status != 'final':
                if not DRY_RUN:
                    # Inform the tenant and set expires date and status
                    send_email(user.email, tenant.name)
                    kc.tenants.update(user.tenantId, expires=new_expiry,
                                      status='final')

    print '\nProcessed', tenants, 'tenants.', \
        suspended, 'suspended.', errors, '404s'


def get_instances(nc, tenant_id):

    search_opts = {'tenant_id': tenant_id, 'all_tenants': 1}
    instances = nc.servers.list(search_opts=search_opts)
    print "%d instance%s found" % (len(instances), "s"[len(instances) == 1:])
    if instances:
        for instance in instances:
            suspend_instance(instance)
            lock_instance(instance)


def suspend_instance(instance):

    print instance.id, "- suspending instance..."
    if instance.status == 'SUSPENDED':
        print instance.id, "- instance is already suspended"
    elif instance.status == 'SHUTOFF':
        print instance.id, "- instance is off"
    else:
        instance.suspend()


def lock_instance(instance):

    print instance.id, "- locking instance..."
    instance.lock()


def set_nova_quota(nc, tenant_id, cores, instances, ram):

    nc.quotas.update(tenant_id=tenant_id,
                     ram=ram,
                     instances=instances,
                     cores=cores)


def render_template(tenantname):

    env = Environment(loader=FileSystemLoader('templates'))
    template = env.get_template('first-notification.tmpl')
    template = template.render({'project_name': tenantname})
    return template


def send_email(recepient, tenantname):

    from email.mime.text import MIMEText
    msg = MIMEText(render_template(tenantname))

    msg['From'] = 'NeCTAR Research Cloud <bounces@rc.nectar.org.au>'
    msg['To'] = recepient
    msg['Reply-to'] = 'support@rc.nectar.org.au'
    msg['Subject'] = 'NeCTAR project upcoming expiry - %s' % tenantname

    s = smtplib.SMTP('smtp.unimelb.edu.au')

    print 'Sending an email to', recepient
    if not DRY_RUN:
        try:
            s.sendmail(msg['From'], [recepient], msg.as_string())
        except smtplib.SMTPRecipientsRefused as err:
            sys.stderr.write('%s\n' % str(err))
        finally:
            s.quit()


def read_csv(filename=False):
    """ Get a list of UUIDs from either file.
        Can be tenant or user IDs
    """
    reader = csv.reader(filename)
    return list(reader)


def set_admin(kc, tenant_ids):
    """Set status to admin for specified list of tenants"""

    for tenant_id in tenant_ids:
        tenant_id = tenant_id[0]
        tenant = kc.tenants.get(tenant_id)

        if hasattr(tenant, 'status') and tenant.status == 'admin':
            print tenant.id, "- tenant is already admin"
        else:
            if DRY_RUN:
                print tenant.id, "- would set status admin (dry run)"
            else:
                print tenant.id, "- setting status to admin"
                # kc.tenants.update(tenant.id, status='admin', expires='')


if __name__ == '__main__':

    parser = collect_args()
    args = parser.parse_args()

    if args.no_dry_run:
        DRY_RUN = False
    else:
        print >> sys.stderr, "DRY RUN"

    kc = auth.get_keystone_client()
    nc = auth.get_nova_client()

    if args.set_admin:
        if not args.filename:
            parser.error("Can't specify set admin without list of users.")

        data = read_csv(args.filename)
        set_admin(kc, data)
    else:
        if args.filename:
            data = read_csv(args.filename)
        else:
            data = kc.users.list()

        update(kc, nc, data)
