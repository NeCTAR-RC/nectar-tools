#!/usr/bin/env python
import os

import sys
import argparse
import re
import prettytable
import textwrap
from novaclient.v1_1 import client
from novaclient.exceptions import ClientException
import novaclient


# Get authentication details from environment
AUTH_USER = os.environ.get('OS_USERNAME', None)
AUTH_PASSWORD = os.environ.get('OS_PASSWORD', None)
AUTH_TENANT_NAME = os.environ.get('OS_TENANT_NAME', None)
AUTH_URL = os.environ.get('OS_AUTH_URL', None)


def conn():
    nclient = client.Client(username=AUTH_USER,
                                 api_key=AUTH_PASSWORD,
                                 project_id=AUTH_TENANT_NAME,
                                 auth_url=AUTH_URL)

    return nclient


def get_agg(client):
    agg_detail = {}

    try:
        for i in client.aggregates.list():
            agg_detail[i.name] = i.availability_zone

        return agg_detail

    except ClientException, e:
        print "Error %r" % e


def getDetails(client, agg, zone):
    stro = r'(\s|^|$)'
    try:
        zone_info = []
        agg_info = []
        agg_list = client.aggregates.list()
        for i in agg_list:
            if i.availability_zone is not None:
                agg_info.append(i)

        for i in agg_info:
                if re.match(stro + agg + stro, i.name, flags=re.IGNORECASE):
                        if re.match(stro + zone + stro,
                                    i.availability_zone, flags=re.IGNORECASE):
                            zone_info.append(i._info)

        if len(zone_info) > 0:
            val = (az for az in zone_info
                   if az['availability_zone'] == zone).next()
            return val
        else:
            return None

    except ClientException, e:
        print "Error %r" % e


def getResource(client, nodes):

    host = nodes.get('4.Hosts')
    node_info = []
    t_cpu = u_cpu = t_m = u_m = r_vm = 0
    for i in host:
        hz = re.compile(r'%s' % i)
        for h in client.hypervisors.list(False):
            try:
                if hz.search(h.hypervisor_hostname):
                    node_info.append(h.manager.get(h.id)._info.copy())
            except novaclient.exceptions.BadRequest:
                pass

    for r in node_info:
        t_cpu += r.get('vcpus')
        u_cpu += r.get('vcpus_used')
        t_m += r.get('memory_mb')
        u_m += r.get('memory_mb_used')
        r_vm += r.get('running_vms')

    nodes['5.total_cpu'] = t_cpu
    nodes['6.used_cpu'] = u_cpu
    nodes['7.total_mem'] = (t_m / 1024)
    nodes['8.used_mem'] = (u_m / 1024)
    nodes['9.total_vm'] = r_vm

    return nodes


def printData(data):
    print_data = {}

    print_data['1.Name'] = data.get('name')
    print_data['2.Az'] = data.get('availability_zone')
    print_data['3.Count'] = len(data.get('hosts'))
    print_data['4.Hosts'] = data.get('hosts')

    return print_data


def printPretty(data, wrap=0, dict_property=None, val=None):
    if dict_property == None:
        dict_property = 'Property'
    if val == None:
        val = 'Value'
    pt = prettytable.PrettyTable([dict_property, val], caching=False)
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
    client = conn()
    if args.func is 'list_detail':
        host_data = get_agg(client)
        printPretty(host_data, wrap=70, dict_property='Aggregate', val='Zone')
    elif args.func is 'show_detail':
        agg = getDetails(client, args.a, args.z)
        if agg != None:
            if args.d is True:
                detail_ = getResource(client, printData(agg))
                printPretty(detail_, wrap=70)
            else:
                printPretty(printData(agg), wrap=50)
        else:
            print "None found from aggregate:%s, zone:%s" % (args.a, args.z)


def get_args():
    parser = argparse.ArgumentParser(argument_default=argparse.SUPPRESS)
    subparsers = parser.add_subparsers()
    list_ = subparsers.add_parser('list-agg', help='List Available Aggregates')
    list_.set_defaults(func='list_detail')
    show_ = subparsers.add_parser('show-agg', help='Show An Aggregate Detail')
    show_.add_argument('-a', action='store', required=True,
                        help='aggregate name')
    show_.add_argument('-z', action='store', required=True,
                        help='zone name')
    show_.add_argument('-d', action='store_true', default='False',
                         help='In details, show resources count')
    show_.set_defaults(func='show_detail')

    return parser.parse_args()

if __name__ == '__main__':
    main()
