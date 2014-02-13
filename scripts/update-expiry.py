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
    parser.add_argument('-y', '--no-dry-run', action='store_false',
        default=True,
        help='Perform the actual actions, default is to only show \
                    what would happen')
    parser.add_argument('-f', '--filename', metavar='filename',
        type=argparse.FileType('r'),
        help='File path with a list of users')
    parser.add_argument('-a', '--set-admin', metavar='store_true',
        help='Mark a list of tenants as admins')

    return parser


def update(kc, nc, users, dry_run):
    """Update tenant start and expiry dates in Keystone DB"""

    dateformat = "%Y-%m-%d"
    limit = 4383 # 6 months in hours
    end = datetime.now() + relativedelta(days=1) # tomorrow
    expires = date.today() + relativedelta(months=1)
    tenants = suspended = errors = 0

    for user in users:
        user_id = user['id']
        start = user['start']
        # Needed when reading start date from file, for testing
        if type(start) is str:
            start = datetime.strptime(start, dateformat)

        try:
            user = kc.users.get(user_id)
            tenant = kc.tenants.get(user.tenantId)
            tenants += 1
        except NotFound as err:
            sys.stderr.write('%s\n' % str(err))
            errors += 1
            continue

        usage = nc.usage.get(user.tenantId, start, end)
        cpu_hours = getattr(usage, 'total_vcpus_usage', None)

        if not hasattr(tenant, 'started'):
            started = start.strftime(dateformat)
            print "Updating tenant start date to", started
            if not dry_run:
                kc.tenants.update(user.tenantId, started=started, status=None)
        else:
            if tenant.status == 'suspended':
                print tenant.id, 'tenant is suspended'
                suspended += 1
            elif tenant.status == 'admin':
                print tenant.id, 'tenant is admin. Will never expire'
            elif tenant.expires is date.today():
                print tenant.id, 'tenant expires today. Will suspend instances'
                # TODO Call to function to do that
            elif cpu_hours < limit*0.8:
              print tenant.id, 'tenant is under 80%'
            elif cpu_hours <= limit:
              print tenant.id, 'tenant is over 80% - 1st warning'
              if tenant.status != 'first':
                  if not dry_run:
                      send_email(user.email, tenant.name, dry_run)
                      kc.tenants.update(user.tenantId, status='first')
            elif cpu_hours <= limit*1.2:
              print tenant.id, 'tenant is over 100% - 2nd warning'
              if tenant.status != 'second':
                  if not dry_run:
                      send_email(user.email, tenant.name, dry_run)
                      kc.tenants.update(user.tenantId, status='second')
            elif cpu_hours > limit*1.2:
              print tenant.id, 'tenant is over 120% - final warning'
              if tenant.status != 'final':
                  if not dry_run:
                      send_email(user.email, tenant.name, dry_run)
                      kc.tenants.update(user.tenantId, expires=expires, status='final')

    print '\nProcessed', tenants, 'tenants.', suspended, 'suspended.', errors, '404s'


def render_template(tenantname):
    """Prepapre email"""

    env = Environment(loader=FileSystemLoader('templates'))
    template = env.get_template('first-notification.tmpl')
    template = template.render({ "project_name": tenantname })
    return template


def send_email(recepient, tenantname, dry_run):

    from email.mime.text import MIMEText
    msg = MIMEText(render_template(tenantname))

    msg['From'] = 'NeCTAR RC <rc-rt-bounces@melbourne.nectar.org.au>'
    msg['To'] = recepient
    msg['Reply-to'] = 'support@rc.nectar.org.au'
    msg['Subject'] = 'NeCTAR project upcoming expiry - %s' % tenantname

    s = smtplib.SMTP('smtp.unimelb.edu.au')

    print 'Sending an email to', recepient
    if not dry_run:
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
              LIMIT 10"
              #LIMIT 845"

      cursor.execute(sql)
      results = cursor.fetchall()

    # Name user attributes for easy access
    results = [{'id':x, 'start':y} for x,y in results]
    return results


def admin_set(kc, users, dry_run):
    """Set status attribute to admin for cloud admins"""

    for user in users:
        user_id = user['id']
        admin = kc.tenants.get(user_id)
        if hasattr(admin, 'status'):
            print admin.id, 'status set to', admin.status
        else:
            print 'Setting', admin.id, 'to never expire...'
            if not dry_run:
                kc.tenants.update(user_id, status='admin')


if __name__ == '__main__':

    args = collect_args().parse_args()
    kc = auth.get_keystone_client()
    nc = auth.get_nova_client()

    users = get_data(args.filename)

    if args.set_admin:
        admin_set(kc, users, args.no_dry_run)
    else:
        update(kc, nc, users, args.no_dry_run)
