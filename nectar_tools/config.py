import argparse
import configparser
import functools
import inspect
import os
import sys

from oslo_config import cfg


class AttrDict(dict):
    def __getattr__(self, attr):
        try:
            return self[attr]
        except KeyError:
            raise AttributeError(attr)


class Config(AttrDict):
    def __init__(self):
        parser = argparse.ArgumentParser()
        parser.add_argument('-c', '--config',
                            help='Path of configuration file',
                            default='/etc/nectar/tools.ini')
        parser.add_argument('-d', '--debug', action='store_true',
                            help='Show debug logging.')
        parser.add_argument('-q', '--quiet', action='store_true',
                            help="Don't print anything on the console.")
        self._parser = parser
        self._parsed_args = None

    def get_parser(self):
        return self._parser

    def parse(self):
        if self._parsed_args is None:
            self._parsed_args = self.get_parser().parse_args()
            self.read(self._parsed_args.config)
        return self._parsed_args

    @property
    def args(self):
        self.parse()
        return self._parsed_args

    def read(self, filename):
        if not os.path.isfile(filename):
            print("Config file %s not found." % filename, file=sys.stderr)
            return
        conf = configparser.SafeConfigParser()
        conf.read(filename)
        self['DEFAULT'] = AttrDict(conf.defaults())
        for section in conf.sections():
            self[section] = AttrDict(conf.items(section))


CONFIG = Config()
OSLO_CONF = cfg.CONF


def configurable(config_section, env_prefix=None):
    """Decorator that makes all options for the function configurable
    within the settings file.

       :param str section: The name given to the config section

    """
    def _configurable(func):
        # If there is a . assume that the name is fully qualified.
        args_list = inspect.getargspec(func)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            filtered_defaults = {}
            if env_prefix:
                for a in args_list.args:
                    env_name = (env_prefix + '_' + a).upper()
                    if env_name in os.environ:
                        filtered_defaults[a] = os.environ.get(env_name)
            conf = CONFIG.get(config_section, {})
            filtered_defaults.update(dict((a, conf.get(a))
                                     for a in args_list.args if a in conf))
            arguments = dict(zip(reversed(args_list.args),
                                 reversed(args_list.defaults or [])))
            arguments.update(dict(zip(args_list.args, args)))
            arguments.update(kwargs)
            arguments.update(filtered_defaults)
            missing_args = [arg for arg in args_list.args
                            if arg not in arguments]
            if missing_args:
                raise Exception(
                    'Error configuring function %s: '
                    'Configuration section %s is missing values for %s' %
                    (func.__name__, config_section, missing_args))

            return func(**arguments)
        return wrapper
    return _configurable
