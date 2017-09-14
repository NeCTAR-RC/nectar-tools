from nectar_tools import allocations
from nectar_tools import cmd_base
from nectar_tools import config


CONF = config.CONFIG


class ProvisionCmd(cmd_base.CmdBase):

    def __init__(self):
        super(ProvisionCmd, self).__init__()
        self.manager = allocations.AllocationManager(
            CONF.allocations.api_url,
            CONF.allocations.username,
            CONF.allocations.password,
            self.session)

    def provision_allocation(self, allocation_id):
        allocation = self.manager.get_allocation(allocation_id)

        allocation.provision()

    def add_args(self):
        """Handle command-line options"""
        super(ProvisionCmd, self).add_args()
        self.parser.description = 'Provision Allocations'
        project_group = self.parser.add_mutually_exclusive_group()
        project_group.add_argument('--all', action='store_true',
                            help='Run over all pending allocations')
        project_group.add_argument('-a', '--allocation-id',
                            help='Allocation ID to process')


def main():
    cmd = ProvisionCmd()
    cmd.provision_allocation(cmd.args.allocation_id)


if __name__ == '__main__':
    main()
