from nectar_tools import auth
from nectar_tools import config
from nectar_tools import log


CONFIG = config.CONFIG
OSLO_CONF = config.OSLO_CONF


class CmdBase(object):

    def __init__(self, log_filename=None):
        self.parser = CONFIG.get_parser()
        self.add_args()
        self.args = CONFIG.parse()

        log.setup(filename=log_filename)

        OSLO_CONF([], default_config_files=[self.args.config])

        self.list_not_run = False
        if self.args.list:
            self.list_not_run = True

        self.session = auth.get_session()
        self.k_client = auth.get_keystone_client(self.session)

    def run_audits(self):
        for auditor in self.AUDITORS:
            a = auditor(ks_session=self.session)
            a.run_all(list_not_run=self.list_not_run)

    def add_args(self):
        self.parser.add_argument('-l', '--list', action='store_true',
                                 help="List audits but don't run them")
