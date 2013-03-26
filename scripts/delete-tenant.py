#!/usr/bin/env python

import sys
import os
import argparse

from keystoneclient.v2_0 import client as ks_client
import glanceclient as glance_client
from novaclient.v1_1 import client as nova_client
import swiftclient

def collect_args():

  parser = argparse.ArgumentParser(description='Deletes a Tenant')
  parser.add_argument('--user', metavar='user', type=str,
        required=False,
        help='user to delete')
  parser.add_argument('--tenant', metavar='tenant', type=str,
        required=True,
        help='tenant to delete')

  return parser


def process_images(client, nova_client, tenant_id):
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


def process_instances(client, tenant_id):
    print "===================================="
    print "=========  Nova Data  =============="
    print "===================================="
    instances = client.servers.list(search_opts={'tenant_id': tenant_id, 'all_tenants': 1})
    if instances:
        for i in instances:
            print i.id

    print "%d instances" % len(instances)
    #TODO Option to Archive all data
    #TODO Option to delete all data


def process_swift(auth_url, token, swift_url):
    print "===================================="
    print "=========  Swift Data  ============="
    print "===================================="
    account_details = swiftclient.head_account(swift_url, token)
    print "Data used : %s Bytes" % account_details['x-account-bytes-used']
    print "Containers: %s" % account_details['x-account-container-count']
    print "Objects   : %s" % account_details['x-account-object-count']

    #TODO Option to Archive all data
    #TODO Option to delete all data

def process_keystone():
    #TODO Remove all users from the tenant


if __name__ == '__main__':
  args = collect_args().parse_args()
  user_id = args.user
  tenant_id = args.tenant

  auth_username = os.environ.get('OS_USERNAME')
  auth_password = os.environ.get('OS_PASSWORD')
  auth_tenant = os.environ.get('OS_TENANT_NAME')
  auth_url = os.environ.get('OS_AUTH_URL')

  ks_client = ks_client.Client(username=auth_username,
                              password=auth_password,
                              tenant_name=auth_tenant,
                              auth_url=auth_url)

  token = ks_client.auth_token
  image_endpoint = ks_client.service_catalog.url_for(service_type='image')

  gc = glance_client.Client('1', image_endpoint, token=token)
  nc = nova_client.Client(auth_username,
                               auth_password,
                               auth_tenant,
                               auth_url,
                               service_type="compute")

  swift_url = ks_client.service_catalog.url_for(service_type='object-store', endpoint_type='adminURL') + 'AUTH_' + tenant_id

  process_images(gc, nc, tenant_id)
  process_instances(nc, tenant_id)
  process_swift(auth_url, token, swift_url)
