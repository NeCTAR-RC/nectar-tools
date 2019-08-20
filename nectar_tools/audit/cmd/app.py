from nectar_tools.audit.app import environment
from nectar_tools.audit.cmd import base


class AppAuditorCmd(base.AuditCmdBase):

    AUDITORS = [environment.AppAuditor]

    def add_args(self):
        super(AppAuditorCmd, self).add_args()
        self.parser.description = 'Application catalog auditor'


def main():
    cmd = AppAuditorCmd()
    cmd.run_audits()


if __name__ == '__main__':
    main()
