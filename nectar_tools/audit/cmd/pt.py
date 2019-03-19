#!/usr/bin/env python

import logging

from nectar_tools.audit.projects import pt
from nectar_tools import cmd_base
from nectar_tools import utils


LOG = logging.getLogger(__name__)


class PTAuditor(cmd_base.CmdBase):

    def run_audits(self):
        for project in self.k_client.projects.list():
            if utils.valid_project_trial(project):
                auditor = pt.ProjectTrialAuditor(ks_session=self.session,
                                                 project=project)
                auditor.run_all()


def main():
    cmd = PTAuditor()
    cmd.run_audits()


if __name__ == '__main__':
    main()
