#!/usr/bin/python

import requests
import socket

API = "http://mon.mgmt.melbourne.rc.nectar.org.au:8080/v3/"
resp = requests.get(API + 'nodes', params={'query': '["=", ["node", "active"], true]'})
hosts = resp.json()

import logging

log = logging.getLogger(__file__)


def get_fact(fqdn, fact):
    URL = API + 'nodes/%s/facts/%s' % (fqdn, fact)
    resp = requests.get(URL).json()
    if resp:
        return resp[0]['value']
    else:
        return ''


def get_hosts():
    for host in hosts:
        fqdn = host['name']
        if not(fqdn.endswith('rc.nectar.org.au')
               or fqdn.endswith('melbourne.nectar.org.au')
               or fqdn.endswith('unimelb.edu.au')):
            continue
        key = get_fact(fqdn, 'sshecdsakey')
        private_ip = get_fact(fqdn, 'ipaddress_private')
        if not private_ip.startswith('172.26'):
            private_ip = get_fact(fqdn, 'ipaddress')
            log.debug("Address isn't in our private management network %s." % private_ip)
        else:
            # Try to use the private ip address to find the hostname
            try:
                hostname = socket.gethostbyaddr(private_ip)[0]
                fqdn = hostname
            except:
                log.debug("Reverse lookup of %s failed." % private_ip)
                pass
        print ','.join((fqdn, private_ip)), 'ecdsa-sha2-nistp256', key


if '__main__' == __name__:
    import argparse

    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description='Generate a known hosts file from puppetdb')
    parser.add_argument(
        '-v', '--verbose', action='count', default=0,
        help="Increase verbosity (specify multiple times for more)")

    args = parser.parse_args()

    log_level = logging.WARNING
    if args.verbose == 1:
        log_level = logging.INFO
    elif args.verbose >= 2:
        log_level = logging.DEBUG

    logging.basicConfig(
        level=log_level,
        format='%(asctime)s %(name)s %(levelname)s %(message)s')

    # run program
    get_hosts()
