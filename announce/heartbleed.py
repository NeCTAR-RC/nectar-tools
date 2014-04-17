#!/usr/bin/env python

import os
import sys
import re
import argparse
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from keystoneclient.exceptions import AuthorizationFailure
from keystoneclient.v2_0 import client as ks_client
from novaclient.v1_1 import client as nova_client

from jinja2 import Environment, FileSystemLoader

email_pattern = re.compile('([\w\-\.\']+@(\w[\w\-]+\.)+[\w\-]+)')


def collect_args():

    parser = argparse.ArgumentParser(
        description='Notifies users of an upcoming outage')

    parser.add_argument('-y', '--no-dry-run', action='store_false',
                        default=True,
                        help='Perform the actual actions, \
                              default is to only show what would happen')
    parser.add_argument('-u', '--uuid',
                        required=True,
                        help='Affected instance uuid')
    parser.add_argument('-p', '--port',
                        required=True,
                        help='Affected port')
    parser.add_argument('-s', '--smtp_server',
                        default='127.0.0.1',
                        help='SMTP server to use, defaults to localhost')
    return parser


def check_valid_email(email, name, enabled):

    if not enabled:
        print 'User %s: user disabled, not sending email => %s' % (name, email)
        return False

    if email is None:
        print 'User %s: no email address' % name
        return False

    if email_pattern.match(email) is None:
        print 'User %s: invalid email address => %s' % (name, email)
        return False

    return True


def mailout(user, data, dry_run):

    email = user.email
    name = user.name
    enabled = user.enabled

    subject = 'Heartbleed OpenSSL Vulnerability affecting your VM'

    text, html = render_templates(subject, data)

    if not check_valid_email(email, name, enabled):
        return

    msg = 'User %s: sending email to %s' % (name, email)

    if dry_run:
        msg = msg + ' [DRY RUN]'
        print msg
    else:
        print msg
        sys.stdout.flush()
        send_email(email, subject, text, html)


def render_templates(subject, data):

    env = Environment(loader=FileSystemLoader('templates'))

    text = env.get_template('heartbleed.tmpl')
    text = text.render({'server': data})

    html = env.get_template('heartbleed.html.tmpl')
    html = html.render({'title': subject, 'server': data})

    return text, html


def send_email(recipient, subject, text, html):

    global smtp_server

    msg = MIMEMultipart('alternative')
    msg.attach(MIMEText(text, 'plain', 'utf-8'))
    if html is not None:
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

    data = {}

    args = collect_args().parse_args()
    kc = get_keystone_client()
    nc = get_nova_client()

    uuid = args.uuid
    port = args.port

    smtp_server = args.smtp_server

    server = nc.servers.get(uuid)
    tenant_id = server.tenant_id
    tenant = kc.tenants.get(tenant_id)
    project = tenant.name
    users = kc.users.list(tenant_id)
    zone = getattr(server, 'OS-EXT-AZ:availability_zone')

    data['accessIPv4'] = server.accessIPv4
    data['id'] = uuid
    data['port'] = port
    data['name'] = server.name
    data['project'] = project
    data['zone'] = zone

    for user in users:
        mailout(user, data, args.no_dry_run)
