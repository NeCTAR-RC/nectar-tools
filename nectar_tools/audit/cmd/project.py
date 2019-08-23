#!/usr/bin/env python

from nectar_tools.audit.cmd import project_base
from nectar_tools.audit.projects import allocation
from nectar_tools import utils


class ProjectAllocationAuditorCmd(project_base.ProjectAuditorCmd):

    @staticmethod
    def get_manager():
        return allocation.ProjectAllocationAuditor

    def is_valid_project(self, project):
        return utils.valid_project_allocation(project)


def main():
    cmd = ProjectAllocationAuditorCmd()
    cmd.run_audits()


if __name__ == '__main__':
    main()
