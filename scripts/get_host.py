#!/usr/bin/env python
import os

import sys
import argparse
import re
import prettytable
import textwrap
from novaclient.v1_1 import client
from novaclient.exceptions import ClientException


# Get authentication details from environment
AUTH_USER = os.environ.get('OS_USERNAME', None)
AUTH_PASSWORD = os.environ.get('OS_PASSWORD', None)
AUTH_TENANT_NAME = os.environ.get('OS_TENANT_NAME', None)
AUTH_URL = os.environ.get('OS_AUTH_URL', None)


def get_host(name):

    query = re.compile(r'%s' % name)
    nclient = client.Client(username=AUTH_USER,
                                 api_key=AUTH_PASSWORD,
                                 project_id=AUTH_TENANT_NAME,
                                 auth_url=AUTH_URL)
    try:
        all_host = nclient.hypervisors.list(False)

        for i in all_host:
            if query.search(i.hypervisor_hostname):
                data_name = i.manager.get(i.id)._info.copy()
                break
            else:
                data_name = None

        return data_name

    except ClientException, e:
        print "Error %r" % e


def printData(data_name):
    new_data = {}
    new_data['1.host'] = data_name.get('hypervisor_hostname')
    new_data['2.vcpus'] = data_name.get('vcpus')
    new_data['3.vcpus_used'] = data_name.get('vcpus_used')
    free_cpu = data_name.get('vcpus') - data_name.get('vcpus_used')
    new_data['4.vcpus_free'] = free_cpu
    new_data['5.memory_mb'] = data_name.get('memory_mb')
    new_data['6.memory_mb_used'] = data_name.get('memory_mb_used')
    new_data['7.free_ram_mb'] = data_name.get('free_ram_mb')
    new_data['8.Number of VMs'] = data_name.get('running_vms')

    return new_data


def printPretty(data, dict_property="Property", wrap=0):
    pt = prettytable.PrettyTable([dict_property, 'Value'], caching=False)
    pt.align = 'l'
    for k, v in sorted(data.iteritems()):
        if isinstance(v, dict):
            v = str(v)
        if wrap > 0:
            v = textwrap.fill(str(v), wrap)
        if v and isinstance(v, basestring) and r'\n' in v:
            lines = v.strip().split(r'\n')
            col1 = k
            for line in lines:
                pt.add_row([col1, line])
                col1 = ''
        else:
            pt.add_row([k, v])
    print pt.get_string()


def main():

    for auth_variable in (AUTH_USER, AUTH_PASSWORD,
                          AUTH_TENANT_NAME, AUTH_URL):
        if not auth_variable:
            print "Missing environment variable %s" % auth_variable
            return sys.exit(1)

    args = get_args()
    host_data = get_host(args.n)
    if host_data is not None:
        if args.v is True:
            printPretty(host_data, wrap=70)
        else:
            printPretty(printData(host_data), wrap=50)

    else:
        print "Node %s not found" % args.n
        return sys.exit(1)


def get_args():
    parser = argparse.ArgumentParser(argument_default=argparse.SUPPRESS)
    parser.add_argument('-n', '-node_name', action='store',
                        required=True, help='Node Name')
    parser.add_argument('-v', action='store_true', default='False',
                         help='Full Details')

    return parser.parse_args()

if __name__ == '__main__':
    main()
