#!/usr/bin/env python

import sys
import os
import argparse
from operator import attrgetter

from keystoneclient.v2_0 import client as ks_client
from keystoneclient.exceptions import AuthorizationFailure
import glanceclient as glance_client
from novaclient.v1_1 import client as nova_client
import swiftclient

from jinja2 import Environment, FileSystemLoader


def collect_args():

    parser = argparse.ArgumentParser(description='Deletes a Tenant')
    parser.add_argument('-u', '--user', metavar='user', type=str,
        required=False,
        help='user to delete')
    parser.add_argument('-t', '--tenant', metavar='tenant', type=str,
        required=True,
        help='tenant to delete')
    parser.add_argument('-y', '--no-dry-run', action='store_true',
        required=False,
        help='Perform the actual actions, default is to only show what would happen')
    parser.add_argument('-1', '--stage1', action='store_true',
                        required=False,
                        help='Stage 1 Nag')
    parser.add_argument('-2', '--stage2', action='store_true',
                        required=False,
                        help='Stage 2 Termination')
    parser.add_argument('-3', '--stage3', action='store_true',
                        required=False,
                        help='Stage 3 Archive')

    return parser

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
                            service_type="compute")
    return nc


def stage2_images(client, nova_client, tenant_id):
    print "===================================="
    print "=========  Glance Data  ============"
    print "===================================="
    raw_images = list(client.images.list(**{"owner": tenant_id}))
    images = []
    if raw_images:
        for i in raw_images:
            #Seems like the glance client returns all images user can see so this is needed
            if i.owner == tenant_id:
                images.append(i)
                instances = nova_client.servers.list(search_opts={'image': i.id, 'all_tenants': 1})
                print "%s public: %s, instances: %s" % (i.id, i.is_public, len(instances))
    else:
        print "No images"
    #TODO Option to delete all images that have no running instances. What if instances are in same tenant and will be deleted though?


def instance_suspend(instance, dry_run=True):
    if instance.status == 'SUSPENDED':
        print "%s - already suspended" % instance.id
    else:
        if dry_run:
            print "%s - would suspend this instance" % instance.id
        else:
            print "%s - suspending" % instance.id
            instance.suspend()


def instance_lock(instance, dry_run=True):
    if dry_run:
        print "%s - would lock this instance" % instance.id
    else:
        print "%s - locking" % instance.id
        instance.lock()


def stage2_instances(client, tenant_id, dry_run=True):
    print "===================================="
    print "=========  Nova Data  =============="
    print "===================================="
    instances = client.servers.list(search_opts={'tenant_id': tenant_id, 'all_tenants': 1})
    if instances:
        for i in instances:
            instance_suspend(instance=i, dry_run=dry_run)
            instance_lock(instance=i, dry_run=dry_run)

    # archive? (copy to swift?) (2
    # terminate (2

    print "%d instances processed" % len(instances)

    #TODO Option to Archive all data
    #TODO Option to delete all data


def stage2_swift(auth_url, token, swift_url, dry_run=True):
    print "===================================="
    print "=========  Swift Data  ============="
    print "===================================="
    account_details = swiftclient.head_account(swift_url, token)
    print "Data used : %s Bytes" % account_details['x-account-bytes-used']
    print "Containers: %s" % account_details['x-account-container-count']
    print "Objects   : %s" % account_details['x-account-object-count']

    #TODO Option to Archive all data
    #TODO Option to delete all data


def stage3_keystone(client, tenant_id, dry_run=True):
    print "===================================="
    print "===== Keystone Data (tenant) ======="
    print "===================================="
    users = client.tenants.list_users(tenant_id)
    print "Users: %s" % " ".join(map(attrgetter("id"), users))
    if not dry_run:
        print "Deleting tenant %s" % tenant_id
        client.tenant.delete(tenant_id)


def stage3_keystone_user(client, user_id, dry_run=True):
    print "===================================="
    print "====== Keystone Data (user) ========"
    print "===================================="
    print "Deleting user %s" % user_id
    if not dry_run:
        print "Deleting user %s" % user_id
        client.user.delete(user_id)


def render_email():
    env = Environment(loader=FileSystemLoader('templates'))
    template = env.get_template('first-notification.tmpl')
    template.render()


if __name__ == '__main__':

    args = collect_args().parse_args()
    user_id = args.user
    tenant_id = args.tenant

    if args.no_dry_run:
        dry_run = False
    else:
        dry_run = True

    kc = get_keystone_client()
    token = kc.auth_token
    auth_url = kc.auth_url

    image_endpoint = kc.service_catalog.url_for(service_type='image')
    gc = glance_client.Client('1', image_endpoint, token=token)

    nc = get_nova_client()

    swift_url = kc.service_catalog.url_for(service_type='object-store', endpoint_type='adminURL') + 'AUTH_' + tenant_id

    if args.stage1:
        print "Would send email"
        #render_email()
        #exit
    if args.stage2:
        stage2_images(gc, nc, tenant_id)
        stage2_instances(nc, tenant_id, dry_run)
        stage2_swift(auth_url, token, swift_url + swift_auth, dry_run)
    if args.stage3:
        if tenant_id:
            stage3_keystone(kc, tenant_id)
        if user_id:
            stage3_keystone_user(kc, tenant_id)
