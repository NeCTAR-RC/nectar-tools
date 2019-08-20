from nectar_tools.audit.app_catalog import environment
from nectar_tools.audit.cmd import base


class AppCatalogAuditorCmd(base.AuditCmdBase):

    AUDITORS = [environment.EnvironmentAuditor]

    def add_args(self):
        super(AppCatalogAuditorCmd, self).add_args()
        self.parser.description = 'Application catalog auditor'


def main():
    cmd = AppCatalogAuditorCmd()
    cmd.run_audits()


if __name__ == '__main__':
    main()
