from nectar_tools.audit.cmd import base
from nectar_tools.audit.placement import resource_provider


class PlacementAuditorCmd(base.AuditCmdBase):

    AUDITORS = [resource_provider.ResourceProviderAuditor]

    def add_args(self):
        super(PlacementAuditorCmd, self).add_args()
        self.parser.description = 'Placement auditor'


def main():
    cmd = PlacementAuditorCmd()
    cmd.run_audits()


if __name__ == '__main__':
    main()
