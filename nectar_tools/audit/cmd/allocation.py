#!/usr/bin/env python

import logging

from nectar_tools import cmd_base
from nectar_tools.audit.projects import allocation
from nectar_tools import utils

LOG = logging.getLogger(__name__)


class AllocationAuditor(cmd_base.CmdBase):

    def run_audits(self):
        for project in self.k_client.projects.list():
            if utils.valid_project_allocation(project):
                auditor = allocation.ProjectAllocationAuditor(
                    ks_session=self.session, project=project)
                auditor.run_all()


def main():
    cmd = AllocationAuditor()
    cmd.run_audits()


if __name__ == '__main__':
    main()
