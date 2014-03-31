#!/usr/bin/env python

import os
import sys
import re
import argparse
import smtplib

from keystoneclient.exceptions import NotFound, AuthorizationFailure
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
    parser.add_argument('-u', '--user-id',
                        help='Specify user to notify')

    return parser


def mailout(kc, nc, users, target_zone, dry_run):

    total_instances_affected = 0

    for user in users:
        try:
            tenant = kc.tenants.get(user.tenantId)
        except NotFound as e: AttributeError:
            print e
        except AttributeError as e:
            print e

        instances = nc.servers.list(
            search_opts={'tenant_id': tenant.id, 'all_tenants': 1})

        instances_in_az = []

        for instance in instances:
            zone = getattr(instance, 'OS-EXT-AZ:availability_zone')
            if zone == target_zone:
                instances_in_az.append(instance)

        if instances_in_az:
            template = render_template(instances_in_az,
                                       tenant.name,
                                       target_zone)
            total_instances_affected += len(instances_in_az)
            if email_pattern.match(user.email) is None:
                print 'Invalid email address, not mailing %s in tenant %s' % \
                    (user.email, tenant.id)
            else:
                print 'Sending email to %s (%s) about %s instances' % \
                    (user.email, user.id, len(instances_in_az))
                if not dry_run:
                    send_email(user.email, template)

    print 'Total instances affected: %s' % total_instances_affected


def render_template(instances, project, zone):

    env = Environment(loader=FileSystemLoader('templates'))
    template = env.get_template('outage-notification.tmpl')
    template = template.render(
        {'instances': instances,
         'project_name': project,
         'target_zone': zone})

    return template


def send_email(recepient, template):

    from email.mime.text import MIMEText
    msg = MIMEText(template, 'plain', 'utf-8')

    msg['From'] = 'NeCTAR Research Cloud <bounces@rc.nectar.org.au>'
    msg['To'] = recepient
    msg['Reply-to'] = 'support@rc.nectar.org.au'
    msg['Subject'] = 'NeCTAR Research Cloud outage affecting your VMs'

    s = smtplib.SMTP('smtp.unimelb.edu.au')

    try:
        s.sendmail(msg['From'], [recepient], msg.as_string())
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


if __name__ == '__main__':

    args = collect_args().parse_args()
    kc = get_keystone_client()
    nc = get_nova_client()

    users = []
    if args.user_id:
        user = kc.users.get(args.user_id)
        users.append(user)
    else:
        users = kc.users.list()

    mailout(kc, nc, users, args.target_zone, args.no_dry_run)
