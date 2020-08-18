from nectar_tools.audit.cmd import base
from nectar_tools.audit.coe import cluster


class ClusterAuditorCmd(base.AuditCmdBase):

    AUDITORS = [cluster.ClusterAuditor]

    def add_args(self):
        super(ClusterAuditorCmd, self).add_args()
        self.parser.description = 'Cluster auditor'


def main():
    cmd = ClusterAuditorCmd()
    cmd.run_audits()


if __name__ == '__main__':
    main()
