#!/usr/bin/env python

"""parse puppet class data from stdin and given an environment and a class name
report those nodes that do not have the named class realised."""

import itertools
import json
import logging
import os
import sys

logging.basicConfig(level=logging.INFO)


def classname_missing(classes_json, classname, environment):
    """return list of certnames that do not have classname present."""
    names = {}
    for c in classes_json:
        if c['environment'] == environment:
            names[c['certname']] = False
    for c in classes_json:
        if c['environment'] == environment and c['title'] == classname:
            names[c['certname']] = True
    not_present = []
    for n in names.items():
        if n[1] is False:
            not_present.append(n[0])
        logging.debug(n)
    return not_present


if __name__ == "__main__":
    classname = os.environ['PUPPETDB_CLASSNAME']
    environment = os.environ['PUPPETDB_ENVIRONMENT']
    classes_json = json.load(sys.stdin)
    print('Nodes in {} that do not have class {} are :'.format(
        environment,
        classname
    ))
    missing = classname_missing(classes_json, classname, environment)
    missing.sort()
    for n in missing:
        print('\t' + n)
