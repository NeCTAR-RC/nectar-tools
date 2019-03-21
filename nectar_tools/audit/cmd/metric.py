from nectar_tools import cmd_base
from nectar_tools.audit.metric import instance


class MetricAuditor(cmd_base.CmdBase):

    def add_args(self):
        super(MetricAuditor, self).add_args()
        self.parser.description = 'Metric auditor'

    def run_audits(self):
        auditor = instance.InstanceAuditor(ks_session=self.session)
        auditor.run_all()


def main():
    cmd = MetricAuditor()
    cmd.run_audits()


if __name__ == '__main__':
    main()
