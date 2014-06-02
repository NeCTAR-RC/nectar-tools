#!/usr/bin/python
# Copyright (c) 2014 The University of Melbourne
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from datetime import datetime
from urllib import urlencode
import logging
import requests
import socket
import time

import MySQLdb

if __name__ == '__main__':
    LOG_NAME = __file__
else:
    LOG_NAME = __name__

logger = logging.getLogger(LOG_NAME)

cells = ["nectar!melbourne!np",
         "nectar!melbourne!qh2",
         "nectar!monash!monash-01",
         "nectar!qld",
         "nectar!sa-cw",
         "nectar!monash!monash-test",
         "nectar!NCI",
         "nectar!tas!tas-m",
         "nectar!tas!tas-s",
]

azs = {"nectar!melbourne!np": "melbourne-np",
       "nectar!melbourne!qh2": "melbourne-qh2",
       "nectar!monash!monash-01": "monash-01",
       "nectar!qld": "qld",
       "nectar!sa-cw": "sa",
       "nectar!monash!monash-test": "monash-test",
       "nectar!NCI": "NCI",
       "nectar!tas!tas-m": "tasmania",
       "nectar!tas!tas-s": "tasmania-s",
}

header = None
count = 0

first_dates = {
    'sa': 1383186000,
    'NCI': 1396241400,
    'melbourne-qh2': 1352786400,
    'tasmania': 1397101800,
    'qld': 1367304000,
    'monash-test': 1387422600,
    'melbourne-np': 1327543800,
    'monash-01': 1365573000,
    'tasmania-s': 1397184000,
}

for c, d in first_dates.items():
    first_dates[c] = datetime.fromtimestamp(d)


class BaseSender(object):
    message_fmt = '%s %0.2f %d\n'

    def __init__(self):
        self.log = logging.getLogger(self.__class__.__name__)

    def format_metric(self, metric, value, now):
        if isinstance(now, datetime):
            now = time.mktime(now.timetuple())
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


class DB:
    def __init__(self, host, user, passwd, db):
        self.db = MySQLdb.connect(host=host,
                                  user=user,
                                  passwd=passwd,
                                  db=db)

        self.cur = db.cursor()

    def count_instances(self, cell, start_time, end_time):
        self.cur.execute("SELECT count(*), sum(vcpus) from nova.instances "
                         "WHERE cell_name = '%s' "
                         "AND created_at < '%s' "
                         "AND (deleted_at > '%s' OR deleted_at is Null) "
                         "AND launched_at is not Null;" %
                         (cell, start_time, end_time))
        row = self.cur.fetchone()
        return row[0] or 0, row[1] or 0


def recover_data(sender, db, date, reference_cell):
    start = date
    end = date
    total_instances = 0
    total_vcpus = 0
    for cell in cells:
        if not date > first_dates[azs[cell]]:
            continue
        instances, vcpus = db.count_instances(cell, start, end)
        total_instances += instances
        total_vcpus += vcpus
        az = azs[cell]
        sender.send_graphite_cell(az, "total_instances", instances, start)
        sender.send_graphite_cell(az, "used_vcpus", vcpus, start)
        if az == reference_cell:
            print "+", [instances, date]
    sender.send_graphite_nectar("total_instances", total_instances, start)
    sender.send_graphite_nectar("used_vcpus", total_vcpus, start)


def check_data(sender, db, cell):
    arguments = [('from', '-4months'),
                 ('format', 'json'),
                 ('target', '%s.total_instances' % cell)]

    response = requests.get(GRAPHITE + '?' + urlencode(arguments))
    data = response.json()[0]['datapoints']
    previous_point = (None, None)

    for point in data:
        if isinstance(point[1], int):
            point[1] = datetime.fromtimestamp(point[1])
        value, unixtime = point
        if not value:
            if previous_point[0]:
                print "#", previous_point
            recover_data(sender, db, unixtime, cell)
        else:
            if not previous_point[0]:
                print "#", point
        previous_point = point


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
    parser.add_argument('--graphite-url',
                        help='The url to the graphite site.')
    parser.add_argument('--db-host', help='')
    parser.add_argument('--db-name', help='')
    parser.add_argument('--db-port', default=2003, type=int,
                        help='')
    parser.add_argument('--db-username', help='')
    parser.add_argument('--db-password', help='')
    parser.add_argument('--reference-cell',
                        default='melbourne-qh2',
                        help='The cell metric to follow.')
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

    db = DB(host=args.db_host,
            user=args.db_username,
            passwd=args.db_password,
            db=args.db_name)

    GRAPHITE = args.graphite_url + "/render/"

    check_data(sender, db, args.reference_cell)
