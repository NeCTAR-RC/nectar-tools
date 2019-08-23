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
        self.parser.add_argument('-a', '--allocation-id',
                                 help='Allocation ID to process')

    def run_audits(self):
        for auditor in self.AUDITORS:
            a = auditor(ks_session=self.session)
            a.run_all(list_not_run=self.list_not_run,
                      allocation_id=self.args.allocation_id)


def main():
    cmd = AllocationAuditorCmd()
    cmd.run_audits()


if __name__ == '__main__':
    main()
