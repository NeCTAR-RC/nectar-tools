#!/usr/bin/env python
import argparse


def get_args():
    parser = argparse.ArgumentParser(argument_default=argparse.SUPPRESS)
    parser.add_argument('-a', nargs='?', dest='t', action='store',
                        required=True,
                        help='{specify 1 cell name to overide,e,g -a np}')
    parser.add_argument('-o', nargs='?', dest='o', default='n',
                        choices=['html', 'csv', 'both', 'email'],
                        required=False,
                        help='output, {default: console}, {email: email html }'
                        )
    return parser.parse_args()
