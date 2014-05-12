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
from jinja2.exceptions import TemplateNotFound
from keystoneclient.exceptions import NotFound

DRY_RUN = True

PT_RE = re.compile(r'^pt-\d+$')


def main():

    parser = collect_args()
    args = parser.parse_args()

    if args.no_dry_run:
        DRY_RUN = False
    else:
        print_stderr('DRY RUN')

    kc = auth.get_keystone_client()
    nc = auth.get_nova_client()

    data = []
    if args.set_admin:
        if not args.filename:
            parser.error("Can't specify set admin without list of users.")

        data = read_csv(args.filename)
        set_admin(kc, data)
    else:
        if args.filename:
            data = read_csv(args.filename)
        elif args.user_id:
            user = kc.users.get(args.user_id)
            data.append(user)
        else:
            data = kc.users.list()

        update(kc, nc, data)


def parse_config(section, filename='update-expiry.conf'):
    """Read configuration settings from config file"""

    options = {}
    config_file = os.path.join(os.getcwd(), filename)

    try:
        with open(config_file):
            parser = SafeConfigParser()
            parser.read(config_file)
    except IOError as err:
        print_stderr(str(err))
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
    parser.add_argument('-u', '--user-id',
                        help='User ID to process')
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
            print_stderr(str(err))
            errors += 1
            continue

        # skip users that have no tenant
        if not getattr(user, "tenantId", None):
            continue

        try:
            tenant = kc.tenants.get(user.tenantId)
        except NotFound as err:
            print_stderr(str(err))
            errors += 1
            continue

        if not PT_RE.match(tenant.name):
            continue

        tenants += 1

        usage = nc.usage.get(user.tenantId, start, end)
        cpu_hours = getattr(usage, 'total_vcpus_usage', None)

        if not hasattr(tenant, 'status'):
            print tenant.id, "tenant has no status set"
            set_status(user.tenantId, None)
        elif tenant.status == 'suspended':
            print tenant.id, 'tenant is suspended'
            suspended += 1
        elif tenant.status == 'admin':
            print tenant.id, 'tenant is admin. Will never expire'
        elif hasattr(tenant, 'expires') and tenant.expires is not None:
            # Convert expires string to datetime object for comparison
            expires = datetime.strptime(tenant.expires, dateformat)
            if expires <= datetime.today():
                print tenant.id, 'tenant expired...'
                set_status(user.tenantId, 'suspended')
                set_nova_quota(nc, tenant.id, ram=0, instances=0, cores=0)
                # TODO fix test cloud - can't list instances. Redmine #3604
                #instances = get_instances(nc, tenant.id)
                #print "\t%d instance%s found" % (len(instances), "s"[len(instances) == 1:])
                #if instances:
                #    for instance in instances:
                #        suspend_instance(instance)
                #        lock_instance(instance)
            else:
                print tenant.id, 'will expire on', tenant.expires
        elif cpu_hours < limit*0.8:
            print tenant.id, 'tenant is under 80%'
        elif cpu_hours <= limit:
            print tenant.id, 'tenant is over 80% - setting status to first'
            if tenant.status != 'first':
                send_email(user.email, tenant.name, 'first')
                set_status(user.tenantId, 'first')
        elif cpu_hours <= limit*1.2:
            print tenant.id, 'tenant is over 100% - setting status to second'
            if tenant.status != 'second':
                send_email(user.email, tenant.name, 'second')
                set_nova_quota(nc, tenant.id, ram=0, instances=0, cores=0)
                set_status(user.tenantId, 'second')
        elif cpu_hours > limit*1.2:
            print tenant.id, 'tenant is over 120% - setting status to final'
            if tenant.status != 'final':
                send_email(user.email, tenant.name, 'final')
                set_nova_quota(nc, tenant.id, ram=0, instances=0, cores=0)
                set_status(user.tenantId, 'final', new_expiry)

    print '\nProcessed', tenants, 'tenants.', \
        suspended, 'suspended.', errors, '404s'


def get_instances(nc, tenant_id):

    search_opts = {'tenant_id': tenant_id, 'all_tenants': 1}
    instances = nc.servers.list(search_opts=search_opts)
    return instances


def suspend_instance(instance):

    if instance.status == 'SUSPENDED':
        print "\t%s - instance is already suspended" % instance.id
    elif instance.status == 'SHUTOFF':
        print "\t%s - instance is off" % instance.id
    else:
        if DRY_RUN:
            print "\t%s - would suspend instance (dry run)" % instance.id
        else:
            instance.suspend()


def lock_instance(instance):

    if DRY_RUN:
        print "\t%s - would lock instance (dry run)" % instance.id
    else:
        instance.lock()


def set_nova_quota(nc, tenant_id, cores, instances, ram):

    if DRY_RUN:
        print "\twould set Nova quota to 0 (dry run)"
    else:
        print "\tsetting Nova quota to 0"
        nc.quotas.update(tenant_id=tenant_id,
                        ram=ram,
                        instances=instances,
                        cores=cores)

def set_status(tenant_id, status, expires=''):

    if DRY_RUN:
        if status is None:
            print "\twould set empty status (dry run)"
        else:
            print "\twould set status to %s (dry run)" % status
    else:
        if status is None:
            print "\tsetting empty status"
        else:
            print "\tsetting status to %s" % status
        kc.tenants.update(user.tenantId, status=status)


def render_template(tenantname, status):

    tmpl = ''
    if status == 'first':
        tmpl = 'first-notification.tmpl'
    elif status == 'second':
        tmpl = 'second-notification.tmpl'
    elif status == 'final':
        tmpl = 'final-notification.tmpl'

    env = Environment(loader=FileSystemLoader('templates'))
    try:
        template = env.get_template(tmpl)
    except TemplateNotFound as err:
        print_stderr('Template not found. Make sure status is correct.')

    template = template.render({'project_name': tenantname})
    return template


def send_email(recepient, tenantname, status):

    from email.mime.text import MIMEText
    msg = MIMEText(render_template(tenantname, status))

    msg['From'] = 'NeCTAR Research Cloud <bounces@rc.nectar.org.au>'
    msg['To'] = recepient
    msg['Reply-to'] = 'support@rc.nectar.org.au'
    msg['Subject'] = 'NeCTAR project upcoming expiry - %s' % tenantname

    s = smtplib.SMTP('smtp.unimelb.edu.au')

    if DRY_RUN:
        print "would send email to %s (dry run)" % recepient
    else:
        print 'Sending an email to', recepient
        try:
            s.sendmail(msg['From'], [recepient], msg.as_string())
        except smtplib.SMTPRecipientsRefused as err:
            print_stderr(str(err))
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
                kc.tenants.update(tenant.id, status='admin', expires='')


def print_stderr(msg):

    sys.stderr.write(msg+'\n')
    sys.stderr.flush()


if __name__ == '__main__':

    main()
