import importlib.metadata
import logging
import os
import sys

import sentry_sdk

from nectar_tools import config


LOG = logging.getLogger(__name__)


def _get_release():
    try:
        version = importlib.metadata.version('nectar-tools')
    except importlib.metadata.PackageNotFoundError:
        # Not installed as a package, let sentry-sdk auto-detect
        # (e.g. the git commit of a source checkout)
        return None
    return f'nectar-tools@{version}'


@config.configurable('sentry', env_prefix='SENTRY')
def setup(dsn=None, environment=None):
    """Enable error reporting to GlitchTip/Sentry.

    A no-op unless a DSN is set in the [sentry] section of the config
    file (or the SENTRY_DSN environment variable). Once enabled, the
    sentry-sdk default integrations report unhandled exceptions and
    ERROR level log messages.
    """
    if not dsn:
        return False
    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=_get_release(),
        # GlitchTip does not support sessions
        auto_session_tracking=False,
    )
    sentry_sdk.set_tag('command', os.path.basename(sys.argv[0]))
    LOG.debug("Sentry error reporting enabled")
    return True
