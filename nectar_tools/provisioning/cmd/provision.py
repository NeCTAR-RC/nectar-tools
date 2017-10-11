import logging

from nectar_tools import allocations
from nectar_tools import cmd_base
from nectar_tools import config

from nectar_tools.allocations import states


CONF = config.CONFIG
LOG = logging.getLogger(__name__)


class ProvisionCmd(cmd_base.CmdBase):

    def __init__(self):
        super(ProvisionCmd, self).__init__(log_filename='provisioning.log')

        noop = self.dry_run
        self.manager = allocations.AllocationManager(
            CONF.allocations.api_url,
            CONF.allocations.username,
            CONF.allocations.password,
            self.session,
            noop)

    def _get_allocation(self, allocation_id):
        allocation = self.manager.get_allocation(allocation_id)

        if allocation.status != states.APPROVED:
            allocation = self.manager.get_last_approved_allocation(
                parent_request_id=allocation_id)
        return allocation

    def provision_all_pending(self):
        allocations = self.manager.get_allocations(status=states.APPROVED,
                                                   provisioned=False)
        for allocation in allocations:
            try:
                self.provision_allocation(allocation.id)
            except Exception as e:
                LOG.exception(e)

    def provision_allocation(self, allocation_id):
        allocation = self._get_allocation(allocation_id)
        allocation.provision()

    def allocation_report(self, allocation_id):
        allocation = self._get_allocation(allocation_id)
        allocation.quota_report()

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


def main():
    cmd = ProvisionCmd()
    if cmd.args.all:
        cmd.provision_all_pending()
        return
    if cmd.args.report:
        cmd.allocation_report(cmd.args.allocation_id)
    else:
        cmd.provision_allocation(cmd.args.allocation_id)


if __name__ == '__main__':
    main()
