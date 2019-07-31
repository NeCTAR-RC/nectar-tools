from nectar_tools.audit.cmd import base
from nectar_tools.audit.dns import zone


class DnsAuditorCmd(base.AuditCmdBase):

    AUDITORS = [zone.DnsAuditor]

    def add_args(self):
        super(DnsAuditorCmd, self).add_args()
        self.parser.description = 'DNS auditor'


def main():
    cmd = DnsAuditorCmd()
    cmd.run_audits()


if __name__ == '__main__':
    main()
