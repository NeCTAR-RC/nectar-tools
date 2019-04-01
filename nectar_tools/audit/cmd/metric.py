from nectar_tools.audit.metric import instance
from nectar_tools.audit.metric import resource_provider
from nectar_tools import cmd_base


class MetricAuditor(cmd_base.CmdBase):

    def add_args(self):
        super(MetricAuditor, self).add_args()
        self.parser.description = 'Metric auditor'

    def run_audits(self):
        instance_auditor = instance.InstanceAuditor(ks_session=self.session)
        instance_auditor.run_all()
        rp_auditor = resource_provider.ResourceProviderAuditor(
            ks_session=self.session)
        rp_auditor.run_all()


def main():
    cmd = MetricAuditor()
    cmd.run_audits()


if __name__ == '__main__':
    main()
