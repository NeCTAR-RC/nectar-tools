#!/usr/bin/env python
import time
import socket
import logging
from collections import defaultdict

from util_report import processConfig
from util_nova import createNovaConnection
from util_keystone import createConnection as createKeystoneConnection


if __name__ == '__main__':
    LOG_NAME = __file__
else:
    LOG_NAME = __name__

logger = logging.getLogger(LOG_NAME)


class BaseSender(object):
    message_fmt = '%s %0.2f %d\n'

    def __init__(self):
        self.log = logging.getLogger(self.__class__.__name__)

    def format_metric(self, metric, value, now):
        return self.message_fmt % (metric, value, now)

    def send_metric(self, metric, value, now):
        raise NotImplemented()

    def send_graphite_nectar(self, metric, value, time):
        raise NotImplemented()

    def send_graphite_cell(self, cell, metric, value, time):
        raise NotImplemented()

    def send_graphite_domain(self, cell, domain, metric, value, time):
        raise NotImplemented()


class DummySender(BaseSender):

    def send_metric(self, metric, value, now):
        message = self.format_metric(metric, value, now)
        print message
        return message

    def send_graphite_nectar(self, metric, value, time):
        return self.send_metric("%s" % metric,  value, time)

    def send_graphite_cell(self, cell, metric, value, time):
        return self.send_metric("%s.%s" % (cell, metric), value, time)

    def send_graphite_domain(self, cell, domain, metric, value, time):
        return self.send_metric("%s.domains.%s.%s" % (cell, domain, metric),
                                value, time)


class SocketMetricSender(BaseSender):
    sock = None
    reconnect_at = 100

    def __init__(self, host, port):
        super(SocketMetricSender, self).__init__()
        self.host = host
        self.port = port
        self.connect()
        self.count = 1

    def connect(self):
        if self.sock:
            self.sock.close()
            self.log.info("Reconnecting")
        else:
            self.log.info("Connecting")
        self.sock = socket.socket()
        self.sock.connect((self.host, self.port))
        self.log.info("Connected")

    def reconnect(self):
        self.count = 1
        self.connect()

    def send_metric(self, metric, value, now):
        message = self.format_metric(metric, value, now)
        if self.count > self.reconnect_at:
            self.reconnect()
        self.sock.sendall(message)
        return message

    def send_graphite_nectar(self, metric, value, time):
        return self.send_metric("%s" % metric,  value, time)

    def send_graphite_cell(self, cell, metric, value, time):
        return self.send_metric("%s.%s" % (cell, metric), value, time)

    def send_graphite_domain(self, cell, domain, metric, value, time):
        return self.send_metric("%s.domains.%s.%s" % (cell, domain, metric),
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


def main(sender):
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
            users[user.id] = None
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
        # Skip any hosts that are being run by users without an email
        # address.
        if server.user_id in users and users[server.user_id] is None:
            logger.info("skipping unknown user %s" % server.user_id)
            continue
        if server.user_id not in users:
            logger.error(
                "user %s doesn't exist but is currently owner of server %s"
                % (server.user_id, server.id))
            continue
        servers_by_cell_by_domain[cell][users[server.user_id]].append(server)

    now = int(time.time())
    for metric, value in server_metrics(servers, flavors).items():
        sender.send_graphite_nectar(metric, value, now)

    for zone, servers in servers_by_cell.items():
        for metric, value in server_metrics(servers, flavors).items():
            sender.send_graphite_cell(zone, metric, value, now)
    for zone, items in servers_by_cell_by_domain.items():
        for domain, servers in items.items():
            for metric, value in server_metrics(servers, flavors).items():
                if metric not in ['used_vcpus']:
                    continue
                sender.send_graphite_domain(zone, domain, metric, value, now)

if __name__ == '__main__':
    from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
    parser = ArgumentParser(formatter_class=ArgumentDefaultsHelpFormatter)
    parser.add_argument('-v', '--verbose', action='count', default=0,
                        help="Increase verbosity (specify multiple times for more)")
    parser.add_argument('--protocol', choices=['debug', 'carbon'],
                        required=True)
    parser.add_argument('--carbon-host', help='Carbon Host.')
    parser.add_argument('--carbon-port', default=2003, type=int,
                        help='Carbon Port.')
    args = parser.parse_args()

    log_level = logging.WARNING
    if args.verbose == 1:
        log_level = logging.INFO
    elif args.verbose >= 2:
        log_level = logging.DEBUG

    logging.basicConfig(
        level=log_level,
        format='%(asctime)s %(name)s %(levelname)s %(message)s')

    if args.protocol == 'carbon':
        if not args.carbon_host:
            parser.error('argument --carbon-host is required')
        if not args.carbon_port:
            parser.error('argument --carbon-port is required')
        sender = SocketMetricSender(args.carbon_host, args.carbon_port)
    elif args.protocol == 'debug':
        sender = DummySender()

    main(sender)
