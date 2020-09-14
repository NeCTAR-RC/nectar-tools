#!/usr/bin/env python

from nectar_tools.audit.allocation import allocation
from nectar_tools.audit.cmd import base


class AllocationAuditorCmd(base.AuditCmdBase):

    AUDITORS = [allocation.AllocationAuditor]

    @staticmethod
    def get_manager():
        return allocation.AllocationAuditor

    def add_args(self):
        super(AllocationAuditorCmd, self).add_args()
        self.parser.description = 'Allocation auditor'
        alloc_group = self.parser.add_mutually_exclusive_group(required=True)
        alloc_group.add_argument('--all', action='store_true',
                                 help='Run over all allocations')
        alloc_group.add_argument('-a', '--allocation-id',
                                 help='Allocation ID to process')


def main():
    cmd = AllocationAuditorCmd()
    if cmd.args.all:
        cmd.run_audits(allocation_id=None)
    else:
        cmd.run_audits(allocation_id=cmd.args.allocation_id)


if __name__ == '__main__':
    main()
