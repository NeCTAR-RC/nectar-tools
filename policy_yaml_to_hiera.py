#!/usr/bin/env python

import argparse
import yaml

parser = argparse.ArgumentParser()
parser.add_argument('policy_file', help='policy.yaml')
parser.add_argument('namespace', help='Namespace like nova or neutron. This is used to prefix the hiera key')

args = parser.parse_args()

with open(args.policy_file, "r") as stream:
    try:
        yaml = yaml.safe_load(stream)
    except yaml.YAMLError as exc:
        print(exc)

for k, v in yaml.items():
    print(f'"{args.namespace}-{k}":')
    print(f'  key: "{k}"')
    print(f'  value: "{v}"')
