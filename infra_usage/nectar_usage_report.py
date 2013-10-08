#!/usr/bin/env python
import argparse

from util_report import templateLoader, multiCSVNode
from util_report import createCSVFileCloud, emailUser
from util_report import createCSVFileNode, processConfig
from util_nova import createNovaConnection
from process_report import collect_all, combineResource, printOptions


def main():
    parser = argparse.ArgumentParser(argument_default=argparse.SUPPRESS)
    parser.add_argument('-a', nargs='?', dest='target_cell', action='store',
                        required=True, default=True,
                        help='{specify 1 cell name to overide,e,g -a np}')
    parser.add_argument('-o', nargs='?', dest='output', default='n',
                        choices=['html', 'csv', 'both', 'email'],
                        required=False,
                        help='output, {default: console}, {email: email html }')

    opts = parser.parse_args()

    username = processConfig('production', 'user')
    key = processConfig('production', 'passwd')
    tenant_name = processConfig('production', 'name')
    url = processConfig('production', 'url')
    zone = processConfig('config', 'zone')
    client = createNovaConnection(username, key, tenant_name, url)
    az = processConfig('config', 'az')
    if opts.target_cell is not None:
        if opts.target_cell not in az:
            parser.error("Error!, cell %s not found. Current cell %s " %
                         (opts.target_cell, az))
    else:
        opts.target_cell = True

    data = collect_all(client, zone, opt=opts.target_cell)
    if opts.target_cell is True:
        data2 = combineResource(data)
    else:
        data2 = None

    if opts.output is 'n':
        printOptions(data, data_2=data2, options='all')

    elif opts.output == 'html':
        templateLoader(data, data2)

    elif opts.output == 'csv':
        if opts.target_cell is True:
            multiCSVNode(data)
            createCSVFileCloud(data2)
        else:
            createCSVFileCloud(data)

    elif opts.output == 'both':
        templateLoader(data, data2, cell=opts.target_cell)
        if opts.target_cell is True:
            multiCSVNode(data)
            createCSVFileCloud(data2)
        else:
            createCSVFileCloud(data)

    elif opts.output == 'email':
        file_l = templateLoader(data, data2, cell=opts.target_cell, opt='email')
        emailUser(file_l)


if __name__ == '__main__':
    main()
