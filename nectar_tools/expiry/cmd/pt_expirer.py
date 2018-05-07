#!/usr/bin/env python

import logging

from nectar_tools.expiry.cmd import base
from nectar_tools.expiry import expirer


LOG = logging.getLogger(__name__)


class PTExpiryCmd(base.ExpiryCmd):

    @staticmethod
    def valid_project(project):
        return expirer.PT_RE.match(project.name)

    def add_args(self):
        """Handle command-line options"""
        super(PTExpiryCmd, self).add_args()
        self.parser.add_argument('--disable-project', action='store_true',
                            help="Also disable project in keystone")

    def get_expirer(self, project):
        return expirer.PTExpirer(project=project,
                                 ks_session=self.session,
                                 dry_run=self.dry_run,
                                 disable_project=self.args.disable_project,
                                 force_delete=self.args.force_delete)

    def pre_process_projects(self):
        LOG.debug("Pre processing projects")
        projects_dict = {project.id: project for project in self.projects}
        if len(self.projects) == 1:
            users = self.k_client.users.list(
                default_project=self.projects[0].id)
        else:
            users = self.k_client.users.list()
        for user in users:
            project_id = getattr(user, 'default_project_id', None)
            if project_id:
                if project_id in projects_dict:
                    projects_dict[project_id].owner = user
        LOG.debug("Pre processing complete")


def main():
    cmd = PTExpiryCmd()
    if cmd.args.status:
        cmd.print_status()
        return
    cmd.process_projects()


if __name__ == '__main__':
    main()
