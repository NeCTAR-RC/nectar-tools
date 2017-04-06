#!/usr/bin/env python

import logging

from nectar_tools.expiry.cmd import base
from nectar_tools.expiry import expirer


LOG = logging.getLogger(__name__)


class PTManager(base.Manager):

    @staticmethod
    def valid_project(project):
        return project.name.startswith('pt-')

    def get_expirer(self, project):
        return expirer.PTExpirer(project=project,
                                 ks_session=self.session,
                                 dry_run=self.dry_run)

    def pre_process_projects(self):
        LOG.debug("Pre processing projects")
        projects_dict = {project.id: project for project in self.projects}
        users = self.k_client.users.list()
        for user in users:
            project_id = getattr(user, 'default_project_id', None)
            if project_id:
                if project_id in projects_dict:
                    projects_dict[project_id].owner = user
        LOG.debug("Pre processing complete")


def main():
    manager = PTManager()
    if manager.args.status:
        manager.print_status()
        return
    manager.process_projects()


if __name__ == '__main__':
    main()
