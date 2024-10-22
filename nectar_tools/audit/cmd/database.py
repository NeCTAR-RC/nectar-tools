from nectar_tools.audit.cmd import base
from nectar_tools.audit.database import instance


class DatabaseAuditorCmd(base.AuditCmdBase):
    AUDITORS = [instance.DatabaseInstanceAuditor]

    def add_args(self):
        super().add_args()
        self.parser.description = 'Database auditor'


def main():
    cmd = DatabaseAuditorCmd()
    cmd.run_audits()


if __name__ == '__main__':
    main()
