#!/usr/bin/env python

import argparse
import csv
from datetime import datetime
from dateutil.relativedelta import relativedelta
from email.mime.text import MIMEText
import logging
import os

import prettytable


from nectar_tools import auth
from nectar_tools import config
from nectar_tools import log
from nectar_tools.expiry import expirer
from nectar_tools.expiry import exceptions

DRY_RUN = True
ARCHIVE_ATTEMPTS = 10

ACTION_DATE_FORMAT = '%Y-%m-%dT%H:%M:%S.%f'


LOG = logging.getLogger(__name__)
CONFIG = config.CONFIG


def main():
    parser = CONFIG.get_parser()
    add_args(parser)
    args = CONFIG.parse()

    log.setup()

    if args.no_dry_run:
        global DRY_RUN
        DRY_RUN = False
    else:
        LOG.info('DRY RUN')

    ks_session = auth.get_session()
    kc = auth.get_keystone_client(ks_session)

    projects = []
    if args.project_id:
        project = kc.projects.get(args.project_id)
        projects.append(project)
    if not projects:
        projects = kc.projects.list()
        if args.filename:
            wanted_projects = read_csv(args.filename)[0]
            projects = [p for p in projects if p.id in wanted_projects]
    projects.sort(key=lambda p: p.name.split('-')[-1].zfill(5))


    if args.status:
        print_status(projects)
    else:
        for p in projects:
            try:
                ex = expirer.AllocationExpirer(project=p,
                                               ks_session=ks_session,
                                               dry_run=DRY_RUN)
                ex.process(force_no_allocation=True)
            except exceptions.InvalidProjectTrial:
                pass


def project_set_defaults(project):
    project.owner = getattr(project, 'owner', None)
    old_status = getattr(project, 'status', '')
    old_expires = getattr(project, 'expires', '')
    project.expiry_status = getattr(project, 'expiry_status', old_status)
    project.expiry_next_step = getattr(project,
                                            'expiry_next_step', old_expires)


def print_status(projects):
    pt = prettytable.PrettyTable(['Name', 'Project ID', 'Owner',
                                  'Status', 'Expiry date'])
    for project in projects:
        if project.name.startswith('pt-'):
            continue
        project_set_defaults(project)
        pt.add_row([project.name, project.id,
                    '',
                    project.expiry_status, project.expiry_next_step])
    print(pt)


def add_args(parser):
    """Handle command-line options"""
    parser.description = 'Updates project expiry date'
    parser.add_argument('-y', '--no-dry-run', action='store_true',
                        default=False,
                        help='Perform the actual actions, default is to \
                        only show what would happen')
    parser.add_argument('-f', '--filename',
                        type=argparse.FileType('r'),
                        help='File path with a list of projects')
    parser.add_argument('-l', '--limit',
                        type=int,
                        default=0,
                        help='Only process this many eligible projects.')
    parser.add_argument('-p', '--project-id',
                        help='Project ID to process')
    parser.add_argument('-s', '--status', action='store_true',
                        help='Report current status of each project.')


def process_projects(kc, nc, projects, users, zone, limit=0, offset=None,
                    action_state=None):
    """Update project start and expiry dates in Keystone DB"""
    processed = 0
    offset_count = 0
    for project in projects:
        project_set_defaults(project)
        offset_count += 1
        if offset is None or offset_count > offset:

            if should_process_project(project):
                if action_state:
                    project_status = getattr(project, 'status', None)
                    if (not project_status and action_state == 'OK') or \
                       action_state == project_status:
                            if process_project(kc, nc, project):
                                processed += 1

                else:
                    if zone and not project_instances_are_all_in_zone(nc,
                                                                     project,
                                                                     zone):
                        continue
                    did_something = process_project(kc, nc, project)
                    if did_something:
                        processed += 1

        if limit > 0 and processed >= limit:
            break



def set_status(kc, project, status, expires=''):
    if DRY_RUN:
        if status is None:
            LOG.info("\twould set empty status")
        else:
            LOG.info("\twould set status to %s (next step: %s)" %
                     (status, expires))
    else:
        if status is None:
            LOG.info("\tsetting empty status")
        else:
            LOG.info("\tsetting status to %s (next step: %s)" %
                     (status, expires))
        kc.projects.update(project.id, status=status, expires=expires)

    project.status = status
    project.expires = expires




def read_csv(filename=False):
    """ Get a list of UUIDs from either file.
        Can be project or user IDs
    """
    reader = csv.reader(filename)
    return list(reader)



if __name__ == '__main__':
    main()
