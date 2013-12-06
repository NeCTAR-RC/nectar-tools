#!/usr/bin/env python

import argparse
from itertools import chain
import auth


if __name__ == '__main__':

    parser = argparse.ArgumentParser(
        description='Update virtual machines access ip address.')
    args = parser.parse_args()

    kc = auth.get_keystone_client()
    token = kc.auth_token
    auth_url = kc.auth_url
    nc = auth.get_nova_client()
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
