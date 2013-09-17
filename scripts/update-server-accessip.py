#!/usr/bin/env python

import os
import argparse
from itertools import chain

from novaclient.v1_1 import client as nova_client
from novaclient import base
from keystoneclient.v2_0 import client as ks_client


def get_keystone_client():

    auth_username = os.environ.get('OS_USERNAME')
    auth_password = os.environ.get('OS_PASSWORD')
    auth_tenant = os.environ.get('OS_TENANT_NAME')
    auth_url = os.environ.get('OS_AUTH_URL')

    kc = ks_client.Client(username=auth_username,
                          password=auth_password,
                          tenant_name=auth_tenant,
                          auth_url=auth_url,
                          insecure=True)
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

    parser = argparse.ArgumentParser(
        description='Update virtual machines access ip address.')
    args = parser.parse_args()

    kc = get_keystone_client()
    token = kc.auth_token
    auth_url = kc.auth_url
    nc = get_nova_client()
    for server in nc.servers.list(search_opts={"all_tenants": 1}):

        if server.accessIPv4:
            # print "Skipped: %s" % server.id
            continue
        addresses = [addrs for zone, addrs in server.addresses.items()
                     if zone != 'qld-storage']
        addresses = [addr for addr in chain(*addresses)
                     if addr['version'] == 4]
        if not addresses:
            print "No address for: %s" % server.id
            print server.addresses
            continue

        address = addresses[0]['addr']
        print "Update address from %s to %s" % (server.accessIPv4, address)

        body = {
            "server": {
                "accessIPv4": address,
            },
        }
        nc.servers._update("/servers/%s" % base.getid(server),
                           body, "server")
