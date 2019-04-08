from nectar_tools.audit.cmd import base
from nectar_tools.audit.metric import idp
from nectar_tools.audit.metric import instance
from nectar_tools.audit.metric import resource_provider
from nectar_tools.audit.metric import tempest_test


class MetricAuditorCmd(base.AuditCmdBase):

    AUDITORS = [instance.InstanceAuditor,
                resource_provider.ResourceProviderAuditor,
                tempest_test.TempestTestAuditor,
                idp.IDPAuditor]

    def add_args(self):
        super(MetricAuditorCmd, self).add_args()
        self.parser.description = 'Metric auditor'


def main():
    cmd = MetricAuditorCmd()
    cmd.run_audits()


if __name__ == '__main__':
    main()
