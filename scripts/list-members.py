#!/usr/bin/env python

import os
import sys
import argparse
from keystoneclient.v2_0 import client as ks_client
from keystoneclient import exceptions as ks_exceptions

# Get authentication details from environment
AUTH_USER = os.environ.get('OS_USERNAME', None)
AUTH_PASSWORD = os.environ.get('OS_PASSWORD', None)
AUTH_TENANT_NAME = os.environ.get('OS_TENANT_NAME', None)
AUTH_URL = os.environ.get('OS_AUTH_URL', None)


def main():

    for auth_variable in (AUTH_USER, AUTH_PASSWORD,
                          AUTH_TENANT_NAME, AUTH_URL):
        if not auth_variable:
            print "Missing environment variable %s" % auth_variable
            return sys.exit(1)

    args = get_args()

    tenant_name = tenant_id = tenant = None

    if 'tn' in args:
        tenant_name = args.tn

    if 'ti' in args:
        tenant_id = args.ti

    ksclient = ks_client.Client(username=AUTH_USER,
                                password=AUTH_PASSWORD,
                                tenant_name=AUTH_TENANT_NAME,
                                auth_url=AUTH_URL)

    try:
        if tenant_name is not None:
            tenant = ksclient.tenants.find(name=tenant_name)
        if tenant_id is not None:
            tenant = ksclient.tenants.find(id=tenant_id)
    except ks_exceptions.NotFound:
        if not tenant:
            print "Tenant not found."
            sys.exit(1)
    print "Tenant name: %s" % tenant.name
    print "Tenant ID:   %s" % tenant.id
    print "==============="
    tenant_managers = []
    members = []
    manager_role = ksclient.roles.find(name='TenantManager')
    for user in tenant.list_users():
        if manager_role in user.list_roles(tenant=tenant):
            tenant_managers.append(user)
        else:
            members.append(user)

    def print_users(users):
        for u in users:
            full_name = getattr(u, 'full_name', None)
            if full_name:
                print full_name, u.name
            else:
                print u.name

    print "Tenant Managers"
    print "---------------"
    print_users(tenant_managers)
    print "---------------"
    print "Members"
    print "---------------"
    print_users(members)

    sys.exit(0)


def get_args():
    parser = argparse.ArgumentParser(argument_default=argparse.SUPPRESS)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-tn', '-tenant-name', action='store',
                       help='Tenant Name')
    group.add_argument('-ti', '-tenant-id', action='store',
                       help='Tenant ID')
    return parser.parse_args()

if __name__ == '__main__':
    main()
