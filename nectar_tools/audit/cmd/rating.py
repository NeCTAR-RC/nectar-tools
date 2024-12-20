from nectar_tools.audit.cmd import base
from nectar_tools.audit.rating import flavor
from nectar_tools.audit.rating import project
from nectar_tools.audit.rating import reservation


class RatingAuditorCmd(base.AuditCmdBase):
    AUDITORS = [
        flavor.FlavorAuditor,
        project.ProjectAuditor,
        reservation.ReservationFlavorAuditor,
    ]

    def add_args(self):
        super().add_args()
        self.parser.description = 'Rating auditor'
        self.parser.add_argument(
            '-p', '--project-id', help='Project ID to process'
        )

    def get_extra_args(self):
        return {'project_id': self.args.project_id}


def main():
    cmd = RatingAuditorCmd()
    cmd.run_audits()


if __name__ == '__main__':
    main()
