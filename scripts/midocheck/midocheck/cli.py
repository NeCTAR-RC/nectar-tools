# -*- coding: utf-8 -*-

"""Console script for midocheck."""
import logging
import sys
import pdb
import traceback

import click

from midocheck import client

LOG = logging.getLogger(__name__)


@click.command()
@click.option('--ports', help='Check Ports', is_flag=True)
@click.option('--routers', help='Check Routers', is_flag=True)
@click.option('--delete', help='Delete orphaned resources', is_flag=True)
@click.option('--verbose', help='Verbose', is_flag=True)
@click.argument('uuid', nargs=-1, type=click.UUID)
def main(uuid=None, ports=False, routers=False, delete=False, verbose=False):
    c = client.Client()

    try:
        if ports:
            resources = c.list_ports()

        if routers:
            resources = c.list_routers()

        # if uuids is provided, only work on those uuids that matches what is
        # provided
        if uuid:
            # get rid of duplications and stringify
            uuids = set(str(u) for u in uuid)
            resource_ids = set(resources)
            for i in resource_ids - uuids:
                resources.pop(i)

        resources.analyse()
        resources.prettyprint()

        if delete:
            print("Deleting resources...")
            delete_uuids = resources.get_delete_uuids()
            if routers:
                c.delete_routers(delete_uuids)
            if ports:
                c.delete_ports(delete_uuids)

        return 0

    except:  # noqa
        extype, value, tb = sys.exc_info()
        traceback.print_exc()
        pdb.post_mortem(tb)


if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover
