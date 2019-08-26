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

        self.dry_run = True
        if self.args.no_dry_run:
            self.dry_run = False

        self.session = auth.get_session()
        self.k_client = auth.get_keystone_client(self.session)
        self.n_client = auth.get_nova_client(self.session)
        self.a_client = auth.get_allocation_client(self.session)

    def add_args(self):
        self.parser.add_argument('-y', '--no-dry-run', action='store_true',
                        help='Perform the actual actions, default is to \
                              only show what would happen')
