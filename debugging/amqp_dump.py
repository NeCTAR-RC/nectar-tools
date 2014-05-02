#!/usr/bin/env python
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

import os
import sys
import pprint
import json
import logging

import pika

log = logging.getLogger(__file__)

binding_key = "#"


def getTerminalSize():
    env = os.environ

    def ioctl_GWINSZ(fd):
        try:
            import fcntl
            import termios
            import struct
            cr = struct.unpack('hh',
                               fcntl.ioctl(fd, termios.TIOCGWINSZ, '1234'))
        except:
            return
        return cr
    cr = ioctl_GWINSZ(0) or ioctl_GWINSZ(1) or ioctl_GWINSZ(2)
    if not cr:
        try:
            fd = os.open(os.ctermid(), os.O_RDONLY)
            cr = ioctl_GWINSZ(fd)
            os.close(fd)
        except:
            pass
    if not cr:
        cr = (env.get('LINES', 25), env.get('COLUMNS', 80))

    return int(cr[1]), int(cr[0])


include_filter_key = []
exclude_filter_key = []

include_method = []
exclude_method = []

msg_no = 0


def callback(ch, method, properties, body):
    width, height = getTerminalSize()

    global msg_no
    msg_no = msg_no + 1
    if include_filter_key and method.routing_key not in include_filter_key:
        sys.stdout.write('.')
        sys.stdout.flush()
        log.debug("Skipping message for key %s" % method.routing_key)
        return
    if method.routing_key in exclude_filter_key:
        sys.stdout.write('.')
        sys.stdout.flush()
        log.debug("Skipping message for key %s" % method.routing_key)
        return

    msg = json.loads(body)
    if 'oslo.message' in msg:
        msg['oslo.message'] = json.loads(msg['oslo.message'])
        if 'args' in msg['oslo.message'] \
           and 'message' in msg['oslo.message']['args']:
            msg['oslo.message']['args']['message'] = \
                json.loads(msg['oslo.message']['args']['message'])

        if msg['oslo.message'].get('method'):
            rpc_method = msg['oslo.message']['method']
            if include_method and rpc_method not in include_method:
                sys.stdout.write('.')
                sys.stdout.flush()
                log.debug("Skipping method %s" % rpc_method)
                return

            if rpc_method in exclude_method:
                sys.stdout.write('.')
                sys.stdout.flush()
                log.debug("Skipping method %s" % rpc_method)
                return

    print "\n\n** [%s] %s\n" % (msg_no, method.routing_key)
    pprint.pprint(msg, width=width)


if '__main__' == __name__:
    import argparse

    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--rabbit-user',
                        default='guest',
                        help='The user to connect to rabbitmq as.')
    parser.add_argument('--rabbit-password',
                        default='test',
                        help='The password of the rabbitmq user.')
    parser.add_argument('--rabbit-vhost',
                        default='%2f',
                        help='The rabbitmq vhost to use.')
    parser.add_argument('--rabbit-host',
                        default='localhost',
                        help='The address of the rabbitmq server.')
    parser.add_argument('--rabbit-port',
                        default=5672, type=int,
                        help='The port of the rabbitmq server.')
    parser.add_argument('--rabbit-exchange',
                        default='nova',
                        help='The port of the rabbitmq server.')
    parser.add_argument('--include',
                        default=[], required=False, action='append',
                        help='Only show messages with this routing key.')
    parser.add_argument('--exclude',
                        default=[], required=False, action='append',
                        help='Hide messages with this routing key.')
    parser.add_argument('--include-method',
                        default=[], required=False, action='append',
                        help='Only show messages with this routing key.')
    parser.add_argument('--exclude-method',
                        default=[], required=False, action='append',
                        help='Hide messages with this routing key.')
    parser.add_argument(
        '-v', '--verbose', action='count', default=0,
        help='Increase verbosity (specify multiple times for more)')

    args = parser.parse_args()

    log_level = logging.WARNING
    if args.verbose == 1:
        log_level = logging.INFO
    elif args.verbose >= 2:
        log_level = logging.DEBUG

    logging.basicConfig(
        level=log_level,
        format='%(asctime)s %(name)s %(levelname)s %(message)s')

    exchange_name = args.rabbit_exchange
    include_filter_key = args.include
    exclude_filter_key = args.exclude
    include_method = args.include_method
    exclude_method = args.exclude_method

    parameters = pika.URLParameters(
        'amqp://%s:%s@%s:%s/%s'
        % (args.rabbit_user,
           args.rabbit_password,
           args.rabbit_host,
           args.rabbit_port,
           args.rabbit_vhost))

    try:
        connection = pika.BlockingConnection(parameters)
    except:
        log.error("Unable to connect to rabbitmq.")
        sys.exit(1)

    channel = connection.channel()
    if 'trace' in exchange_name:
        channel.exchange_declare(exchange=exchange_name,
                                 type='topic',
                                 durable=True,
                                 internal=False,
                                 auto_delete=False)
    else:
        channel.exchange_declare(exchange=exchange_name, type='topic')

    # result = channel.queue_declare(exclusive=True)
    result = channel.queue_declare(durable=False, auto_delete=True)
    queue_name = result.method.queue

    channel.queue_bind(exchange=exchange_name,
                       queue=queue_name,
                       routing_key=binding_key)

    channel.basic_consume(callback,
                          queue=queue_name,
                          no_ack=True)

    print '** Waiting for messages. To exit press CTRL+C'

    channel.start_consuming()
