import argparse
import configparser
import functools
import inspect
import logging
import os
import sys

from oslo_config import cfg


class AttrDict(dict):
    def __getattr__(self, attr):
        try:
            return self[attr]
        except KeyError:
            raise AttributeError(attr)


class ConfigBase(AttrDict):
    def read(self, filename):
        if not os.path.isfile(filename):
            print(f"Config file {filename} not found.", file=sys.stderr)
            return
        conf = configparser.ConfigParser()
        conf.read(filename)
        self['DEFAULT'] = AttrDict(conf.defaults())
        for section in conf.sections():
            self[section] = AttrDict(conf.items(section))


class Config(ConfigBase):
    def __init__(self):
        parser = argparse.ArgumentParser()
        parser.add_argument(
            '-c',
            '--config',
            help='Path of configuration file',
            default='/etc/nectar/tools.ini',
        )
        log_group = parser.add_mutually_exclusive_group()
        log_group.add_argument(
            '-d', '--debug', action='store_true', help='Show debug logging.'
        )
        log_group.add_argument('--loglevel', help='Set log level.')
        parser.add_argument(
            '-q',
            '--quiet',
            action='store_true',
            help="Don't print anything on the console.",
        )
        parser.add_argument(
            '--use_syslog',
            action='store_true',
            default=False,
            help="Log to syslog.",
        )
        self._parser = parser
        self._parsed_args = None

    def get_parser(self):
        return self._parser

    def parse(self):
        if self._parsed_args is None:
            self._parsed_args = self.get_parser().parse_args()
            self.read(self._parsed_args.config)

            if self._parsed_args.loglevel:
                loglevel = self._parsed_args.loglevel
                numeric_level = getattr(logging, loglevel.upper(), None)

                if not isinstance(numeric_level, int):
                    raise ValueError(f'Invalid log level: {loglevel}')

                self._parsed_args.loglevel = numeric_level

        return self._parsed_args

    @property
    def args(self):
        self.parse()
        return self._parsed_args


CONFIG = Config()
OSLO_CONF = cfg.CONF


def configurable(config_section, env_prefix=None):
    """Decorator that makes all options for the function configurable
    within the settings file.

       :param str section: The name given to the config section

    """

    def _configurable(func):
        # If there is a . assume that the name is fully qualified.
        args_list = inspect.getfullargspec(func)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            filtered_defaults = {}
            if env_prefix:
                for a in args_list.args:
                    env_name = (env_prefix + '_' + a).upper()
                    if env_name in os.environ:
                        filtered_defaults[a] = os.environ.get(env_name)
            conf = CONFIG.get(config_section, {})
            filtered_defaults.update(
                dict((a, conf.get(a)) for a in args_list.args if a in conf)
            )
            arguments = dict(
                zip(
                    reversed(args_list.args),
                    reversed(args_list.defaults or []),
                )
            )
            arguments.update(dict(zip(args_list.args, args)))
            arguments.update(kwargs)
            arguments.update(filtered_defaults)
            missing_args = [
                arg for arg in args_list.args if arg not in arguments
            ]
            if missing_args:
                raise Exception(
                    f'Error configuring function {func.__name__}: '
                    f'Configuration section {config_section} is missing values for {missing_args}'
                )

            return func(**arguments)

        return wrapper

    return _configurable
