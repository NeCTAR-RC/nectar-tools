#!/usr/bin/env python3

"""Retrieve a list of all nodes from puppetdb"""

import json
import logging
import os
import urllib
import requests

logging.basicConfig(level=logging.DEBUG)


def nodes(url):
    logging.debug('url: {}'.format(url))
    endpoint = urllib.parse.urljoin(url, '/v4/nodes')
    logging.debug('endpoint: {}'.format(endpoint))
    r = requests.get(endpoint)
    logging.debug(r.text[200])
    return r.text


if __name__ == "__main__":
    puppetdb_url = os.getenv(
            'PUPPETDB_URL',
            default='http://puppetdb.example.com:8080')
    logging.debug('puppetdb_url is {}'.format(puppetdb_url))
    logging.debug('puppetdb_url type is {}'.format(type(puppetdb_url)))
    print (nodes(puppetdb_url))
