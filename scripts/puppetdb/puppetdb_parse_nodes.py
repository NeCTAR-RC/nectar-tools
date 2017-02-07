#!/usr/bin/env python

"""parse puppet node data from stdin and report bare names of nodes"""

import json
import logging
import os
import sys

logging.basicConfig(level=logging.DEBUG)


def certnames(nodes_json):
    """return list of certnames from list of puppet node data"""
    names = []
    for n in nodes_json:
        names.append(n['certname'])
    return names

if __name__ == "__main__":
    nodes_json = json.load(sys.stdin)
    print(certnames(nodes_json))
