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

email_pattern = re.compile('([\w\-\.]+@(\w[\w\-]+\.)+[\w\-]+)')


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
    parser.add_argument('-s', '--skip-to-tenant',
                        required=False,
                        default=None,
                        help='Skip processing up to a given tenant. \
                             Useful in cases where the script has partially\
                             completed.')

    return parser


def mailout(tenant, tenant_data, target_zone, dry_run):

    total_affected_instances = 0

    tenant_name = tenant_data['name']

    users = tenant_data['users']
    print 'Tenant %s: # users => %s' % (tenant, len(users))

    try:
        instances = tenant_data['instances']
    except KeyError:
        instances = []
    print 'Tenant %s: # instances => %s' % (tenant, len(instances))

    instances_in_az = []
    for instance in instances:
        zone = getattr(instance, 'OS-EXT-AZ:availability_zone')
        if zone == target_zone:
            instances_in_az.append(instance)

    affected_instances = len(instances_in_az)
    total_affected_instances += affected_instances

    if affected_instances == 0:
        affected = False
    else:
        affected = True

    print 'Tenant %s: # affected instances => %s' % \
        (tenant, total_affected_instances)

    for user in users:
        text = 'NeCTAR Research Cloud outage'
        if affected:
            subject = '%s affecting your VMs (project: %s)' % \
                (text, tenant_name)
        else:
            subject = '%s (project: %s)' % (text, tenant_name)
        text_template, html_template = render_templates(
            subject,
            instances_in_az,
            tenant_name,
            target_zone,
            affected)

        if not user.enabled:
            print 'Tenant %s: user disabled, not sending email => %s' % \
                (tenant, user.email)
            continue

        if user.email is None:
            print 'Tenant %s: no email address' % tenant
            continue

        if email_pattern.match(user.email) is None:
            print 'Tenant %s: invalid email address => %s' % \
                (tenant, user.email)
            continue

        msg = 'Tenant %s: sending email to %s => %s instances affected' % \
            (tenant, user.email, affected_instances)
        if dry_run:
            msg = msg + ' [DRY RUN]'
            print msg
        else:
            print msg
            send_email(user.email,
                       text_template,
                       html_template,
                       subject)

    return total_affected_instances


def render_templates(subject, instances, project, zone, affected):

    env = Environment(loader=FileSystemLoader('templates'))
    text_template = env.get_template('outage-notification.tmpl')
    text_template = text_template.render(
        {'instances': instances,
         'project_name': project,
         'target_zone': zone,
         'affected': affected})
    html_template = env.get_template('outage-notification.html.tmpl')
    html_template = html_template.render(
        {'title': subject,
         'instances': instances,
         'project_name': project,
         'target_zone': zone,
         'affected': affected})

    return text_template, html_template


def send_email(recepient, text_template, html_template, subject):

    msg = MIMEMultipart('alternative')
    msg.attach(MIMEText(text_template, 'plain', 'utf-8'))
    msg.attach(MIMEText(html_template, 'html', 'utf-8'))

    msg['From'] = 'NeCTAR Research Cloud <bounces@rc.nectar.org.au>'
    msg['To'] = recepient
    msg['Reply-to'] = 'support@rc.nectar.org.au'
    msg['Subject'] = subject

    s = smtplib.SMTP('smtp.unimelb.edu.au')

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

    data = OrderedDict()
    instances = all_servers(nc)
    tenants = kc.tenants.list()

    for instance in instances:
        if instance.tenant_id not in data:
            data[instance.tenant_id] = {'instances': [instance, ]}
        else:
            data[instance.tenant_id]['instances'].append(instance)

    for tenant in tenants:
        users = kc.users.list(tenant_id=tenant.id)
        name = tenant.name
        if tenant.id not in data:
            data[tenant.id] = {'users': users}
        else:
            data[tenant.id]['users'] = users
        data[tenant.id]['name'] = name

    return data


def get_test_data(kc, nc):

    data = OrderedDict()
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

    for instance in instances:
        if instance.tenant_id not in data:
            data[instance.tenant_id] = {'instances': [instance, ]}
        else:
            data[instance.tenant_id]['instances'].append(instance)

    for tenant in tenants:
        users = kc.users.list(tenant_id=tenant.id)
        name = tenant.name
        if tenant.id not in data:
            data[tenant.id] = {'users': users}
        else:
            data[tenant.id]['users'] = users
        data[tenant.id]['name'] = name

    return data


def skip(tenant, skip_to_tenant):

    if tenant == skip_to_tenant:
        print 'Found tenant %s, resuming mailout' % tenant
        skip = False
    else:
        print 'Skipping tenant %s' % tenant
        skip = True
    return skip

if __name__ == '__main__':

    args = collect_args().parse_args()
    kc = get_keystone_client()
    nc = get_nova_client()

    if args.test:
        data = get_test_data(kc, nc)
    else:
        data = get_data(kc, nc)

    total = 0
    proceed = False
    for tenant, tenantdata in data.iteritems():
        if args.skip_to_tenant is not None and not proceed:
            if not skip(tenant, args.skip_to_tenant):
                total += mailout(tenant,
                                 tenantdata,
                                 args.target_zone,
                                 args.no_dry_run)
                proceed = True
        else:
            total += mailout(tenant,
                             tenantdata,
                             args.target_zone,
                             args.no_dry_run)

    print 'Total instances affected in zone %s: %s' % (args.target_zone, total)
