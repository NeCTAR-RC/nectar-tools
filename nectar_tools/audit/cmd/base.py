from nectar_tools import cmd_base


class AuditCmdBase(cmd_base.CmdBase):

    def __init__(self, log_filename=None):
        super(AuditCmdBase, self).__init__(log_filename)

        self.list_not_run = False
        if self.args.list:
            self.list_not_run = True

    def run_audits(self):
        for auditor in self.AUDITORS:
            a = auditor(ks_session=self.session)
            a.run_all(list_not_run=self.list_not_run)

    def add_args(self):
        super(AuditCmdBase, self).add_args()
        self.parser.add_argument('-l', '--list', action='store_true',
                                 help="List audits but don't run them")
