#!/usr/bin/env python

"""parse puppet class data from stdin and report those nodes that contain
a named classs"""

import json
import logging
import os
import sys

logging.basicConfig(level=logging.DEBUG)


def certnames(classes_json, classname):
    """return list of certnames from list of puppet node data"""
    names = []
    for c in classes_json:
        if c['title'] == classname:
            names.append(c['certname'])
    return names


if __name__ == "__main__":
    classname = os.environ['PUPPETDB_CLASSNAME']
    classes_json = json.load(sys.stdin)
    print(certnames(classes_json, classname))
