import importlib.metadata
import os
import sys
from unittest import mock

from nectar_tools import config
from nectar_tools import sentry
from nectar_tools import test


DSN = 'https://key@glitchtip.example.com/1'
RELEASE = 'nectar-tools@1.0.0'


@mock.patch('nectar_tools.sentry._get_release', return_value=RELEASE)
@mock.patch('nectar_tools.sentry.sentry_sdk')
class TestSentrySetup(test.TestCase):
    def test_setup_no_config(self, mock_sdk, mock_release):
        self.assertFalse(sentry.setup())
        mock_sdk.init.assert_not_called()

    def test_setup_with_dsn(self, mock_sdk, mock_release):
        section = config.AttrDict(dsn=DSN, environment='testing')
        with mock.patch.dict(config.CONFIG, {'sentry': section}):
            self.assertTrue(sentry.setup())
        mock_sdk.init.assert_called_once_with(
            dsn=DSN,
            environment='testing',
            release=RELEASE,
            auto_session_tracking=False,
        )
        mock_sdk.set_tag.assert_called_once_with(
            'command', os.path.basename(sys.argv[0])
        )

    def test_setup_dsn_only(self, mock_sdk, mock_release):
        section = config.AttrDict(dsn=DSN)
        with mock.patch.dict(config.CONFIG, {'sentry': section}):
            self.assertTrue(sentry.setup())
        mock_sdk.init.assert_called_once_with(
            dsn=DSN,
            environment=None,
            release=RELEASE,
            auto_session_tracking=False,
        )

    def test_setup_dsn_from_environment(self, mock_sdk, mock_release):
        with mock.patch.dict(os.environ, {'SENTRY_DSN': DSN}):
            self.assertTrue(sentry.setup())
        mock_sdk.init.assert_called_once_with(
            dsn=DSN,
            environment=None,
            release=RELEASE,
            auto_session_tracking=False,
        )


class TestGetRelease(test.TestCase):
    def test_get_release(self):
        version = importlib.metadata.version('nectar-tools')
        self.assertEqual(f'nectar-tools@{version}', sentry._get_release())

    def test_get_release_not_installed(self):
        with mock.patch(
            'nectar_tools.sentry.importlib.metadata.version',
            side_effect=importlib.metadata.PackageNotFoundError,
        ):
            self.assertIsNone(sentry._get_release())
