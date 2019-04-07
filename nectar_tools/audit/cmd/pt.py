#!/usr/bin/env python

from nectar_tools.audit.cmd import project_base
from nectar_tools.audit.projects import pt
from nectar_tools import utils


class PTAuditorCmd(project_base.ProjectAuditorCmd):

    @staticmethod
    def get_manager():
        return pt.ProjectTrialAuditor

    def is_valid_project(self, project):
        return utils.valid_project_trial(project)


def main():
    cmd = PTAuditorCmd()
    cmd.run_audits()


if __name__ == '__main__':
    main()
