from nectar_tools.audit.cmd import base
from nectar_tools.audit.loadbalancer import loadbalancer


class LoadbalancerAuditorCmd(base.AuditCmdBase):

    AUDITORS = [loadbalancer.LoadBalancerAuditor]

    def add_args(self):
        super(LoadbalancerAuditorCmd, self).add_args()
        self.parser.description = 'Loadbalancer auditor'


def main():
    cmd = LoadbalancerAuditorCmd()
    cmd.run_audits()


if __name__ == '__main__':
    main()
