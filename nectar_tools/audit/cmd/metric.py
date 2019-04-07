from nectar_tools.audit.metric import instance
from nectar_tools.audit.metric import resource_provider
from nectar_tools import cmd_base


class MetricAuditor(cmd_base.CmdBase):

    AUDITORS = [instance.InstanceAuditor,
                resource_provider.ResourceProviderAuditor]

    def add_args(self):
        super(MetricAuditor, self).add_args()
        self.parser.description = 'Metric auditor'


def main():
    cmd = MetricAuditor()
    cmd.run_audits()


if __name__ == '__main__':
    main()
