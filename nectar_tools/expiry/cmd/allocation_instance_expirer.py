#!/usr/bin/env python

import prettytable

from nectar_tools.expiry.cmd import base
from nectar_tools.expiry import expirer


class AllocationInstanceExpiryCmd(base.ProjectExpiryBaseCmd):

    @staticmethod
    def valid_project(project):
        if expirer.PT_RE.match(project.name) or \
           not hasattr(project, 'compute_zones') or \
           not project.compute_zones or \
           project.compute_zones == 'national':
            return False
        return True

    def add_args(self):
        super(AllocationInstanceExpiryCmd, self).add_args()

    def get_expirer(self, project):
        return expirer.AllocationInstanceExpirer(
            project=project,
            ks_session=self.session,
            dry_run=self.dry_run,
            force_delete=self.args.force_delete)

    def print_status(self):
        pt = prettytable.PrettyTable(['Name', 'Project ID', 'Allocation Zone',
                                      'Expiry date', 'Expiry status',
                                      'Ticket ID'])
        for project in self.projects:
            if self.valid_project(project):
                self.project_set_defaults(project)
                pt.add_row([project.name, project.id, project.compute_zones,
                            project.expiry_date, project.expiry_status,
                            project.expiry_ticket_id])
        print(pt)

    @staticmethod
    def project_set_defaults(project):
        project.owner = getattr(project, 'owner', None)
        project.compute_zones = getattr(project, 'compute_zones', None)
        project.expiry_status = getattr(
            project, 'zone_expiry_status', None)
        project.expiry_date = getattr(
            project, 'zone_expiry_date', None)
        project.expiry_next_step = getattr(
            project, 'zone_expiry_next_step', None)
        project.expiry_ticket_id = getattr(
            project, 'zone_expiry_ticket_id', None)


def main():
    cmd = AllocationInstanceExpiryCmd()
    if cmd.args.status:
        cmd.print_status()
        return

    if cmd.args.set_admin:
        cmd.set_admin()
        return
    cmd.process_projects()


if __name__ == '__main__':
    main()
