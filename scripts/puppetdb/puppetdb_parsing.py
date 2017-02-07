#!/usr/bin/env python

"""parse puppet fact data from a file and report useful information"""

import json
import logging
import os
import yaml

logging.basicConfig(level=logging.INFO)

config_file = os.getenv(
    'PUPPETDB_PARSING_CONFIG_FILE',
    os.path.join(
        os.environ['HOME'], '.local',  'puppetdb_parsing.yaml',
    )
)

logging.debug('config file: {}'.format(config_file))

with open(config_file) as cf:
    config = yaml.safe_load(cf)

logging.debug('config: {}'.format(config))

try:
    fact_file = config['fact_file']
except KeyError:
    fact_file = os.path.join(
        os.environ['HOME'], 'data', 'puppet', 'facts'
    )

with open(fact_file) as ff:
    facts = json.load(ff)


def disk_devices(node):
    """given a nodename, return a list of its disk devices."""
    disks = []
    for fact in facts:
        if (
            fact['name'] == 'blockdevices' and
            fact['certname'].startswith(node)
        ):
            logging.debug('evaluating {}'.format(fact['certname']))
            logging.debug('blockdevices fact: {}'.format(fact['value']))
            blockdevices = fact['value'].split(',')
            logging.debug('block devices: {}'.format(blockdevices))
            disks.extend([x for x in blockdevices if x.startswith('sd')])
    return disks


def disk_device_size(node, disks):
    """given a nodename and a list of disks, return the sum of the capacities
    in GB"""
    BILLION = 1.00E+09
    capacity_bytes = 0
    for fact in facts:
        if fact['certname'].startswith(node):
            for disk in disks:
                disk_fact_name = 'blockdevice_' + disk + '_size'
                if fact['name'] == disk_fact_name:
                    logging.debug(
                        'adding capacity {} from disk {} node {}'.format(
                            fact['value'],
                            fact['name'],
                            fact['certname']
                        )
                    )
                    capacity_bytes += int(fact['value'])

    return round(capacity_bytes / BILLION)


if __name__ == "__main__":
    n = (
        config['nodes']['test'] +
        config['nodes']['shared'] +
        config['nodes']['production']
    )
    for host in n:
        print('{}: disk devices: {}'.format(host, disk_devices(host)))
        print(
            '{}: total disk capacity: {} GB'.format(
                host,
                disk_device_size(host, disk_devices(host))
            )
        )
