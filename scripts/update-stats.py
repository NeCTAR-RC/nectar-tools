#!/usr/bin/env python

import sys
import os
import rrdtool
import shutil
import argparse

from keystoneclient.v2_0 import client as ks_client
from keystoneclient.exceptions import AuthorizationFailure
from novaclient.v1_1 import client as nova_client


def collect_args():

    parser = argparse.ArgumentParser(description='Updates used_vcpus and running_vms usage statistics')
    parser.add_argument('-r', '--rrd_dir', metavar='rrd_dir', type=str,
                        required=False,
                        help='directory to output rrds (defaults to /var/www/usage/rrds/)')

    parser.add_argument('-g', '--graph_dir', metavar='graph_dir', type=str,
                        required=False,
                        help='directory to out graphs (defaults to /var/www/usage/)')
    return parser


def update_graphs(rrd_dir, graph_dir):

    time_periods = ['-1h', '-1d', '-1w', '-1m', '-1y', '-2y']

    for tp in time_periods:
        filename = rrd_dir + '/usage' + tp + '.png'
        rrdtool.graph(filename, '--start', tp,
                      '--vertical-label=VMs&Cores',
                      "DEF:cpus=%s/vcpus_used-usage.rrd:vcpus_used:AVERAGE" % rrd_dir,
                      "DEF:vms=%s/running_vms-usage.rrd:running_vms:AVERAGE" % rrd_dir,
                      "AREA:cpus#0099CC:Cores in use",
                      "AREA:vms#003366:Running VMs",
                      "COMMENT:\\n",
                      "GPRINT:vms:AVERAGE:Avg Running VMs\: %3.0lf",
                      "COMMENT:  ",
                      "GPRINT:vms:MAX:Max Running VMs\: %3.0lf\\r",
                      "GPRINT:cpus:AVERAGE:Avg Cores\: %3.0lf",
                      "COMMENT:  ",
                      "GPRINT:cpus:MAX:Max Cores\: %3.0lf\\r",
                      "COMMENT: ")

        # create locally, then copy, so we don't lose the graph temporarily
        if rrd_dir != graph_dir:
            shutil.copy(filename, graph_dir)


def update_rrds(nc, rrd_dir):

    stats = nc.hypervisors.statistics()._info.copy()

    for stat in ['vcpus_used', 'running_vms']:

        value = str(stats[stat])
        filename = rrd_dir + '/' + stat + '-usage.rrd'

        if not os.path.isfile(filename):

            rv = rrdtool.create(filename,
                                "DS:%s:GAUGE:600:0:U" % stat,
                                "RRA:AVERAGE:0.5:1:1051200",
                                "RRA:MAX:0.5:1:1051200")
            if rv:
                print rrdtool.error()
                sys.exit(1)

        rv = rrdtool.update(filename, 'N:' + value)
        if rv:
            print rrdtool.error()
            sys.exit(1)


def get_keystone_client():

    auth_username = os.environ.get('OS_USERNAME')
    auth_password = os.environ.get('OS_PASSWORD')
    auth_tenant = os.environ.get('OS_TENANT_NAME')
    auth_url = os.environ.get('OS_AUTH_URL')

    try:
        kc = ks_client.Client(username=auth_username,
                              password=auth_password,
                              tenant_name=auth_tenant,
                              auth_url=auth_url,
                              insecure=True)
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
                            service_type="compute",
                            insecure=True)
    return nc


if __name__ == '__main__':

    args = collect_args().parse_args()

    if args.rrd_dir:
        rrd_dir = args.rrd_dir
    else:
        rrd_dir = '/var/www/usage/rrds/'

    if args.graph_dir:
        graph_dir = args.graph_dir
    else:
        graph_dir = '/var/www/usage/'

    kc = get_keystone_client()
    token = kc.auth_token
    auth_url = kc.auth_url
    nc = get_nova_client()

    update_rrds(nc, rrd_dir)
    update_graphs(rrd_dir, graph_dir)
