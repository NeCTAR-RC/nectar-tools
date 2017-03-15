import argparse
import csv
import logging
import prettytable

from nectar_tools import auth
from nectar_tools import config
from nectar_tools import log

from nectar_tools.expiry import exceptions
from nectar_tools.expiry import expiry_states


CONFIG = config.CONFIG
LOG = logging.getLogger(__name__)


class Manager(object):

    def __init__(self):
        self.parser = CONFIG.get_parser()
        self.add_args()
        self.args = CONFIG.parse()

        log.setup()

        self.dry_run = True
        if self.args.no_dry_run:
            self.dry_run = False

        self.session = auth.get_session()
        self.k_client = auth.get_keystone_client(self.session)

        projects = []
        if self.args.project_id:
            project = self.k_client.projects.get(self.args.project_id)
            projects.append(project)
        if not projects:
            projects = self.k_client.projects.list(enabled=True)
            if self.args.filename:
                wanted_projects = self.read_csv(self.args.filename)[0]
                projects = [p for p in projects if p.id in wanted_projects]
            projects.sort(key=lambda p: p.name.split('-')[-1].zfill(5))
        self.projects = projects

    def print_status(self):
        pt = prettytable.PrettyTable(['Name', 'Project ID', 'Owner',
                                      'Status', 'Expiry date'])
        for project in self.projects:
            if self.valid_project(project):
                self.project_set_defaults(project)
                pt.add_row([project.name, project.id,
                            '',
                            project.expiry_status, project.expiry_next_step])
        print(pt)

    def pre_process_projects(self):
        return

    def process_projects(self):

        self.pre_process_projects()

        limit = self.args.limit
        offset = self.args.offset
        offset_count = 0
        processed = 0

        for p in self.projects:
            if self.valid_project(p):
                offset_count += 1
                if offset is None or offset_count > offset:
                    try:
                        ex = self.get_expirer(p)
                        if ex.process():
                            processed += 1
                    except exceptions.InvalidProject:
                        pass
                    except Exception as e:
                        LOG.exception('Exception processing project %s', p.id)

                if limit > 0 and processed >= limit:
                    break
        print("Processed %s projects" % processed)
        return processed

    def add_args(self):
        """Handle command-line options"""
        self.parser.description = 'Updates project expiry date'
        self.parser.add_argument('-y', '--no-dry-run', action='store_true',
                            default=False,
                            help='Perform the actual actions, default is to \
                                 only show what would happen')
        self.parser.add_argument('-f', '--filename',
                            type=argparse.FileType('r'),
                            help='File path with a list of projects')
        self.parser.add_argument('-l', '--limit',
                            type=int,
                            default=0,
                            help='Only process this many eligible projects.')
        self.parser.add_argument('-o', '--offset',
                            type=int,
                            default=None,
                            help='Skip this many projects before processing.')
        self.parser.add_argument('-p', '--project-id',
                            help='Project ID to process')
        self.parser.add_argument('-s', '--status', action='store_true',
                            help='Report current status of each project.')
        self.parser.add_argument('-a', '--set-admin', action='store_true',
                            help='Mark a list of projects as admins')
        self.parser.add_argument('--action-state', action='store',
                            default=None,
                                 help='Only process projects in this state')

    @staticmethod
    def read_csv(filename=False):
        """Get a list of UUIDs from either file.

        Can be project or user IDs
        """
        reader = csv.reader(filename)
        return list(reader)

    @staticmethod
    def project_set_defaults(project):
        project.owner = getattr(project, 'owner', None)
        old_status = getattr(project, 'status', '')
        old_expires = getattr(project, 'expires', '')
        project.expiry_status = getattr(project, 'expiry_status', old_status)
        project.expiry_next_step = getattr(project,
                                           'expiry_next_step', old_expires)

    def set_admin(self):
        """Set status to admin for specified list of projects.
        """
        for project in self.projects:
            self.project_set_defaults(project)
            if project.expiry_status == expiry_states.ADMIN:
                LOG.error("Project %s is already admin", project.id)
            else:
                if self.dry_run:
                    LOG.info("would set status admin for %s(%s) (dry run)",
                             project.name, project.id)
                else:
                    LOG.debug("setting status admin for %s", project.id)
                    self.k_client.projects.update(
                        project.id, expiry_status=expiry_states.ADMIN)
