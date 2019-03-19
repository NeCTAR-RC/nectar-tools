#!/usr/bin/env python

import logging

from nectar_tools.audit.projects import pt
from nectar_tools.audit.cmd import project_base
from nectar_tools import utils


LOG = logging.getLogger(__name__)


class PTAuditor(project_base.ProjectAuditor):

    @staticmethod
    def get_manager():
        return pt.ProjectTrialAuditor

    def is_valid_project(self, project):
        return utils.valid_project_trial(project)


def main():
    cmd = PTAuditor()
    cmd.run_audits()


if __name__ == '__main__':
    main()
