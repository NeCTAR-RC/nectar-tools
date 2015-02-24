#!/usr/bin/env python

import os
import sys
import argparse
import collections

from keystoneclient.v2_0 import client as ks_client
from keystoneclient.exceptions import AuthorizationFailure
from novaclient.v1_1 import client as nova_client
from cinderclient.v1 import client as cinder_client
from cinderclient import exceptions as cinder_exceptions


def all_servers(client):
    servers = []
    marker = None

    while True:
        opts = {"all_tenants": True}
        if marker:
            opts["marker"] = marker

        res = client.servers.list(search_opts=opts)
        if not res:
            break
        servers.extend(res)
        marker = servers[-1].id
    return servers


def audit_instances(az_filter=None):

    nc = get_nova_client()
    cc = get_cinder_client()
    instances = all_servers(nc)
    safe_cleanups = []
    stuck_cleanups = []
    for instance in instances:
        az = getattr(instance, 'OS-EXT-AZ:availability_zone')
        if az_filter and az_filter != az:
            continue
        volumes_attached = getattr(instance,
                                   'os-extended-volumes:volumes_attached')
        volumes_attached = [x['id'] for x in volumes_attached]
        dupes = [x for x, y in collections.Counter(
            volumes_attached).items() if y > 1]
        others = [x for x, y in collections.Counter(
            volumes_attached).items() if y < 2]

        for vol in dupes:
            try:
                v = cc.volumes.get(vol)
            except cinder_exceptions.NotFound:
                msg = "Instance %s has a deleted volume %s - %s" % (
                    instance.id, vol, az)
                safe_cleanups.append((msg, instance, vol))
                continue
            if not v.attachments and v.status == 'available':
                msg = "Instance %s has a dupe available volume %s - %s" % (
                    instance.id, v.id, az)
                safe_cleanups.append((msg, instance, v.id))
            else:
                msg = "Instance %s has a dupe volume %s - %s" % (
                    instance.id, v.id, az)
                stuck_cleanups.append((msg, instance, v.id))
        for vol in others:
            try:
                v = cc.volumes.get(vol)
            except cinder_exceptions.NotFound:
                msg = "Instance %s has a deleted volume %s - %s" % (
                    instance.id, vol, az)
                safe_cleanups.append((msg, instance, vol))
                continue
            if not v.attachments and v.status == 'available':
                msg = "Instance %s has an available volume %s - %s" % (
                    instance.id, v.id, az)
                safe_cleanups.append((msg, instance, v.id))
                continue

    print "========================="
    print "Volumes safe to clean up:"
    print "========================="
    for msg, instance, volume in safe_cleanups:
        print msg
    print
    print "To clean up these BDMs run the following: (NOTE will only work on icehouse compute nodes):"
    print
    for msg, instance, volume in safe_cleanups:
        host = getattr(instance, 'OS-EXT-SRV-ATTR:host')
        print "ssh root@%s nova-manage nectar remove_bdm --instance %s --volume %s" % (host, instance.id, volume)
    print
    print "========================="
    print "Volumes stuck:"
    print "========================="
    print
    print "These BDMs are in a bad state! Manual action required"
    print
    for msg, instance, volume in stuck_cleanups:
        print msg


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

    nc = nova_client.Client(username=auth_username,
                            api_key=auth_password,
                            project_id=auth_tenant,
                            auth_url=auth_url,
                            service_type='compute')
    return nc


def get_cinder_client():

    auth_username = os.environ.get('OS_USERNAME')
    auth_password = os.environ.get('OS_PASSWORD')
    auth_tenant = os.environ.get('OS_TENANT_NAME')
    auth_url = os.environ.get('OS_AUTH_URL')

    cc = cinder_client.Client(username=auth_username,
                              api_key=auth_password,
                              project_id=auth_tenant,
                              auth_url=auth_url)
    return cc


def collect_args():

    parser = argparse.ArgumentParser(argument_default=argparse.SUPPRESS)
    parser.add_argument('-Z', '--az', action='store',
                        help='AZ filter', default=None)
    return parser


if __name__ == '__main__':

    args = collect_args().parse_args()

    az_filter = args.az

    audit_instances(az_filter)
