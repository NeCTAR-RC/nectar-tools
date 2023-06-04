import logging
import sys

from nectar_tools import cmd_base
from nectar_tools import config

from nectar_tools.reports import manager


CONF = config.CONFIG
LOG = logging.getLogger(__name__)


class SUReportCmd(cmd_base.CmdBase):

    def __init__(self):
        super(SUReportCmd, self).__init__(log_filename='reports.log')
        self.manager = manager.SUReporter(self.session, self.dry_run)

    def add_args(self):
        """Handle command-line options"""
        super(SUReportCmd, self).add_args()
        self.parser.description = 'SUReport Allocations'
        project_group = self.parser.add_mutually_exclusive_group()
        project_group.add_argument('--all', action='store_true',
                                   help='Run over all pending allocations')
        project_group.add_argument('-a', '--allocation-id',
                                   type=int,
                                   help='Allocation ID to process')
        project_group.add_argument('--skip-to-allocation-id',
                                   type=int,
                                   required=False,
                                   default=None,
                                   help='Skip processing up to a given \
                                   allocation. Useful in cases where the \
                                   script has partially completed.')


def main():
    cmd = SUReportCmd()

    if cmd.args.all:
        cmd.manager.send_all_reports()
    elif cmd.args.skip_to_allocation_id:
        cmd.manager.send_all_reports(skip_to=cmd.args.skip_to_allocation_id)
    elif cmd.args.allocation_id:
        cmd.manager.send_reports(cmd.args.allocation_id)
    else:
        print("Please specify --all or -a argument")
        sys.exit(1)


if __name__ == '__main__':
    main()
