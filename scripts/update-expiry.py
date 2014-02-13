#!/usr/bin/env python

import os
import sys
import argparse
import MySQLdb
import auth
import csv
import smtplib
from ConfigParser import SafeConfigParser
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from keystoneclient.exceptions import NotFound
from jinja2 import Environment, FileSystemLoader


DRY_RUN = True


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
        help='Perform the actual actions, default is to only show \
                    what would happen')
    parser.add_argument('-f', '--filename',
        type=argparse.FileType('r'),
        help='File path with a list of users')
    parser.add_argument('-a', '--set-admin', action='store_true',
        help='Mark a list of tenants as admins')

    return parser


def update(kc, nc, users):
    """Update tenant start and expiry dates in Keystone DB"""

    dateformat = "%Y-%m-%d"
    limit = 4383 # 6 months in hours
    end = datetime.now() + relativedelta(days=1) # tomorrow
    new_expiry = date.today() + relativedelta(months=1)
    tenants = suspended = errors = 0

    for user in users:
        user_id = user['id']
        start = user['start']

        try:
            user = kc.users.get(user_id)
            tenant = kc.tenants.get(user.tenantId)
            tenants += 1
        except NotFound as err:
            sys.stderr.write('%s\n' % str(err))
            errors += 1
            continue

        # Needed when reading start date from file, for testing
        if type(start) is str:
            start = datetime.strptime(start, dateformat)

        usage = nc.usage.get(user.tenantId, start, end)
        cpu_hours = getattr(usage, 'total_vcpus_usage', None)

        if not hasattr(tenant, 'status'):
            started = start.strftime(dateformat)
            print "Updating tenant start date to", started
            if not DRY_RUN:
                kc.tenants.update(user.tenantId, started=started,
                                  status=None)
        elif tenant.status == 'suspended':
            print tenant.id, 'tenant is suspended'
            suspended += 1
        elif tenant.status == 'admin':
            print tenant.id, 'tenant is admin. Will never expire'
        elif tenant.status == 'final':
            print tenant.id, 'will expire on', tenant.expires
        elif hasattr(tenant, 'expires') and tenant.expires is not None:
            # Convert expires string to datetime object for comparison
            expires = datetime.strptime(tenant.expires, dateformat)
            if expires <= datetime.today():
                print tenant.id, 'tenant expired! Will suspend instances'
                if not DRY_RUN:
                    # Suspend any instances and set status to suspended
                    get_instances(nc, tenant.id)
                    kc.tenants.update(user.tenantId, status='suspended')
        elif cpu_hours < limit*0.8:
            print tenant.id, 'tenant is under 80%'
        elif cpu_hours <= limit:
            print tenant.id, 'tenant is over 80% - 1st warning'
            if tenant.status != 'first':
                if not DRY_RUN:
                    # Inform the tenant of allocation process
                    send_email(user.email, tenant.name)
                    kc.tenants.update(user.tenantId, status='first')
        elif cpu_hours <= limit*1.2:
            print tenant.id, 'tenant is over 100% - 2nd warning'
            if tenant.status != 'second':
                if not DRY_RUN:
                    # Inform the tenant, set quota to 0 and update the status
                    send_email(user.email, tenant.name)
                    set_nova_quota(nc, tenant.id, ram=0, instances=0, cores=0)
                    kc.tenants.update(user.tenantId, status='second')
        elif cpu_hours > limit*1.2:
            print tenant.id, 'tenant is over 120% - final warning'
            if tenant.status != 'final':
                if not DRY_RUN:
                    # Inform the tenant and set expires date and status
                    send_email(user.email, tenant.name)
                    kc.tenants.update(user.tenantId, expires=new_expiry,
                        status='final')

    print '\nProcessed', tenants, 'tenants.', suspended, 'suspended.', errors, '404s'


def get_instances(nc, tenant_id):

    search_opts={'tenant_id': tenant_id, 'all_tenants': 1}
    instances = nc.servers.list(search_opts=search_opts)
    print "%d instance%s found" % (len(instances), "s"[len(instances)==1:])
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
    template = template.render({ "project_name": tenantname })
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


def get_data(filename=False):

    results = []
    options = parse_config('mysql')

    if type(filename) is file:
        reader = csv.reader(filename)
        results = filter(None, reader)
    else:
        db = MySQLdb.connect(options['host'], options['username'], options['password'], options['database'])
        cursor = db.cursor()

        sql = "SELECT user_id,terms FROM user \
                WHERE user_id is not NULL \
                ORDER BY terms ASC \
                LIMIT 100"
                #LIMIT 845"

        cursor.execute(sql)
        results = cursor.fetchall()

    # Name user attributes for easy access
    results = [{'id':x, 'start':y} for x,y in results]
    return results


def admin_set(kc, users):
    """Set status attribute to admin for cloud admins"""

    for user in users:
        user_id = user['id']
        tenant = kc.tenants.get(user_id)
        print 'Setting', tenant.id, 'to admin status'
        if not DRY_RUN:
            kc.tenants.update(tenant.id, status='admin')


if __name__ == '__main__':

    args = collect_args().parse_args()
    if args.no_dry_run:
        DRY_RUN = False
    kc = auth.get_keystone_client()
    nc = auth.get_nova_client()

    users = get_data(args.filename)

    if args.set_admin:
        admin_set(kc, users)
    else:
        update(kc, nc, users)
