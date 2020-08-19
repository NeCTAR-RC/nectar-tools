from nectar_tools.audit.cmd import base
from nectar_tools.audit.database import database


class DatabaseAuditorCmd(base.AuditCmdBase):

    AUDITORS = [database.DatabaseAuditor]

    def add_args(self):
        super(DatabaseAuditorCmd, self).add_args()
        self.parser.description = 'Database auditor'


def main():
    cmd = DatabaseAuditorCmd()
    cmd.run_audits()


if __name__ == '__main__':
    main()
