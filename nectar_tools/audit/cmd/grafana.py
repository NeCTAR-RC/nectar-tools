from nectar_tools.audit.cmd import base
from nectar_tools.audit.grafana import team
from nectar_tools.audit.grafana import user


class GrafanaAuditorCmd(base.AuditCmdBase):

    AUDITORS = [team.TeamAuditor, user.UserAuditor]

    def add_args(self):
        super(GrafanaAuditorCmd, self).add_args()
        self.parser.description = 'Grafana auditor'


def main():
    cmd = GrafanaAuditorCmd()
    cmd.run_audits()


if __name__ == '__main__':
    main()
