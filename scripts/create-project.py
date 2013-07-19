#!/usr/bin/env python

import os
import sys
import argparse
from keystoneclient.v2_0 import client as keystone_client
from novaclient.v1_1 import client as nova_client
from cinderclient.v2 import client as cinder_client


# Get authentication details from environment
AUTH_USER = os.environ.get('OS_USERNAME', None)
AUTH_PASSWORD = os.environ.get('OS_PASSWORD', None)
AUTH_TENANT_NAME = os.environ.get('OS_TENANT_NAME', None)
AUTH_URL = os.environ.get('OS_AUTH_URL', None)


def add_tenant(name, description, manager_email):

    # Create keystone client
    ksclient = keystone_client.Client(username=AUTH_USER,
                                      password=AUTH_PASSWORD,
                                      tenant_name=AUTH_TENANT_NAME,
                                      auth_url=AUTH_URL)

    try:
        tenant_manager = ksclient.users.find(name=manager_email)
    except:
        print "Couldn't find a unique user with that email"
    return sys.exit(1)

    try:
        tenant_manager_role = ksclient.roles.find(name='TenantManager')
        member_role = ksclient.roles.find(name='Member')
    except:
        print "Couldn't find roles"
        return sys.exit(1)

    # Create tenant
    tenant = ksclient.tenants.create(name, description)

    # Add roles to tenant manager
    ksclient.tenants.add_user(tenant, tenant_manager, tenant_manager_role)
    ksclient.tenants.add_user(tenant, tenant_manager, member_role)

    return tenant.id


def add_cinder_quota(tenant_id, gigabytes, volumes):
    cclient = cinder_client.Client(username=AUTH_USER,
                                   api_key=AUTH_PASSWORD,
                                   project_id=AUTH_TENANT_NAME,
                                   auth_url=AUTH_URL)
    # volumes and snapshots the same as we don't care
    cclient.quotas.update(tenant_id=tenant_id,
                          gigabytes=gigabytes,
                          volumes=volumes,
                          snapshots=volumes)


def add_nova_quota(tenant_id, cores, instances, ram):
    nclient = nova_client.Client(username=AUTH_USER,
                                 api_key=AUTH_PASSWORD,
                                 project_id=AUTH_TENANT_NAME,
                                 auth_url=AUTH_URL)

    nclient.quotas.update(tenant_id=tenant_id,
                          ram=ram,
                          instances=instances,
                          cores=cores)


def main():

    for auth_variable in (AUTH_USER, AUTH_PASSWORD,
                          AUTH_TENANT_NAME, AUTH_URL):
        if not auth_variable:
            print "Missing environment variable %s" % auth_variable
            return sys.exit(1)

    args = get_args()
    name = args.t
    description = args.d
    manager_email = args.e
    cores = args.c
    instances = args.i
    ram = cores * 4096
    if 'v' in args:
        volumes = args.v
    if 'g' in args:
        gigabytes = args.g

    tenant_id = add_tenant(name, description, manager_email)
    add_nova_quota(tenant_id, cores, instances, ram)
    if gigabytes and volumes:
        add_cinder_quota(tenant_id, gigabytes, volumes)
    sys.exit(0)


def get_args():
    parser = argparse.ArgumentParser(argument_default=argparse.SUPPRESS)
    parser.add_argument('-t', '-tenant_name', action='store',
                        required=True, help='Tenant Name')
    parser.add_argument('-d', '-tenant_desc', action='store',
                        required=True, help='Tenant description')
    parser.add_argument('-e', '-manager_email', action='store',
                        required=True, help='Manager email')
    parser.add_argument('-c', '-cores', action="store", type=int,
                        required=True, help='Number or cores')
    parser.add_argument('-i', '-instances', action='store',
                        required=True, type=int, help='Number of instances')
    parser.add_argument('-v', '-volumes', action='store',
                        required=False, type=int, help='Number of volumes')
    parser.add_argument('-g', '-gigabytes', action='store',
                        required=False, type=int, help='Number of gigabytes')

    return parser.parse_args()

if __name__ == '__main__':
    main()
