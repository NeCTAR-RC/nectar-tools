#!/usr/bin/env python

from nectar_tools.expiry.cmd import base
from nectar_tools.expiry import expirer


class AllocationExpiryCmd(base.ProjectExpiryCmd):

    @staticmethod
    def valid_project(project):
        return not expirer.PT_RE.match(project.name)

    def add_args(self):
        """Handle command-line options"""
        super(AllocationExpiryCmd, self).add_args()
        self.parser.add_argument('--ignore-no-allocation', action='store_true',
                        default=False,
                        help='Ignore the fact that no allocation exists'),

    def get_expirer(self, project):
        return expirer.AllocationExpirer(
            project=project,
            ks_session=self.session,
            dry_run=self.dry_run,
            disable_project=True,
            force_no_allocation=self.args.ignore_no_allocation,
            force_delete=self.args.force_delete)


def main():
    cmd = AllocationExpiryCmd()
    if cmd.args.status:
        cmd.print_status()
        return

    if cmd.args.set_admin:
        cmd.set_admin()
        return

    cmd.process_projects()


if __name__ == '__main__':
    main()
