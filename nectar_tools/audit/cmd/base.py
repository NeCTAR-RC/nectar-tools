import importlib
import logging
import sys

from nectar_tools import cmd_base


LOG = logging.getLogger(__name__)


class AuditCmdBase(cmd_base.CmdBase):

    def __init__(self):
        super(AuditCmdBase, self).__init__(log_filename='audit.log')

        self.list_not_run = False
        if self.args.list:
            self.list_not_run = True

        if self.args.check:
            try:
                module_str, class_method_str = self.args.check.split(':')
                class_str, method_str = class_method_str.split('.')
                module = importlib.import_module(module_str)
                auditor_class = getattr(module, class_str)
                auditor = auditor_class(ks_session=self.session,
                                        repair=self.args.repair)
                method = getattr(auditor, method_str)
                method()
                sys.exit(0)
            except Exception as e:
                LOG.exception(e)
                sys.exit(1)

    def run_audits(self, **kwargs):
        for auditor in self.AUDITORS:
            a = auditor(ks_session=self.session, repair=self.args.repair)
            a.run_all(list_not_run=self.list_not_run, **kwargs)

    def add_args(self):
        super(AuditCmdBase, self).add_args()
        self.parser.add_argument('-l', '--list', action='store_true',
                                 help="List audits but don't run them")
        self.parser.add_argument('-r', '--repair', action='store_true',
                                 help="Automated repair of some problems "
                                 "found by the audits. Needs the '-y' "
                                 "option to actually do the repairs")
        self.parser.add_argument('check', nargs='?',
                                 help="specific check to run")
