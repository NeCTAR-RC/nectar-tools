from nectar_tools.audit.cmd import base
from nectar_tools.audit.coe import cluster


class CluserAuditorCmd(base.AuditCmdBase):

    AUDITORS = [cluster.ClusterAuditor]

    def add_args(self):
        super(CluserAuditorCmd, self).add_args()
        self.parser.description = 'Cluser auditor'


def main():
    cmd = CluserAuditorCmd()
    cmd.run_audits()


if __name__ == '__main__':
    main()
