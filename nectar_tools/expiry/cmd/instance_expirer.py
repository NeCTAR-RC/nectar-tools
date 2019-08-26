#!/usr/bin/env python

from nectar_tools.expiry.cmd import base
from nectar_tools.expiry import expirer


class InstanceExpiryCmd(base.InstanceExpiryBaseCmd):

    @staticmethod
    def valid_project(project):
        if expirer.PT_RE.match(project.name) or \
           not hasattr(project, 'compute_zones') or \
           not project.compute_zones or \
           project.compute_zones == 'national':
            return False
        return True

    def add_args(self):
        super(InstanceExpiryCmd, self).add_args()

    def get_expirer(self, instance):
        return expirer.InstanceExpirer(instance=instance,
                                       ks_session=self.session,
                                       dry_run=self.dry_run,
                                       force_delete=self.args.force_delete)


def main():
    cmd = InstanceExpiryCmd()
    if cmd.args.status:
        cmd.print_status()
        return

    if cmd.args.set_admin:
        cmd.set_admin()
        return
    cmd.process_instances()


if __name__ == '__main__':
    main()
