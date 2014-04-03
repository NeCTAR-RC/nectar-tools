#!/usr/bin/env python

import os
import sys
import re
import argparse
import smtplib
import time
from collections import OrderedDict
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from keystoneclient.exceptions import AuthorizationFailure
from keystoneclient.v2_0 import client as ks_client
from novaclient.v1_1 import client as nova_client

from jinja2 import Environment, FileSystemLoader

email_pattern = re.compile('([\w\-\.\']+@(\w[\w\-]+\.)+[\w\-]+)')
global tenant_data, user_data, total, smtp_server


def collect_args():

    parser = argparse.ArgumentParser(
        description='Notifies users of an upcoming outage')

    parser.add_argument('-y', '--no-dry-run', action='store_false',
                        default=True,
                        help='Perform the actual actions, \
                              default is to only show what would happen')
    parser.add_argument('-z', '--target-zone',
                        required=True,
                        help='Specify availability zone to notify')
    parser.add_argument('-t', '--test', action='store_true',
                        help='Use test data instead of all keystone tenants')
    parser.add_argument('-p', '--smtp_server',
                        default='120.0.0.1',
                        help='SMTP server to use, defaults to localhost')
    parser.add_argument('-s', '--skip-to-tenant',
                        required=False,
                        default=None,
                        help='Skip processing up to a given tenant. \
                             Useful in cases where the script has partially\
                             completed.')

    return parser


def mailout(user_id, user, zone, dry_run):

    instances = user['instances']
    email = user['email']
    name = user['name']
    enabled = user['enabled']
    affected = user['affected']

    subject = 'NeCTAR Research Cloud outage'
    if affected:
        subject += '%s affecting your VMs'
    affected_instances = len(instances)

    text_template, html_template = render_templates(
        subject,
        instances,
        zone,
        affected)

    if not enabled:
        print 'User %s: user disabled, not sending email => %s' % (name, email)
        return

    if email is None:
        print 'User %s: no email address' % name
        return

    if email_pattern.match(email) is None:
        print 'User %s: invalid email address => %s' % (name, email)
        return

    msg = 'User %s: sending email to %s => %s instances affected' % \
        (name, email, affected_instances)
    if dry_run:
        msg = msg + ' [DRY RUN]'
        print msg
    else:
        print msg
        sys.stdout.flush()
        send_email(email,
                   text_template,
                   html_template,
                   subject)


def render_templates(subject, instances, zone, affected):

    env = Environment(loader=FileSystemLoader('templates'))
    text_template = env.get_template('outage-notification.tmpl')
    text_template = text_template.render(
        {'instances': instances,
         'zone': zone,
         'affected': affected})
    html_template = env.get_template('outage-notification.html.tmpl')
    html_template = html_template.render(
        {'title': subject,
         'instances': instances,
         'zone': zone,
         'affected': affected})

    return text_template, html_template


def send_email(recepient, text_template, html_template, subject):

    global smtp_server

    msg = MIMEMultipart('alternative')
    msg.attach(MIMEText(text_template, 'plain', 'utf-8'))
    msg.attach(MIMEText(html_template, 'html', 'utf-8'))

    msg['From'] = 'NeCTAR Research Cloud <bounces@rc.nectar.org.au>'
    msg['To'] = recepient
    msg['Reply-to'] = 'support@rc.nectar.org.au'
    msg['Subject'] = subject

    s = smtplib.SMTP(smtp_server)

    try:
        s.sendmail(msg['From'], [recepient], msg.as_string())
        time.sleep(2)
    except smtplib.SMTPRecipientsRefused as err:
        sys.stderr.write('%s\n' % str(err))
    finally:
        s.quit()


def get_keystone_client():

    auth_username = os.environ.get('OS_USERNAME')
    auth_password = os.environ.get('OS_PASSWORD')
    auth_tenant = os.environ.get('OS_TENANT_NAME')
    auth_url = os.environ.get('OS_AUTH_URL')

    try:
        kc = ks_client.Client(username=auth_username,
                              password=auth_password,
                              tenant_name=auth_tenant,
                              auth_url=auth_url)
    except AuthorizationFailure as e:
        print e
        print 'Authorization failed, have you sourced your openrc?'
        sys.exit(1)

    return kc


def get_nova_client():

    auth_username = os.environ.get('OS_USERNAME')
    auth_password = os.environ.get('OS_PASSWORD')
    auth_tenant = os.environ.get('OS_TENANT_NAME')
    auth_url = os.environ.get('OS_AUTH_URL')

    nc = nova_client.Client(auth_username,
                            auth_password,
                            auth_tenant,
                            auth_url,
                            service_type='compute')
    return nc


def all_servers(client):
    servers = []
    marker = None

    while True:
        opts = {'all_tenants': True}
        if marker:
            opts['marker'] = marker
        res = client.servers.list(search_opts=opts)
        if not res:
            break
        servers.extend(res)
        marker = servers[-1].id
    return servers


def get_data(kc, nc):

    instances = all_servers(nc)
    tenants = kc.tenants.list()

    populate_instances(instances)
    populate_tenants(tenants)


def get_test_data(kc, nc):

    tids = ['42', '5', '5a6fcfe12c7a4909935e1c3e4a3f3d0c']

    instances = []
    for tid in tids:
        opts = {'all_tenants': True, 'tenant_id': tid}
        tinstances = nc.servers.list(search_opts=opts)
        for tinstance in tinstances:
            instances.append(tinstance)

    tenants = []
    for tid in tids:
        tenants.append(kc.tenants.get(tid))

    populate_instances(instances)
    populate_tenants(tenants)


def populate_instances(instances):

    global tenant_data

    for instance in instances:
        if instance.tenant_id not in tenant_data:
            tenant_data[instance.tenant_id] = {'instances': [instance, ]}
        else:
            tenant_data[instance.tenant_id]['instances'].append(instance)


def populate_tenants(tenants):

    global tenant_data

    for tenant in tenants:
        users = kc.users.list(tenant_id=tenant.id)
        name = tenant.name
        if tenant.id not in tenant_data:
            tenant_data[tenant.id] = {'users': users}
        else:
            tenant_data[tenant.id]['users'] = users
        tenant_data[tenant.id]['name'] = name


def populate_users(tenant, data, target_zone):

    global tenant_data, user_data, total

    tenant_name = data['name']

    users = data['users']
    print 'Tenant %s: # users => %s' % (tenant, len(users))

    try:
        instances = data['instances']
    except KeyError:
        instances = []
    print 'Tenant %s: # instances => %s' % (tenant, len(instances))

    instances_in_az = []
    for instance in instances:
        zone = getattr(instance, 'OS-EXT-AZ:availability_zone')
        if zone == target_zone:
            instances_in_az.append(instance)

    affected_instances = len(instances_in_az)

    if affected_instances == 0:
        affected = False
    else:
        affected = True

    print 'Tenant %s: # affected instances => %s' % \
        (tenant, affected_instances)
    total += affected_instances

    for user in users:
        if user.id not in user_data:
            user_data[user.id] = {'instances': [],
                                  'email': user.email,
                                  'enabled': user.enabled,
                                  'name': user.name,
                                  'affected': affected}
        user = user_data[user.id]
        for iiaz in instances_in_az:
            user['instances'].append([tenant_name, iiaz])
        user['affected'] = user['affected'] or affected


def skip(tenant, skip_to_tenant):

    if tenant == skip_to_tenant:
        print 'Found tenant %s, resuming mailout' % tenant
        skip = False
    else:
        print 'Skipping tenant %s' % tenant
        skip = True
    return skip


if __name__ == '__main__':

    global tenant_data, user_data, smtp_server

    total = 0
    tenant_data = OrderedDict()
    user_data = OrderedDict()

    args = collect_args().parse_args()
    kc = get_keystone_client()
    nc = get_nova_client()

    zone = args.target_zone
    smtp_server = args.smtp_server

    if args.test:
        get_test_data(kc, nc)
    else:
        get_data(kc, nc)

    proceed = False

    for tenant, data in tenant_data.iteritems():
        if args.skip_to_tenant is not None and not proceed:
            if not skip(tenant, args.skip_to_tenant):
                populate_users(tenant, data, zone)
                proceed = True
        else:
            populate_users(tenant, data, zone)

    for uid, user in user_data.iteritems():
        mailout(uid, user, zone, args.no_dry_run)

    print 'Total instances affected in %s zone: %s' % (zone, total)
