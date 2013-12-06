#!/usr/bin/env python

import argparse
import auth


def get_args():

    parser = argparse.ArgumentParser(argument_default=argparse.SUPPRESS)
    parser.add_argument('-t', '-tenant_name', action='store',
                        required=True, help='Tenant Name')

    return parser.parse_args()


if __name__ == '__main__':

    kc = auth.get_keystone_client()
    args = get_args()
    name = args.t

    print name
    print "==============="

    manager_role = kc.roles.find(name='TenantManager')
    tenant = kc.tenants.find(name=name)
    tenant_managers = []
    members = []
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
