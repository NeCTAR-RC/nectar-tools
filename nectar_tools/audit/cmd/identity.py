from nectar_tools.audit.identity import role
from nectar_tools.audit.identity import user
from nectar_tools import cmd_base


class IdentityAuditorCmd(cmd_base.CmdBase):

    def add_args(self):
        super(IdentityAuditorCmd, self).add_args()
        self.parser.description = 'Identity auditor'

    def run_audits(self):
        role_auditor = role.RoleAuditor(self.session)
        role_auditor.run_all()
        user_auditor = user.UserAuditor(self.session)
        user_auditor.run_all()


def main():
    cmd = IdentityAuditorCmd()
    cmd.run_audits()


if __name__ == '__main__':
    main()
