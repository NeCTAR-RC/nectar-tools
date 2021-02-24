#!/usr/bin/env python3

import argparse
import configparser

parser = argparse.ArgumentParser()
parser.add_argument('old', help='old conf')
parser.add_argument('new', help='new conf')
parser.add_argument('--ignore', help='ignore file')
args = parser.parse_args()

old = configparser.RawConfigParser(strict=False)
old.default = 'DEFAULT'
new = configparser.RawConfigParser(strict=False)
ignore = configparser.RawConfigParser(strict=False)
old.read(args.old)
new.read(args.new)

if args.ignore:
    ignore.read(args.ignore)

# if value matches the ignore value, return 'default'
# otherwise return the value in ignore file
# return false in other cases.
def get_ignore(ignore, section, key, value):
    sect = ignore.sections() + ['DEFAULT']
    if section in sect and key in ignore[section]:
        if value == ignore[section][key]:
            return '[default]'
        else:
            return ignore[section][key]
    return False

def print_diff(config, section, key):
    value = config[section][key]
    if config == old:
        msg = "-{}={}".format(key, value)
    if config == new:
        msg = "+{}={}".format(key, value)
    if args.ignore:
        ret = get_ignore(ignore, section, key, value)
        if ret:
            msg = msg + ' ({})'.format(ret)
    print(msg)


def iterate_keys(section, old, new):
    print (" [{}]".format(section))
    old_keys = set(old[section])
    new_keys = set(new[section])
    all_keys = old_keys | new_keys
    for key in all_keys:
        if key not in old_keys:
            if section != 'DEFAULT' and key in new['DEFAULT']:
                continue
            print_diff(new, section, key)
            continue
        if key not in new_keys:
            if section != 'DEFAULT' and key in old['DEFAULT']:
                continue
            print_diff(old, section, key)
            continue
        if new[section][key] != old[section][key]:
            # disregard booleans, e.g. make 'True' same as 'true'
            # distutils.util.strtobool() doesn't seem to work
            if (new[section][key].lower() == 'false' or
                new[section][key].lower() == 'true'):
                if new[section][key].lower() == old[section][key].lower():
                    continue
            if section != 'DEFAULT' and key in old['DEFAULT']:
                continue
            print_diff(old, section, key)
            print_diff(new, section, key)

# Test 'DEFAULT' section first; this is because DEFAULT keys appear in all
# sections and we skip them later
iterate_keys('DEFAULT', old, new)

# Find the section difference
old_sections = set(old.sections())
new_sections = set(new.sections())
sections = old_sections & new_sections
all_sections = old_sections | new_sections

for section in all_sections:
    if section in old_sections - new_sections:
        print (" [{}]".format(section))
        for key in old[section]:
            if key in old['DEFAULT']:
                 continue
            print_diff(old, section, key)
        continue
    if section in new_sections - old_sections:
        print (" [{}]".format(section))
        for key in new[section]:
            if key in new['DEFAULT']:
                 continue
            print_diff(new, section, key)
        continue

# Find the difference in the common sections
for section in sections:
    iterate_keys(section, old, new)
