import os
import sys
from unittest import mock

from nectar_tools import config
from nectar_tools import sentry
from nectar_tools import test


DSN = 'https://key@glitchtip.example.com/1'


@mock.patch('nectar_tools.sentry.sentry_sdk')
class TestSentrySetup(test.TestCase):
    def test_setup_no_config(self, mock_sdk):
        self.assertFalse(sentry.setup())
        mock_sdk.init.assert_not_called()

    def test_setup_with_dsn(self, mock_sdk):
        section = config.AttrDict(dsn=DSN, environment='testing')
        with mock.patch.dict(config.CONFIG, {'sentry': section}):
            self.assertTrue(sentry.setup())
        mock_sdk.init.assert_called_once_with(
            dsn=DSN, environment='testing', auto_session_tracking=False
        )
        mock_sdk.set_tag.assert_called_once_with(
            'command', os.path.basename(sys.argv[0])
        )

    def test_setup_dsn_only(self, mock_sdk):
        section = config.AttrDict(dsn=DSN)
        with mock.patch.dict(config.CONFIG, {'sentry': section}):
            self.assertTrue(sentry.setup())
        mock_sdk.init.assert_called_once_with(
            dsn=DSN, environment=None, auto_session_tracking=False
        )

    def test_setup_dsn_from_environment(self, mock_sdk):
        with mock.patch.dict(os.environ, {'SENTRY_DSN': DSN}):
            self.assertTrue(sentry.setup())
        mock_sdk.init.assert_called_once_with(
            dsn=DSN, environment=None, auto_session_tracking=False
        )
