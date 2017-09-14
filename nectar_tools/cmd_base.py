import logging

from nectar_tools import auth
from nectar_tools import config
from nectar_tools import log


CONFIG = config.CONFIG


class CmdBase(object):

    def __init__(self):
        self.parser = CONFIG.get_parser()
        self.add_args()
        self.args = CONFIG.parse()

        log.setup()

        self.dry_run = True
        if self.args.no_dry_run:
            self.dry_run = False

        self.session = auth.get_session()
        self.k_client = auth.get_keystone_client(self.session)

    def add_args(self):
        self.parser.add_argument('-y', '--no-dry-run', action='store_true',
                        help='Perform the actual actions, default is to \
                              only show what would happen')
