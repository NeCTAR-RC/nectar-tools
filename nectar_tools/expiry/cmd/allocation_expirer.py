#!/usr/bin/env python

from nectar_tools.expiry.cmd import base
from nectar_tools.expiry import expirer


class AllocationManager(base.Manager):

    @staticmethod
    def valid_project(project):
        return not project.name.startswith('pt-')

    def add_args(self):
        """Handle command-line options"""
        super(AllocationManager, self).add_args()
        self.parser.add_argument('--ignore-no-allocation', action='store_true',
                        default=False,
                        help='Ignore the fact that no allocation exists'),

    def get_expirer(self, project):
        return expirer.AllocationExpirer(
            project=project,
            ks_session=self.session,
            dry_run=self.dry_run,
            force_no_allocation=self.args.ignore_no_allocation)


def main():
    manager = AllocationManager()
    if manager.args.status:
        manager.print_status()
        return

    if manager.args.set_admin:
        manager.set_admin()
        return

    manager.process_projects()


if __name__ == '__main__':
    main()
