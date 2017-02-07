#!/usr/bin/env python

"""Retrieve all the facts from puppetdb, dump to stdout in the format
in which they are returned, which is json."""


import json
import logging
import os
import urllib
import requests

logging.basicConfig(level=logging.DEBUG)


endpoint = urllib.parse.urljoin(
    os.getenv('PUPPETDB_URL', 'http://puppetdb.example.com:8080'),
    '/v4/facts'
)
logging.debug('endpoint: {}'.format(endpoint))


def facts():
    global endpoint
    r = requests.get(endpoint)
    logging.debug(r.json()[200])
    logging.debug(r.text[200])
    return r.text


if __name__ == "__main__":
    print (facts())
