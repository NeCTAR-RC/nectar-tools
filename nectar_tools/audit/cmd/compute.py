from nectar_tools.audit.cmd import base
from nectar_tools.audit.compute import flavor
from nectar_tools.audit.compute import instance


class ComputeAuditorCmd(base.AuditCmdBase):

    AUDITORS = [instance.InstanceAuditor, flavor.FlavorAuditor]

    def add_args(self):
        super(ComputeAuditorCmd, self).add_args()
        self.parser.description = 'Compute auditor'


def main():
    cmd = ComputeAuditorCmd()
    cmd.run_audits()


if __name__ == '__main__':
    main()
