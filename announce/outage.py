#!/usr/bin/env python

import os
import sys
import re
import argparse
import smtplib
import logging
import datetime
from collections import OrderedDict
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from keystoneclient.exceptions import AuthorizationFailure
from keystoneclient.v2_0 import client as ks_client
from novaclient.v1_1 import client as nova_client

from jinja2 import Environment, FileSystemLoader

LOG = logging.getLogger(__name__)

email_pattern = re.compile('([\w\-\.\']+@(\w[\w\-]+\.)+[\w\-]+)')

total = 0
tenant_data = OrderedDict()
user_data = OrderedDict()
smtp_server = None


def collect_args():

    parser = argparse.ArgumentParser(
        description='Notifies users of an upcoming outage')

    parser.add_argument('-y', '--no-dry-run', action='store_false',
                        default=True,
                        help='Perform the actual actions, \
                              default is to only show what would happen')

    parser.add_argument('-o', '--only-affected', action='store_true',
                        default=False,
                        help='Only mail users with affected instances')
    parser.add_argument('--status',
                        default=None,
                        help='Only consider instances with status')
    parser.add_argument('-t', '--test', action='store_true',
                        help='Use test data instead of all keystone tenants')
    parser.add_argument('-p', '--smtp_server',
                        default='127.0.0.1',
                        help='SMTP server to use, defaults to localhost')
    parser.add_argument('-st', '--start_time', action='store',
                        type=get_datetime,
                        help='Outage start time (e.g. \'09:00 25-06-2015\')',
                        required=True)
    parser.add_argument('-d', '--duration', action='store', type=int,
                        help='Duration of outage in hours', required=True)
    parser.add_argument('-tz', '--timezone', action='store',
                        help='Timezone (e.g. AEDT)', required=True)
    parser.add_argument('-s', '--skip-to-tenant',
                        required=False,
                        default=None,
                        help='Skip processing up to a given tenant. \
                             Useful in cases where the script has partially\
                             completed.')
    parser.set_defaults(func='args')

    group = parser.add_mutually_exclusive_group()

    group.add_argument('-z', '--target-zone', required=False,
                       help='Availability zone affected by outage')
    group.add_argument('-n', '--node', required=False,
                       help='Host affected by the outage [e.g. np-rcc[5-84]')
    return parser


def get_datetime(dt_string):
    return datetime.datetime.strptime(dt_string, '%H:%M %d-%m-%Y')


def mailout(user_id, user, start_ts, end_ts, tz, dry_run, only_affected,
            zone=None, host=None):

    instances = user['instances']
    email = user['email']
    name = user['name']
    enabled = user['enabled']
    subject = 'NeCTAR Research Cloud outage'

    affected_instances = 0

    for project, servers in instances.iteritems():
        for server in servers:
            affected_instances += 1

    affected = bool(affected_instances)
    if affected:
        subject += ' affecting your VMs'

    if only_affected and affected_instances == 0:
        print 'User %s: user not affected, not sending email => %s' % \
            (name, email)
        return False

    text, html = render_templates(subject, instances, start_ts, end_ts, tz,
                                  zone, affected)

    if not enabled:
        print 'User %s: user disabled, not sending email => %s' % (name, email)
        return False

    if email is None:
        print 'User %s: no email address' % name
        return False

    if email_pattern.match(email) is None:
        print 'User %s: invalid email address => %s' % (name, email)
        return False

    msg = 'User %s: sending email to %s => %s instances affected' % \
        (name, email, affected_instances)
    if dry_run:
        msg = msg + ' [DRY RUN]'
        print msg
    else:
        print msg
        sys.stdout.flush()
        send_email(email, subject, text, html)

    return True


def render_templates(subject, instances, start_ts, end_ts, tz, zone, affected):

    duration = end_ts - start_ts
    days = duration.days
    hours = duration.seconds//3600

    env = Environment(loader=FileSystemLoader('templates'))
    text = env.get_template('outage-notification-host.tmpl')
    text = text.render(
        {'instances': instances,
         'zone': zone,
         'start_ts': start_ts,
         'end_ts': end_ts,
         'days': days,
         'hours': hours,
         'tz': tz,
         'affected': affected})
    html = env.get_template('outage-notification-host.html.tmpl')
    html = html.render(
        {'title': subject,
         'instances': instances,
         'zone': zone,
         'start_ts': start_ts,
         'end_ts': end_ts,
         'days': days,
         'hours': hours,
         'tz': tz,
         'affected': affected})

    return text, html


def send_email(recipient, subject, text, html):
    global smtp_server

    msg = MIMEMultipart('alternative')
    msg.attach(MIMEText(text, 'plain', 'utf-8'))
    msg.attach(MIMEText(html, 'html', 'utf-8'))

    msg['From'] = 'NeCTAR Research Cloud <bounces@rc.nectar.org.au>'
    msg['To'] = recipient
    msg['Reply-to'] = 'support@rc.nectar.org.au'
    msg['Subject'] = subject

    s = smtplib.SMTP(smtp_server)

    try:
        s.sendmail(msg['From'], [recipient], msg.as_string())
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
        return ks_client.Client(username=auth_username,
                                password=auth_password,
                                tenant_name=auth_tenant,
                                auth_url=auth_url)
    except AuthorizationFailure as e:
        print e
        print 'Authorization failed, have you sourced your openrc?'
        sys.exit(1)


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


def get_servers(client, zone=None, inst_status=None):
    marker = None

    while True:
        opts = {'all_tenants': True}
        if inst_status is not None:
            opts['status'] = inst_status
        if marker:
            opts['marker'] = marker
        response = client.servers.list(search_opts=opts)
        if not response:
            break
        for server in response:
            marker = server.id
            server_az = server._info.get('OS-EXT-AZ:availability_zone') or ''
            if zone and not server_az.lower() == zone.lower():
                continue
            yield server


def get_servers_from_host(client, host, inst_status=None):
    marker = None
    opts = {'all_tenants': True,
            'host': host
            }

    if inst_status is not None:
            opts['status'] = inst_status
    if marker:
            opts['marker'] = marker
    servers = client.servers.list(search_opts=opts)

    return servers


def get_data(kc, nc, zone, inst_status, only_affected):

    print 'Gathering instance,',

    servers = list(get_servers(nc, zone, inst_status))
    print 'tenant,',
    tenants = kc.tenants.list()
    server_tenants = set([server.tenant_id for server in servers])

    populate_instances(servers)
    print 'user data.'
    for tenant in tenants:
        if tenant.id in server_tenants:
            populate_tenant(tenant)


def get_data_from_host(kc, nc, host, inst_status, only_affected):
    servers = []
    tenants = kc.tenants.list()
    filtered_tenant = []
    filtered_vm = []

    print "Gathering instance"

    if len(host) == 1:
        servers.append(get_servers_from_host(nc, ''.join(host), inst_status))
    else:
        for h in host:
            servers.append(get_servers_from_host(nc, ''.join(h), inst_status))

    populate_instances(servers, node=True)

    for server in servers:
        for vm in server:
            filtered_vm.append(vm.tenant_id)

    for fv in set(filtered_vm):
        for tenant in tenants:
            if tenant.id == fv:
                filtered_tenant.append(tenant)

    if len(filtered_tenant) == 1:
        populate_tenant(filtered_tenant[0])
    else:
        for t in filtered_tenant:
            populate_tenant(t)


def get_test_data(kc, nc):

    tids = ['42',  # nectar_tenant
            '2f6f7e75fc0f453d9c127b490b02e9e3',  # NeCTAR-Devs
            'f42f9588576c43969760d81384b83b1f']  # NeCTAR-Admins

    instances = []
    for tid in tids:
        opts = {'all_tenants': True, 'tenant_id': tid}
        tinstances = nc.servers.list(search_opts=opts)
        for tinstance in tinstances:
            instances.append(tinstance)

    for tid in tids:
        tenant = kc.tenants.get(tid)
        populate_tenant(tenant)

    populate_instances(instances)


def populate_instances(instances, node=None):
    if node is None:
        for instance in instances:
            populate_instance(instance)
    else:
        for instance in instances:
            for i in instance:
                populate_instance(i)


def populate_instance(instance):
    if instance.tenant_id not in tenant_data:
        tenant_data[instance.tenant_id] = {'instances': []}
    tenant_data[instance.tenant_id]['instances'].append(instance)


def populate_tenant(tenant):
    users = tenant.list_users()
    name = tenant.name
    if tenant.id not in tenant_data:
        tenant_data[tenant.id] = {'users': users, 'instances': []}
    else:
        tenant_data[tenant.id]['users'] = users
    tenant_data[tenant.id]['name'] = name


def populate_tenant_users(tenant, data, target_zone):

    global total

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

    print 'Tenant %s: # affected instances => %s' % \
        (tenant, affected_instances)
    total += affected_instances

    for user in users:
        user = populate_user(user)
        for instance in instances_in_az:
            if tenant_name not in user['instances']:
                user['instances'][tenant_name] = []
            user['instances'][tenant_name].append(instance)


def populate_tenant_users_host(tenant, data):

    global total

    tenant_name = data['name']

    users = data['users']
    print 'Tenant %s: # users => %s' % (tenant, len(users))

    try:
        instances = data['instances']
    except KeyError:
        instances = []
    print 'Tenant %s: # instances => %s' % (tenant, len(instances))

    affected_instances = len(instances)

    print 'Tenant %s: # affected instances => %s' % \
        (tenant, affected_instances)
    total += affected_instances

    for user in users:
        user = populate_user(user)
        for instance in instances:
            if tenant_name not in user['instances']:
                user['instances'][tenant_name] = []
            user['instances'][tenant_name].append(instance)


def populate_user(user):
    if user.id not in user_data:
        user_data[user.id] = {'instances': {},
                              'email': user._info.get('email', None),
                              'enabled': user.enabled,
                              'name': user.name}
    return user_data[user.id]


def skip(tenant, skip_to_tenant):

    if tenant == skip_to_tenant:
        print 'Found tenant %s, resuming mailout' % tenant
        skip = False
    else:
        print 'Skipping tenant %s' % tenant
        skip = True
    return skip


def parse_hosts(nodes):
    hosts = []
    hostname = nodes.split('[')[0]
    m = re.search(r"\[([A-Za-z0-9-]+)\]", nodes)
    if m is not None:
        host_start = int(m.group(1).split('-')[0])
        try:
            host_end = int(m.group(1).split('-')[1])
        except IndexError:
            host_end = host_start
        for x in range(host_start, host_end + 1):
            host = hostname + str(x)
            hosts.append(host)
    else:
        hosts.append(nodes)
    return hosts


def main():

    global smtp_server

    args = collect_args().parse_args()

    kc = get_keystone_client()
    nc = get_nova_client()

    zone = args.target_zone
    node = args.node
    smtp_server = args.smtp_server
    inst_status = args.status

    start_ts = args.start_time
    end_ts = start_ts + datetime.timedelta(hours=args.duration)

    if zone:
        print "Listing instances from %" % zone
        if args.test:
            get_test_data(kc, nc)
        else:
            get_data(kc, nc, zone, inst_status, args.only_affected)

        print "Gathering tenant information."
        proceed = False
        for tenant, data in tenant_data.iteritems():
            if args.skip_to_tenant is not None and not proceed:
                if not skip(tenant, args.skip_to_tenant):
                    populate_tenant_users(tenant, data, zone)
                    proceed = True
            else:
                populate_tenant_users(tenant, data, zone)

    if node:
        if args.test:
            get_test_data(kc, nc)
        else:
            get_data_from_host(kc, nc, parse_hosts(node), inst_status,
                               args.only_affected)

        print "Gathering tenant information."
        proceed = False
        for tenant, data in tenant_data.iteritems():
            if args.skip_to_tenant is not None and not proceed:
                if not skip(tenant, args.skip_to_tenant):
                    populate_tenant_users_host(tenant, data)
                    proceed = True
            else:
                populate_tenant_users_host(tenant, data)

    sent = 0

    for uid, user in user_data.iteritems():
        if mailout(uid, user, start_ts, end_ts, args.timezone,
                   args.no_dry_run, args.only_affected, zone):
            sent += 1

    print 'Total instances affected in %s zone: %s' % (zone, total)
    if args.no_dry_run:
        print 'Would send %s notifications' % sent
    else:
        print 'Sent %s notifications' % sent


if __name__ == '__main__':
    main()
