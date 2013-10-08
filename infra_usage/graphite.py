#!/usr/bin/env python
import calendar
import socket
from datetime import datetime
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter

from util_report import processConfig
from util_nova import createNovaConnection
from process_report import collect_compute, combineResource


def send_metric(sock, metric, value, time):
    message = ('%s %0.2f %d\n' %
               (metric, value, calendar.timegm(time.utctimetuple())))
    sock.sendall(message)
    return message


def send_graphite_nectar(sock, metric, value, time):
    return send_metric(sock, "nectar.%s" % metric,  value, time)


def send_graphite_cell(sock, cell, metric, value, time):
    return send_metric(sock, "nectar.cell.%s.%s" % (cell, metric),
                       value, time)


def main(host, port, cell):
    username = processConfig('production', 'user')
    key = processConfig('production', 'passwd')
    tenant_name = processConfig('production', 'name')
    url = processConfig('production', 'url')
    zone = processConfig('config', 'zone')
    client = createNovaConnection(username, key, tenant_name, url)

    cells = collect_compute(client, zone, target_cell=cell)
    totals = combineResource(cells)

    sock = socket.socket()
    sock.connect((host, port))
    now = datetime.now()
    for cell in cells:
        cell_name = cell["cell_name"]
        for metric, value in cell.items():
            if metric in ["node_name", "cell_name"]:
                continue
            send_graphite_cell(sock, cell_name, metric, value, now)

    for metric, value in totals.items():
        send_graphite_nectar(sock, metric, value, now)

if __name__ == '__main__':
    parser = ArgumentParser(formatter_class=ArgumentDefaultsHelpFormatter)
    parser.add_argument('--cell', action='store',
                        help='specify 1 cell name to overide, e.g. -a np')
    parser.add_argument('--host', required=True,
                        help='Carbon Host.')
    parser.add_argument('--port', default=2003, type=int,
                        required=False,
                        help='Carbon Port.')
    args = parser.parse_args()
    main(args.host, args.port, args.cell)
