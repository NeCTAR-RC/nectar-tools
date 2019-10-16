#!/usr/bin/env python3

import prettytable

from nectar_tools.expiry.cmd import base
from nectar_tools.expiry import expirer


class AllocationInstanceExpiryCmd(base.ProjectExpiryBaseCmd):

    @staticmethod
    def valid_project(project):
        # rule out following projects:
        # pt project, project without compute_zones provisioned,
        # allocation expiry on-going project,
        if expirer.PT_RE.match(project.name) or \
           not hasattr(project, 'compute_zones') or \
           (hasattr(project, 'expiry_status')
            and project.expiry_status != ''):
            return False
        return True

    def get_expirer(self, project):
        return expirer.AllocationInstanceExpirer(
            project=project,
            ks_session=self.session,
            dry_run=self.dry_run,
            force_delete=self.args.force_delete)

    def print_status(self):
        pt = prettytable.PrettyTable(['Name', 'Project ID', 'Allocation Zones',
                                      'Expiry date', 'Expiry status',
                                      'Ticket ID'])
        for project in self.projects:
            if self.valid_project(project):
                self.project_zones_set_defaults(project)
                pt.add_row([project.name, project.id, project.compute_zones,
                            project.zone_expiry_next_step,
                            project.zone_expiry_status,
                            project.zone_expiry_ticket_id])
        print(pt)

    @staticmethod
    def project_zones_set_defaults(project):
        project.compute_zones = getattr(project, 'compute_zones', None)
        project.zone_expiry_status = getattr(
            project, 'zone_expiry_status', None)
        project.zone_expiry_next_step = getattr(
            project, 'zone_expiry_next_step', None)
        project.zone_expiry_ticket_id = getattr(
            project, 'zone_expiry_ticket_id', None)


def main():
    cmd = AllocationInstanceExpiryCmd()
    if cmd.args.status:
        cmd.print_status()
        return

    cmd.process_projects()


if __name__ == '__main__':
    main()
