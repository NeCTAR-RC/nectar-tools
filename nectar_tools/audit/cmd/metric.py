from nectar_tools.audit.cmd import base
from nectar_tools.audit.metric import cinder_pool
from nectar_tools.audit.metric import idp
from nectar_tools.audit.metric import instance
from nectar_tools.audit.metric import resource_provider
from nectar_tools.audit.metric import tempest_test


class MetricAuditorCmd(base.AuditCmdBase):

    AUDITORS = [instance.InstanceAuditor,
                resource_provider.ResourceProviderAuditor,
                tempest_test.TempestTestAuditor,
                idp.IDPAuditor, cinder_pool.CinderPoolAuditor]

    def add_args(self):
        super(MetricAuditorCmd, self).add_args()
        self.parser.description = 'Metric auditor'
        self.parser.add_argument('-s', '--site', default=None,
                                 help="Specify site name, by default it will "
                                 "check all sites (only appliable for "
                                 "instance consistency check).")
        self.parser.add_argument('-n', '--days-ago', default=3,
                                 help="Query any changed instances in the "
                                 "last x days, default is 3 (only applicable "
                                 "for instance consistency check).")

    def get_extra_args(self):
        return {'days_ago': self.args.days_ago,
                'site': self.args.site}


def main():
    cmd = MetricAuditorCmd()
    cmd.run_audits()


if __name__ == '__main__':
    main()
