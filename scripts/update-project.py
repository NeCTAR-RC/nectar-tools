#!/usr/bin/env python

import os
import sys
import argparse

from keystoneclient.v2_0 import client as ks_client
from keystoneclient.exceptions import AuthorizationFailure
from novaclient.v1_1 import client as nova_client
from cinderclient.v1 import client as cinder_client


def update_tenant(kc, id, name, description, allocation_id):

    try:
        tenant = kc.tenants.get(id)
    except:
        print "Couldn't find tenant with the id %s" % id
        return sys.exit(1)
    # Link tenant to allocation
    tenantd = tenant.to_dict()
    kwargs = {}
    if allocation_id:
        kwargs['allocation_id'] = allocation_id
    else:
        if 'allocation_id' not in tenantd:
            print "ERROR: no tenant has no allocation_id."
            return sys.exit(1)

    if name:
        kwargs['name'] = name

    if description:
        kwargs['description'] = description
    else:
        if 'description' not in tenantd:
            print "WARNING: no tenant has no description."

    tenant = kc.tenants.update(tenant.id, **kwargs)

    # TODO update the manager
    # Add roles to tenant manager
    # kc.tenants.add_user(tenant, tenant_manager, tenant_manager_role)
    # kc.tenants.add_user(tenant, tenant_manager, member_role)
    return tenant


def get_cinder_quota(cc, tenant):
    quota = cc.quotas.get(tenant_id=tenant.id)
    return quota


def add_cinder_quota(cc, tenant, gigabytes, volumes):

    kwargs = {}
    if gigabytes:
        kwargs['gigabytes'] = gigabytes
    if volumes:
        kwargs['volumes'] = volumes
        kwargs['snapshots'] = volumes
    # volumes and snapshots are the same as we don't care
    return cc.quotas.update(tenant_id=tenant.id, **kwargs)


def get_nova_quota(nc, tenant):
    quota = nc.quotas.get(tenant_id=tenant.id)
    return quota


def add_nova_quota(nc, tenant, cores, instances, ram):

    kwargs = {}
    if cores:
        kwargs['cores'] = cores
    if ram:
        kwargs['ram'] = ram
    if instances:
        kwargs['instances'] = instances

    quota = nc.quotas.update(tenant_id=tenant.id, **kwargs)
    return quota


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
                        help='Tenant Name')
    parser.add_argument('-d', '--tenant_desc', action='store',
                        help='Tenant description')
    parser.add_argument('-e', '--manager_email', action='store',
                        help='Manager email')
    parser.add_argument('-a', '--allocation-id', action='store', type=int,
                        help='NeCTAR allocation request ID')
    parser.add_argument('-c', '--cores', action="store", type=int,
                        help='Number of cores')
    parser.add_argument('-r', '--ram', action="store", type=int,
                        help='Maximium amount of RAM')
    parser.add_argument('-i', '--instances', action='store',
                        type=int, help='Number of instances')
    parser.add_argument('-v', '--volumes', action='store', default=0, type=int,
                        help='Maximum number of volumes allowed')
    parser.add_argument('-g', '--gigabytes', action='store', default=0, type=int,
                        help='Total gigabytes of volume quota')
    parser.add_argument('tenant_id', action='store',
                        help='The id of the tenant')

    return parser


if __name__ == '__main__':

    args = vars(collect_args().parse_args())
    tenant_id = args['tenant_id']
    name = args.get('tenant_name')
    description = args.get('tenant_desc')
    allocation_id = args.get('allocation_id')
    manager_email = args.get('manager_email')
    cores = args.get('cores')
    instances = args.get('instances')
    ram = args.get('ram')
    volumes = args.get('volumes')
    gigabytes = args.get('gigabytes')

    kc = get_keystone_client()
    nc = get_nova_client()
    cc = get_cinder_client()

    tenant = update_tenant(kc, tenant_id, name, description, allocation_id)

    print """Hi,

Thanks for your continued use of the NeCTAR Research Cloud.  Your
request has been processed and the details are below.  """

    print 'Tenant %s created for allocation %s' % (tenant.id, tenant.allocation_id)
    print 'Name: %s' % tenant.name
    print 'Description: %s' % tenant.description

    print "\n\nCurrent Quota:"
    nquota = get_nova_quota(nc, tenant)
    print '  Instances', nquota.instances
    print '  Cores', nquota.cores
    print '  Ram', nquota.ram

    cquota = get_cinder_quota(cc, tenant)
    print '  Volumes', cquota.volumes
    print '  Snapshots', cquota.snapshots
    print '  Gigabytes', cquota.gigabytes

    nquota = add_nova_quota(nc, tenant, cores, instances, ram)

    cquota = add_cinder_quota(cc, tenant, gigabytes, volumes)

    print "\nNew Quota:"
    nquota = get_nova_quota(nc, tenant)
    print '  Instances', nquota.instances
    print '  Cores', nquota.cores
    print '  Ram', nquota.ram

    cquota = get_cinder_quota(cc, tenant)
    print '  Volumes', cquota.volumes
    print '  Snapshots', cquota.snapshots
    print '  Gigabytes', cquota.gigabytes
    print """
For hints on the next steps to access these resources, add users and launch VMs, please visit
https://support.rc.nectar.org.au/wiki/AllocationsGettingStarted:_Allocations_GettingStarted

Kind Regards,
The NeCTAR Research Cloud Team.
"""
