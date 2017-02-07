#!/usr/bin/env python3

"""Retrieve the catalog from puppetdb for a node"""

import argparse
import json
import logging
import os
import urllib
import requests

logging.basicConfig(level=logging.DEBUG)


def catalog(node):
    logging.debug('node: {}'.format(node))
    slug = 'v4/catalogs/' + node
    endpoint = urllib.parse.urljoin(
        os.getenv(
            'PUPPETDB_URL',
            'http://puppetdb.example.com:8080'),
        slug,
    )
    logging.debug('endpoint: {}'.format(endpoint))
    r = requests.get(endpoint)
    logging.debug(r.text[200])
    return r.text


if __name__ == "__main__":
    node = os.environ['PUPPETDB_NODE']
    print (catalog(node))
