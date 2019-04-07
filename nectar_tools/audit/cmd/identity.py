from nectar_tools.audit.identity import role
from nectar_tools.audit.identity import user
from nectar_tools import cmd_base


class IdentityAuditorCmd(cmd_base.CmdBase):

    AUDITORS = [role.RoleAuditor, user.UserAuditor]

    def add_args(self):
        super(IdentityAuditorCmd, self).add_args()
        self.parser.description = 'Identity auditor'


def main():
    cmd = IdentityAuditorCmd()
    cmd.run_audits()


if __name__ == '__main__':
    main()
