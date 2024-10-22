from nectar_tools.audit.cmd import base
from nectar_tools.audit.network import floating_ip


class NetworkAuditorCmd(base.AuditCmdBase):
    AUDITORS = [floating_ip.FloatingIPAuditor]

    def add_args(self):
        super().add_args()
        self.parser.description = 'Network auditor'


def main():
    cmd = NetworkAuditorCmd()
    cmd.run_audits()


if __name__ == '__main__':
    main()
