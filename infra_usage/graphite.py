#!/usr/bin/env python
import time
import socket
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from collections import defaultdict

from util_report import processConfig
from util_nova import createNovaConnection
from util_keystone import createConnection as createKeystoneConnection

DEBUG = False


def send_metric(sock, metric, value, now):
    message = ('%s %0.2f %d\n' %
               (metric, value, now))
    if not DEBUG:
        sock.sendall(message)
    else:
        print message
    return message


def send_graphite_nectar(sock, metric, value, time):
    return send_metric(sock, "%s" % metric,  value, time)


def send_graphite_cell(sock, cell, metric, value, time):
    return send_metric(sock, "%s.%s" % (cell, metric),
                       value, time)

def send_graphite_domain(sock, cell, domain, metric, value, time):
    return send_metric(sock, "%s.domains.%s.%s" % (cell, domain, metric),
                       value, time)

flavor = {}


def all_servers(client):
    servers = []
    marker = None

    while True:
        opts = {"all_tenants": True}
        if marker:
            opts["marker"] = marker
        res = client.servers.list(search_opts=opts)
        if not res:
            break
        servers.extend(res)
        marker = servers[-1].id
    return servers


def all_flavors(client, servers):
    flavor_ids = set()
    for server in servers:
        flavor_ids.add(server.flavor['id'])
    flavors = {}
    for flavor_id in flavor_ids:
        flavor = client.flavors.get(flavor_id)
        flavors[flavor.id] = {'disk': flavor.disk,
                                'ram': flavor.ram,
                                'vcpus': flavor.vcpus}
    return flavors


def server_metrics(servers, flavors):
    metrics = defaultdict(int)
    metrics['total_instances'] = len(servers)
    for server in servers:
        metrics['used_vcpus'] += flavors[server.flavor['id']]['vcpus']
        metrics['used_memory'] += flavors[server.flavor['id']]['ram']
        metrics['used_disk'] += flavors[server.flavor['id']]['disk']
    return metrics


def main(host, port, cell):
    username = processConfig('production', 'user')
    key = processConfig('production', 'passwd')
    tenant_name = processConfig('production', 'name')
    url = processConfig('production', 'url')
    zone = processConfig('config', 'zone')
    client = createNovaConnection(username, key, tenant_name, url)
    kclient = createKeystoneConnection(username, key, tenant_name, url)
    users = {}
    for user in kclient.users.list():
        if not user.email:
            continue
        email = user.email.split('@')[-1]
        if email.endswith('.edu.au'):
            email = '_'.join(email.split('.')[-3:])
        else:
            email = email.replace('.', '_')
        users[user.id] = email

    servers = all_servers(client)
    flavors = all_flavors(client, servers)
    servers_by_cell = defaultdict(list)
    servers_by_cell_by_domain = defaultdict(lambda: defaultdict(list))

    for server in servers:
        cell = getattr(server, 'OS-EXT-AZ:availability_zone')
        servers_by_cell[cell].append(server)
        servers_by_cell_by_domain[cell][users[server.user_id]].append(server)

    if DEBUG:
        sock = None
    else:
        sock = socket.socket()
        sock.connect((host, port))
    now = int(time.time())
    for metric, value in server_metrics(servers, flavors).items():
        send_graphite_nectar(sock, metric, value, now)

    for zone, servers in servers_by_cell.items():
        sock = socket.socket()
        sock.connect((host, port))
        for metric, value in server_metrics(servers, flavors).items():
            send_graphite_cell(sock, zone, metric, value, now)
    for zone, items in servers_by_cell_by_domain.items():
        sock = socket.socket()
        sock.connect((host, port))
        for domain, servers in items.items():
            for metric, value in server_metrics(servers, flavors).items():
                if metric not in ['used_vcpus']:
                    continue
                send_graphite_domain(sock, zone, domain, metric, value, now)

if __name__ == '__main__':
    parser = ArgumentParser(formatter_class=ArgumentDefaultsHelpFormatter)
    parser.add_argument('--cell', action='store',
                        help='specify 1 cell name to overide, e.g. -a np')
    parser.add_argument('--host', required=True,
                        help='Carbon Host.')
    parser.add_argument('--debug', required=False, action='store_true',
                        help='Print output instead of sending to Graphite.')
    parser.add_argument('--port', default=2003, type=int,
                        required=False,
                        help='Carbon Port.')
    args = parser.parse_args()
    DEBUG = args.debug
    main(args.host, args.port, args.cell)
