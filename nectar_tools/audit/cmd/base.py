import importlib
import logging
import sys

from nectar_tools import cmd_base


LOG = logging.getLogger(__name__)


class AuditCmdBase(cmd_base.CmdBase):

    def __init__(self):
        super(AuditCmdBase, self).__init__(log_filename='audit.log')
        self.list_not_run = self.args.list
        self.repair = self.args.repair
        extra_args = {
            'ensure_instance_consistency': {
                'days_ago': self.args.days_ago,
                'site': self.args.site}
        }

        if self.args.check:
            try:
                module_str, class_method_str = self.args.check.split(':')
                class_str, method_str = class_method_str.split('.')
                module = importlib.import_module(module_str)
                auditor_class = getattr(module, class_str)
                self.extra_args = extra_args.get(method_str)
                auditor = auditor_class(ks_session=self.session,
                                        repair=self.repair,
                                        dry_run=self.dry_run,
                                        extra_args=self.extra_args)
                method = getattr(auditor, method_str)
                method()
                sys.exit(0)
            except Exception as e:
                LOG.exception(e)
                sys.exit(1)

    def run_audits(self, **kwargs):
        for auditor in self.AUDITORS:
            a = auditor(ks_session=self.session,
                        repair=self.repair,
                        dry_run=self.dry_run)
            a.run_all(list_not_run=self.list_not_run, **kwargs)

    def add_args(self):
        super(AuditCmdBase, self).add_args()
        self.parser.add_argument('-l', '--list', action='store_true',
                                 help="List audits but don't run them")
        self.parser.add_argument('-r', '--repair', action='store_true',
                                 help="Tells audits to report automated "
                                 "repairs for (some) problems they find. "
                                 "Include the '-y' or '--no-dry-run' option "
                                 "to actually perform the repairs.")
        self.parser.add_argument('-s', '--site', default=None,
                                 help="Specify site name, by default it will "
                                 "check all sites (only appliable for "
                                 "instance consistency check).")
        self.parser.add_argument('-n', '--days-ago', default=3,
                                 help="Query any changed instances in the "
                                 "last x days, default is 3 (only applicable "
                                 "for instance consistency check).")
        self.parser.add_argument('check', nargs='?',
                                 help="specific check to run")
