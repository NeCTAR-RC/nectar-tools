from nectar_tools.audit.aggregate import aggregate
from nectar_tools.audit.cmd import base


class AggregateAuditorCmd(base.AuditCmdBase):
    AUDITORS = [aggregate.AggregateAuditor]

    def add_args(self):
        super().add_args()
        self.parser.description = 'Host aggregate routing auditor'
        self.parser.add_argument(
            '--availability-zone',
            required=True,
            help='Availability zone to audit (required).',
        )
        self.parser.add_argument(
            '--report-output',
            help='Write a routing report to this path (extension is added '
            'per --report-format).',
        )
        self.parser.add_argument(
            '--report-format',
            choices=['html', 'md', 'both'],
            default='html',
            help='Report format when --report-output is given.',
        )

    def get_extra_args(self):
        return {'availability_zone': self.args.availability_zone}

    def run_audits(self, **kwargs):
        # The base run_audits does not plumb extra_args through to the
        # auditor, so build it here with the required availability zone.
        extra_args = self.get_extra_args()
        auditor = None
        for auditor_class in self.AUDITORS:
            auditor = auditor_class(
                ks_session=self.session,
                dry_run=self.dry_run,
                limit=self.limit,
                **extra_args,
            )
            auditor.run_all(list_not_run=self.list_not_run, **kwargs)

        if self.args.report_output and not self.list_not_run:
            # Reuse the auditor instance so the gathered graph is shared.
            written = auditor.generate_report(
                self.args.report_output, fmt=self.args.report_format
            )
            for path in written:
                print(f"Wrote report: {path}")


def main():
    cmd = AggregateAuditorCmd()
    cmd.run_audits()


if __name__ == '__main__':
    main()
