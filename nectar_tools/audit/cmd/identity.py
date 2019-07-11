from nectar_tools.audit.cmd import base
from nectar_tools.audit.identity import project
from nectar_tools.audit.identity import role
from nectar_tools.audit.identity import user


class IdentityAuditorCmd(base.AuditCmdBase):

    AUDITORS = [role.RoleAuditor, user.UserAuditor, project.ProjectAuditor]

    def add_args(self):
        super(IdentityAuditorCmd, self).add_args()
        self.parser.description = 'Identity auditor'


def main():
    cmd = IdentityAuditorCmd()
    cmd.run_audits()


if __name__ == '__main__':
    main()
