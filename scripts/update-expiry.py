#!/usr/bin/env python

import argparse
import MySQLdb
import auth
import csv
import smtplib
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
#from keystoneclient import utils
from keystoneclient.exceptions import NotFound
from jinja2 import Environment, FileSystemLoader


def collect_args():
    """docstring for collect_args"""

    parser = argparse.ArgumentParser(description='Updates tenant expiry date')
    parser.add_argument('-y', '--no-dry-run', action='store_true',
            required=False,
            help='Perform the actual actions, default is to only show \
                    what would happen')
    return parser


def update(client, user_list, dry_run=True):
    """Update tenant start and expiry dates in Keystone DB"""

    today = date.today()
    tenants = errors = 0

    for row in user_list:
        #userId = row[0]
        #start_date = row[1].strftime('%Y-%m-%d')
        tenantId = row[0]
        start_date = row[1]
        try:
            #user = client.users.get(userId)
            #tenantId = user.tenantId
            tenant = client.tenants.get(tenantId)
            tenants += 1
        except NotFound as e:
            print e, '\n'
            errors += 1
            continue
        if hasattr(tenant, 'status'):
            #utils.print_dict(tenant._info)
            started = datetime.strptime(tenant.started, '%Y-%m-%d').date()
            expires = datetime.strptime(tenant.expires, '%Y-%m-%d').date()
            warning = today + relativedelta(months=1)
            new_expiry = warning.isoformat()
            print '\n',tenant.id
            if tenant.status == 'suspended':
                print 'Tenant is suspended.'
            elif tenant.status == 'expired':
                print 'Tenant expired on %s.' % tenant.expires
            elif tenant.status == 'admin':
                print 'Tenant is admin. Will never expire.'
            elif tenant.status is None and warning > expires < today:
                print 'Tenant expires on', tenant.expires
                print 'Setting expiry date to 1 month from now.'
                client.tenants.update(tenantId, expires=new_expiry,
                        status='emailed')
                #send_email(user.email, tenant.name, new_expiry, dry_run)
                send_email('foo', tenant.name, new_expiry, dry_run)
            elif tenant.status != 'emailed' and expires <= warning:
                print 'Expiry is within 4 weeks.'
                print 'Setting expiry date to 1 month from then.'
                new_expiry = (expires + relativedelta(months=1)).isoformat()
                client.tenants.update(tenantId, expires=new_expiry,
                        status='emailed')
                send_email('foo', tenant.name, new_expiry, dry_run)
            elif expires == today:
                print 'Tenant expires today. Suspending...'
                client.tenants.update(tenantId, status='suspended')
            else:
                print 'Tenant will expire on %s' % tenant.expires
        else:
            #utils.print_dict(tenant._info)
            print tenant.id
            started = datetime.strptime(start_date, '%Y-%m-%d').date()
            expires = started + relativedelta(months=3)
            print "Updating tenant start date to %s" % start_date
            print "Updating tenant expiry date to %s" % expires
            client.tenants.update(tenantId, started=start_date, expires=expires.isoformat(), status=None)

    print '\nProcessed', tenants, 'tenants.', errors, '404s'


def render_template(tenantname, expires):
    """Prepapre email"""

    env = Environment(loader=FileSystemLoader('templates'))
    template = env.get_template('first-notification.tmpl')
    template = template.render({ "project_name": tenantname, "expiry_date": expires})
    return template


def send_email(recepient, tenantname, expires, dry_run):

    sender = 'NeCTAR RC <rc-rt-bounces@melbourne.nectar.org.au>'
    replyto = 'support@rc.nectar.org.au'
    subject = 'NeCTAR project upcoming expiry - %s' % tenantname
    body = render_template(tenantname, expires)
    msg = ("From: %s\r\nTo: %s\r\nReply-To: %s\r\nSubject: %s\r\n\r\n%s"
        % (sender, recepient, replyto, subject, body))
    s = smtplib.SMTP('smtp.unimelb.edu.au')
    print 'Sending email to', recepient
    if not dry_run:
        try:
            s.sendmail(sender, [recepient], msg)
        except smtplib.SMTPRecipientsRefused as e:
            print e
        finally:
            s.quit()


def get_mysql_data():

    db = MySQLdb.connect("db1-qh2","rcshib_ro","ash2;workers","rcshibboleth")
    cursor = db.cursor()

    sql = "SELECT user_id,terms FROM user \
            WHERE user_id is not NULL \
            ORDER BY terms ASC \
            LIMIT 1200"

    cursor.execute(sql)
    results = cursor.fetchall()
    return results


def get_data(filename):

    #with open('data.txt', 'w') as thefile:
    #    for item in results:
    #        print>>thefile, item

    #results = open('data.txt').read().splitlines()
    #return results
    reader = csv.reader(open(filename))
    return filter(None, reader)


def admin_set(client, uuid_list, dry_run=True):
    """Set expires attribute to None for cloud admins"""

    for uuid in uuid_list:
        uuid = uuid[0]
        admin = client.tenants.get(uuid)
        if hasattr(admin, 'status'):
            print admin.id, 'status set to', admin.status
        else:
            print 'Setting', admin.id, 'to never expire...'
            if not dry_run:
                client.tenants.update(uuid, status='admin')


if __name__ == '__main__':

    args = collect_args().parse_args()

    kc = auth.get_keystone_client()

    if args.no_dry_run:
        dry_run = False
    else:
        dry_run = True

    #admin_list = get_data('admins.txt')
    #admin_set(kc, admin_list)
    user_list = get_data('data.txt')
    #user_list = get_mysql_data()
    update(kc, user_list, dry_run)
