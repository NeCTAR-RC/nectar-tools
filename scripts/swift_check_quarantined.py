#!/usr/bin/env python3

"""Check and delete swift quarantined objects
"""

import argparse
import netifaces
import os
import sys

from swift.common.exceptions import DiskFileBadMetadataChecksum
from swift.common.ring import Ring
from swift.common.utils import hash_path, storage_directory
from swift.obj.diskfile import read_metadata


class InvalidDatafile(Exception):
    pass


def get_my_ips():
    addrs = []
    interfaces = netifaces.interfaces()
    for interface in interfaces:
        links = netifaces.ifaddresses(interface).get(netifaces.AF_INET)
        if links:
            for link in links:
                addrs.append(link['addr'])
    return addrs


def get_fullpath(datafile):
    if not os.path.exists(datafile):
        print("Data file doesn't exist")
        sys.exit(2)
    if not datafile.startswith(('/', './')):
        datafile = './' + datafile

    fullpath = os.path.abspath(datafile)

    return fullpath


def get_metadata(datafile):
    with open(datafile, 'rb') as fp:
        try:
            metadata = read_metadata(fp)
        except EOFError:
            print("Error reading file: EOFError")
            raise InvalidDatafile
        except DiskFileBadMetadataChecksum:
            print("Error reading file: Bad checksum")
            raise InvalidDatafile

    return metadata


def delete_datafile(datafile):
    print(f"Deleting {datafile}")
    os.remove(datafile)
    dirname = os.path.dirname(datafile)
    print(f"Deleting {dirname}")
    os.rmdir(dirname)


def main(arguments):

    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--delete', action='store_true')
    parser.add_argument('--delete-invalid-source', action='store_true')
    parser.add_argument('datafiles', metavar='file', nargs='+',
                        help='swift object file')

    args = parser.parse_args(arguments)

    my_ips = get_my_ips()

    for datafile in args.datafiles:
        datafile = get_fullpath(datafile)

        # most of this is copied from swift/cli/info.py
        try:
            metadata = get_metadata(datafile)
        except InvalidDatafile:
            if args.delete_invalid_source:
                delete_datafile(datafile)
            continue

        basename = os.path.basename(datafile)
        name = metadata.get('name')
        account, container, obj = name.split('/', 3)[1:]
        ring = Ring('/etc/swift/', ring_name='object')
        part = ring.get_part(account, container, obj)
        path_hash = hash_path(account, container, obj)

        primary_nodes = ring.get_part_nodes(part)
        file_belongs = False
        for node in primary_nodes:
            # if one of the primary nodes matches with my IP, find out where
            # the file should be
            if node['ip'] in my_ips:
                file_belongs = True
                storage_dir = storage_directory('objects', part, path_hash)
                # this is where the file should be
                datafile_correct = (f"/srv/node/{node['device']}/"
                                    f"{storage_dir}/{basename}")

                # make sure datafile and datafile correct are not the same
                if datafile == datafile_correct:
                    print(f"{datafile} is in the right place, skipping.")
                    continue

                if not os.path.exists(datafile_correct):
                    print(f"{datafile} should be in {datafile_correct}, "
                          "skipping.")
                    continue

                print(f"Found! Comparing {datafile} to {datafile_correct}")
                # read_metadata() fill check etag against md5sum of file, so we
                # just load metadata and check that
                try:
                    metadata_correct = get_metadata(datafile_correct)
                except InvalidDatafile:
                    print(f"{datafile_correct} seems to be corrupted, skipping.")
                    continue
                print(f"ETag {metadata['ETag']} for File {datafile}")
                print(f"ETag {metadata_correct['ETag']} for File "
                      f"{datafile_correct}")
                if metadata_correct['ETag'] == metadata['ETag']:
                    print(f"Both metadata matches {metadata['ETag']}, "
                          f"{datafile} is OK to delete")

                if args.delete:
                    delete_datafile(datafile)

        if not file_belongs:
            print(f"{datafile} does not belong to this node, please check "
                  "with swift-object-info.")


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
