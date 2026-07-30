import argparse
import logging
import os

from nectar_tools import auth
from nectar_tools import config
from nectar_tools import sentry


CONF = config.CONF


class CmdBase:
    def __init__(self):
        self.parser = argparse.ArgumentParser()
        self.add_args()
        self.args = self.parser.parse_args()

        config_files = []
        if self.args.config:
            config_files = [self.args.config]
        elif os.path.isfile(config.DEFAULT_CONFIG_FILE):
            config_files = [config.DEFAULT_CONFIG_FILE]

        config.init(default_config_files=config_files)

        if self.args.debug:
            CONF.set_override('debug', True)
        config.setup_logging(CONF)
        if self.args.quiet:
            logging.getLogger().setLevel(logging.ERROR)

        sentry.setup()

        self.dry_run = not self.args.no_dry_run

        self.session = auth.get_session()
        self.k_client = auth.get_keystone_client(self.session)

    def add_args(self):
        self.parser.add_argument(
            '-c',
            '--config',
            help='Path of configuration file '
            f'(default: {config.DEFAULT_CONFIG_FILE} if it exists)',
        )
        self.parser.add_argument(
            '-d',
            '--debug',
            action='store_true',
            help='Show debug logging.',
        )
        self.parser.add_argument(
            '-q',
            '--quiet',
            action='store_true',
            help='Only log errors.',
        )
        self.parser.add_argument(
            '-y',
            '--no-dry-run',
            action='store_true',
            help='Perform the actual actions, default is to \
                              only show what would happen',
        )
