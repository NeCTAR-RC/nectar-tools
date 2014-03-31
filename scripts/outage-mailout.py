#!/usr/bin/env python

import sys
import argparse
import auth
import smtplib
from keystoneclient.exceptions import NotFound
from jinja2 import Environment, FileSystemLoader


def collect_args():

    parser = argparse.ArgumentParser(description='Notifies user of upcoming outage')
    parser.add_argument('-y', '--no-dry-run', action='store_false',
                   default=True,
                   help='Perform the actual actions, default is to only show what would happen')
    parser.add_argument('-z', '--target-zone',
                   required=True,
                   help='Specify availability zone to notify')
    parser.add_argument('-u', '--user-id',
                   help='Specify user to notify')

    return parser


def mailout(kc, nc, users, target_zone, dry_run):

    for user in users:
        try:
            tenant = kc.tenants.get(user.tenantId)
        except (NotFound, AttributeError):
            continue

        instances = nc.servers.list(search_opts={'tenant_id': tenant.id,
                                                    'all_tenants': 1})
        match = []
        if instances:
            for instance in instances:
                zone = getattr(instance, 'OS-EXT-AZ:availability_zone')
                if zone == target_zone:
                    match.append(instance)

        if match:
            template = render_template(match, tenant.name, target_zone)
            print 'Sending email to', user.email, user.id
            if not dry_run:
                send_email(user.email, template)


def render_template(instances, project, zone):

    env = Environment(loader=FileSystemLoader('templates'))
    template = env.get_template('outage-notification.tmpl')
    template = template.render({ "instances": instances,
                              "project_name": project,
                              "target_zone": zone})
    return template


def send_email(recepient, template):

    from email.mime.text import MIMEText
    msg = MIMEText(template, 'plain', 'utf-8')

    msg['From'] = 'NeCTAR RC <rc-rt-bounces@melbourne.nectar.org.au>'
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


if __name__ == '__main__':

    args = collect_args().parse_args()
    kc = auth.get_keystone_client()
    nc = auth.get_nova_client()

    users = []
    if args.user_id:
        user = kc.users.get(args.user_id)
        users.append(user)
    else:
        users = kc.users.list()

    mailout(kc, nc, users, args.target_zone, args.no_dry_run)


