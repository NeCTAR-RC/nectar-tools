#!/usr/bin/env python

import os
import sys
import argparse

from keystoneclient.v2_0 import client as ks_client
from keystoneclient.exceptions import AuthorizationFailure
from novaclient.v1_1 import client as nova_client
from cinderclient.v1 import client as cinder_client


def add_tenant(kc, name, description, manager_email, allocation_id):

    try:
        tenant_manager = kc.users.find(name=manager_email)
    except:
        print "Couldn't find a unique user with that email"
        return sys.exit(1)

    try:
        tenant_manager_role = kc.roles.find(name='TenantManager')
        member_role = kc.roles.find(name='Member')
    except:
        print "Couldn't find roles"
        return sys.exit(1)

    # Create tenant
    tenant = kc.tenants.create(name, description)

    # Link tenant to allocation
    kwargs = {'allocation_id': allocation_id}
    kc.tenants.update(tenant.id, **kwargs)

    # Add roles to tenant manager
    kc.tenants.add_user(tenant, tenant_manager, tenant_manager_role)
    kc.tenants.add_user(tenant, tenant_manager, member_role)

    print 'Tenant %s created for allocation %s' % (tenant.id, allocation_id)
    print 'Name: %s' % name
    print 'Email: %s' % manager_email
    print 'Description: %s' % description

    return tenant.id


def add_cinder_quota(cc, tenant_id, gigabytes, volumes):

    snapshots = volumes
    # volumes and snapshots are the same as we don't care
    cc.quotas.update(tenant_id=tenant_id,
                     gigabytes=gigabytes,
                     volumes=volumes,
                     snapshots=snapshots)
    print 'cinder quota updated (gigabytes=%s, volumes=%s, snapshots=%s)' \
        % (gigabytes, volumes, snapshots)


def add_nova_quota(nc, tenant_id, cores, instances, ram):

    nc.quotas.update(tenant_id=tenant_id,
                     ram=ram,
                     instances=instances,
                     cores=cores)
    print 'nova quota updated (instances=%s, cores=%s, ram=%s)' \
          % (instances, cores, ram)


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
    parser.add_argument('-t', '--tenant_name', action='store',
                        required=True, help='Tenant Name')
    parser.add_argument('-d', '--tenant_desc', action='store',
                        required=True, help='Tenant description')
    parser.add_argument('-e', '--manager_email', action='store',
                        required=True, help='Manager email')
    parser.add_argument('-a', '--allocation-id', action='store',
                        required=True, type=int,
                        help='NeCTAR allocation request ID')
    parser.add_argument('-c', '--cores', action="store", type=int,
                        required=True, help='Number of cores')
    parser.add_argument('-r', '--ram', action="store", type=int,
                        required=False, help='Maximium amount of RAM')
    parser.add_argument('-i', '--instances', action='store',
                        required=True, type=int, help='Number of instances')
    parser.add_argument('-v', '--volumes', action='store', default=0,
                        required=False, type=int,
                        help='Maximum number of volumes allowed')
    parser.add_argument('-g', '--gigabytes', action='store', default=0,
                        required=False, type=int,
                        help='Total gigabytes of volume quota')

    return parser


if __name__ == '__main__':

    args = collect_args().parse_args()

    name = args.tenant_name
    description = args.tenant_desc
    manager_email = args.manager_email
    cores = args.cores
    instances = args.instances
    if 'ram' in args:
        ram = args.ram
    else:
        ram = cores * 4096
    volumes = args.volumes
    gigabytes = args.gigabytes

    kc = get_keystone_client()
    nc = get_nova_client()
    cc = get_cinder_client()

    allocation_id = args.allocation_id

    tenant_id = add_tenant(kc, name, description, manager_email, allocation_id)
    add_nova_quota(nc, tenant_id, cores, instances, ram)

    if gigabytes != 0 or volumes != 0:
        add_cinder_quota(cc, tenant_id, gigabytes, volumes)
