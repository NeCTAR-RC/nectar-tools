import logging

from nectarallocationclient import states

from nectar_tools import cmd_base
from nectar_tools import config

from nectar_tools.provisioning import manager


CONF = config.CONFIG
LOG = logging.getLogger(__name__)


class ProvisionCmd(cmd_base.CmdBase):

    def __init__(self):
        super(ProvisionCmd, self).__init__(log_filename='provisioning.log')
        self.manager = manager.ProvisioningManager(self.session, self.dry_run)

    def _get_allocation(self, allocation_id):
        allocation = self.manager.client.allocations.get(allocation_id)

        if allocation.status != states.APPROVED:
            allocation = self.manager.client.allocations.get_last_approved(
                parent_request_id=allocation_id)
        return allocation

    def provision_all_pending(self):
        allocations = self.manager.client.allocations.list(
            status=states.APPROVED, provisioned=False,
            parent_request__isnull=True)
        for allocation in allocations:
            try:
                self.provision_allocation(allocation.id)
            except Exception as e:
                LOG.exception(e)

    def provision_allocation(self, allocation_id):
        allocation = self._get_allocation(allocation_id)
        self.manager.provision(allocation)

    def allocation_report(self, allocation_id):
        allocation = self._get_allocation(allocation_id)
        self.manager.quota_report(allocation)

    def set_quota(self, allocation_id):
        allocation = self._get_allocation(allocation_id)
        self.manager.set_quota(allocation)

    def add_args(self):
        """Handle command-line options"""
        super(ProvisionCmd, self).add_args()
        self.parser.description = 'Provision Allocations'
        project_group = self.parser.add_mutually_exclusive_group()
        project_group.add_argument('--all', action='store_true',
                                   help='Run over all pending allocations')
        project_group.add_argument('-a', '--allocation-id',
                                   help='Allocation ID to process')
        self.parser.add_argument('-r', '--report', action='store_true',
                                 help='Report current quota')
        self.parser.add_argument('-s', '--set-quota', action='store_true',
                                 help='Only set quota')
        self.parser.add_argument('-f', '--force', action='store_true',
                                 help='Force processing of allocation')
        self.parser.add_argument('-k', '--keep-dates', action='store_true',
                                 help='Don\'t modify start/end dates '
                                 '(requires --force)')
        self.parser.add_argument('-n', '--no-notify', action='store_true',
                                 help='Don\'t notify the user')


def main():
    cmd = ProvisionCmd()
    if cmd.args.force:
        cmd.manager.force = True
        if cmd.args.keep_dates:
            cmd.manager.keep_dates = True
    if cmd.args.no_notify:
        cmd.manager.no_notify = True

    if cmd.args.all:
        cmd.provision_all_pending()
        return
    if cmd.args.report:
        cmd.allocation_report(cmd.args.allocation_id)
    elif cmd.args.set_quota:
        cmd.set_quota(cmd.args.allocation_id)
    else:
        cmd.provision_allocation(cmd.args.allocation_id)


if __name__ == '__main__':
    main()
