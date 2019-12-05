import logging.config
from os import path

from nectar_tools import config

CONF = config.CONFIG


@config.configurable('logging')
def setup(filename=None, file_level='INFO', console_level='INFO',
          enabled_loggers=None, log_format=None, log_dir=None,
          use_syslog=False):
    if log_format is None:
        log_format = '%(asctime)s %(name)s %(levelname)s %(message)s'
    if enabled_loggers is None:
        enabled_loggers = ['nectar_tools']
    if isinstance(enabled_loggers, str):
        enabled_loggers = enabled_loggers.split(',')

    if CONF.args.debug:
        console_level = 'DEBUG'
        file_level = 'DEBUG'
    if CONF.args.quiet:
        console_level = None
    if CONF.args.use_syslog or CONF.logging.use_syslog:
        use_syslog = True
    # When set via config this comes in as a string
    use_syslog = bool(use_syslog)

    config = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'simple': {
                'format': log_format,
            },
            'rsyslog': {
                'format': '%(filename)s: ' + log_format,
            },
        },
        'handlers': {
            'null': {
                'class': 'logging.NullHandler',
            },
            'console': {
                'level': console_level,
                'class': 'logging.StreamHandler',
                'formatter': 'simple'
            },
            'file': {
                'level': file_level,
                'class': 'logging.FileHandler',
                'formatter': 'simple',
                'filename': filename,
            },
            'syslog': {
                'level': file_level,
                'class': 'logging.handlers.SysLogHandler',
                'formatter': 'rsyslog',
                'address': '/dev/log',
            },
        },
    }
    handlers = ['console', 'file', 'null', 'syslog']
    if log_dir and filename:
        config['handlers']['file']['filename'] = path.join(log_dir, filename)
    else:
        del config['handlers']['file']
        handlers.remove('file')

    if not use_syslog:
        del config['handlers']['syslog']
        handlers.remove('syslog')
    # Disable console logging if it's not used.
    if not console_level:
        del config['handlers']['console']
        handlers.remove('console')

    config['loggers'] = {}
    for module in enabled_loggers:
        config['loggers'][module] = {
            'handlers': handlers,
            'level': 'DEBUG',
            'propagate': False,
        }
    logging.config.dictConfig(config)
