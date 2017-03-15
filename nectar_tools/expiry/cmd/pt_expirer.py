#!/usr/bin/env python

import argparse
import csv
import prettytable

from nectar_tools import auth
from nectar_tools import config
from nectar_tools import log

from nectar_tools.expiry import exceptions
from nectar_tools.expiry import expirer


DRY_RUN = True
CONFIG = config.CONFIG


def main():
    parser = CONFIG.get_parser()
    add_args(parser)
    args = CONFIG.parse()

    log.setup()

    if args.no_dry_run:
        global DRY_RUN
        DRY_RUN = False

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

    users = kc.users.list()
    link_projects_to_users(projects, users)
    if args.status:
        print_status(projects)
    else:
        for p in projects:
            try:
                ex = expirer.PTExpirer(project=p, ks_session=ks_session,
                                       dry_run=True)
                ex.process()
            except exceptions.InvalidProjectTrial:
                pass


def print_status(projects):
    pt = prettytable.PrettyTable(['Name', 'Project ID', 'Owner',
                                  'Status', 'Expiry date'])
    for project in projects:
        pt.add_row([project.name, project.id,
                    getattr(project.owner, 'email', ''),
                    project.status, project.expires])
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


def link_projects_to_users(projects, users):
    projects_dict = {project.id: project for project in projects}

    for user in users:
        project_id = getattr(user, 'default_project_id', None)
        if project_id:
            if project_id in projects_dict:
                projects_dict[project_id].owner = user


def read_csv(filename=False):
    """Get a list of UUIDs from either file.

    Can be project or user IDs
    """
    reader = csv.reader(filename)
    return list(reader)


if __name__ == '__main__':
    main()
