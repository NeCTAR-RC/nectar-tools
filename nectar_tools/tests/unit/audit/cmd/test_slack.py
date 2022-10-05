import contextlib
import logging
import re
import unittest

from nectar_tools.audit.cmd import slack
from nectar_tools.tests import fakes


LOG = logging.getLogger(__name__)


# There is something odd about 'nectar_tools.test.TestCase' that is
# breaking 'with self.assertRaises(Exception) as cm:'

class SlackFilterSpecTests(unittest.TestCase):

    def test_construct(self):
        with self.assertRaisesRegex(
                slack.SlackConfigError,
                "Empty filter spec for 'foo'"):
            slack.SlackFilterSpec('', 'foo', ',', '=')

        with self.assertRaisesRegex(
                slack.SlackConfigError,
                "Key or value missing for 'key=' in filter spec for 'foo'"):
            slack.SlackFilterSpec('key=', 'foo', ',', '=')

        with self.assertRaisesRegex(
                slack.SlackConfigError,
                "Key or value missing for '=value' in filter spec for 'foo'"):
            slack.SlackFilterSpec('=value', 'foo', ',', '=')

        with self.assertRaisesRegex(
                slack.SlackConfigError,
                "Expected key-value pair but got 'lock' in "
                "filter spec for 'foo'"):
            slack.SlackFilterSpec('lock', 'foo', ',', '=')

        with self.assertRaisesRegex(
                slack.SlackConfigError,
                "Expected key-value pair but got 'key=value=' in "
                "filter spec for 'foo'"):
            slack.SlackFilterSpec('key=value=', 'foo', ',', '=')

        self.assertEqual(re.compile("Hi"),
                         slack.SlackFilterSpec('msg=Hi', 'foo', ',', '=')
                         .message_regex)
        self.assertEqual([],
                         slack.SlackFilterSpec('msg=Hi', 'foo', ',', '=')
                         .arg_regexes)
        self.assertEqual({},
                         slack.SlackFilterSpec('msg=Hi', 'foo', ',', '=')
                         .extra_regexes)
        self.assertEqual([re.compile('a'), re.compile('b'), re.compile("c")],
                         slack.SlackFilterSpec(
                             'msg=Hi,0=a,1=b,2=c', 'foo', ',', '=')
                         .arg_regexes)
        self.assertEqual([None, re.compile('b'), None, re.compile('d')],
                         slack.SlackFilterSpec(
                             'msg=Hi,1=b,3=d', 'foo', ',', '=')
                         .arg_regexes)
        self.assertEqual({'a': re.compile('1'), 'b': re.compile('2')},
                         slack.SlackFilterSpec(
                             'msg=Hi,a=1,b=2', 'foo', ',', '=')
                         .extra_regexes)

    def test_filter(self):
        TEST_LOG = logging.getLogger('a.b.c')

        # Filter matching on the msg
        spec = slack.SlackFilterSpec('msg=Hi', 'foo', ',', '=')
        record = TEST_LOG.makeRecord('a.b.c', logging.INFO, "code.py", 42,
                                     "Hi", [], None)
        self.assertTrue(spec.filter(record))
        record = TEST_LOG.makeRecord('a.b.c', logging.INFO, "code.py", 42,
                                     "Hi", [1, 2, 3], None)
        self.assertTrue(spec.filter(record))
        record = TEST_LOG.makeRecord('a.b.c', logging.INFO, "code.py", 42,
                                     "Ho", [1, 2, 3], None)
        self.assertFalse(spec.filter(record))

        # Filter matching on the args
        spec = slack.SlackFilterSpec('msg=Hi,0=1,1=2', 'foo', ',', '=')
        record = TEST_LOG.makeRecord('a.b.c', logging.INFO, "code.py", 42,
                                     "Hi", [1, 2, 3], None)
        self.assertTrue(spec.filter(record))
        record = TEST_LOG.makeRecord('a.b.c', logging.INFO, "code.py", 42,
                                     "Hi", [0, 2, 3], None)
        self.assertFalse(spec.filter(record))
        record = TEST_LOG.makeRecord('a.b.c', logging.INFO, "code.py", 42,
                                     "Hi", [1], None)
        self.assertFalse(spec.filter(record))
        record = TEST_LOG.makeRecord('a.b.c', logging.INFO, "code.py", 42,
                                     "Hi", [1, None], None)
        self.assertFalse(spec.filter(record))

        # Filter matching on 'extra' parameter
        spec = slack.SlackFilterSpec('msg=Hi,site=ardc', 'foo', ',', '=')
        record = TEST_LOG.makeRecord('a.b.c', logging.INFO, "code.py", 42,
                                     "Hi", [1, 2, 3], None)
        self.assertFalse(spec.filter(record))
        record = TEST_LOG.makeRecord('a.b.c', logging.INFO, "code.py", 42,
                                     "Hi", [1, 2, 3], None,
                                     extra={})

        self.assertFalse(spec.filter(record))
        record = TEST_LOG.makeRecord('a.b.c', logging.INFO, "code.py", 42,
                                     "Hi", [1, 2, 3], None,
                                     extra={'extra': {'site': 'ardc'}})
        self.assertTrue(spec.filter(record))
        record = TEST_LOG.makeRecord('a.b.c', logging.INFO, "code.py", 42,
                                     "Hi", [1, 2, 3], None,
                                     extra={'extra': {'site': 'intersect'}})
        self.assertFalse(spec.filter(record))


class SlackLogHandlerTests(unittest.TestCase):

    def test_constructor(self):
        handler = slack.SlackLogHandler(
            object(), "name", "https://example.com",
            "slack-channel", "slack-group", logging.INFO, "a.b.c", [], False)
        self.assertEqual('a.b.c', handler.get_name())

    def test_filter(self):
        pass


# We need the following because configuring the slack handlers messes
# with the (real) root logger.  The changes need to be undone to prevent
# the tests interfering with each other.
@contextlib.contextmanager
def managed_config(config, categories_arg):
    config.configure_handlers(categories_arg)
    try:
        yield config
    finally:
        config.unconfigure_handlers()


class SlackConfigTests(unittest.TestCase):

    CONTENT = """
    [DEFAULT]
    slack_webhook = https://slack
    slack_channel = coreservices
    slack_group = weebles
    log_level = INFO
    separator_1 = ,
    separator_2 = =
    state_dir =

    [allocations]
    slack_channel = coreservices
    slack_group = alloc-{site}
    log_level = WARNING
    filter_0 = msg=Hi,0=a,other=other
    filter_1 = msg=Ho,1=b,other=other
    filter_2 = msg=Hum,0=c,other=other,alt=Weeble - %%s
    incremental = True
    """

    @unittest.mock.patch("nectar_tools.config.os.path.isfile")
    @unittest.mock.patch("nectar_tools.audit.cmd.slack.logging.getLogger")
    def test_configure(self, mock_get, mock_isfile):
        mock_logger = unittest.mock.MagicMock(spec=logging.Logger)
        mock_get.return_value = mock_logger
        mock_isfile.return_value = True

        with unittest.mock.patch('configparser.open',
                   unittest.mock.mock_open(read_data=self.CONTENT)) as m:
            config = slack.SlackConfig('blah', reset=True)
        m.assert_called_once_with("blah", encoding=None)
        mock_isfile.assert_called_once_with("blah")

        handlers = config.create_handlers(["allocations"])
        self.assertEqual(1, len(handlers))
        handler = handlers[0]
        self.assertEqual('https://slack', handler.webhook)
        self.assertEqual('allocations', handler.category)
        self.assertEqual('coreservices', handler.channel)
        self.assertEqual('alloc-{site}', handler.group)
        self.assertTrue(handler.incremental)
        self.assertEqual(3, len(handler.or_filters))
        filter_0, filter_1, filter_2 = handler.or_filters
        self.assertEqual(re.compile("Hi"), filter_0.message_regex)
        self.assertEqual([re.compile("a")],
                         filter_0.arg_regexes)
        self.assertEqual({'other': re.compile("other")},
                         filter_0.extra_regexes)
        self.assertIsNone(filter_0.alternative_message)
        self.assertEqual(re.compile("Ho"), filter_1.message_regex)
        self.assertEqual([None, re.compile("b")],
                         filter_1.arg_regexes)
        self.assertEqual({'other': re.compile("other")},
                         filter_1.extra_regexes)
        self.assertIsNone(filter_1.alternative_message)
        self.assertEqual(re.compile("Hum"), filter_2.message_regex)
        self.assertEqual([re.compile("c")],
                         filter_2.arg_regexes)
        self.assertEqual({'other': re.compile("other")},
                         filter_2.extra_regexes)
        self.assertEqual("Weeble - %s", filter_2.alternative_message)

        with managed_config(config, "allocations"):
            mock_logger.addHandler.assert_called_once()
            self.assertEqual(1, len(config.handlers))

            # Should only work once
            with self.assertRaises(slack.SlackConfigError):
                config.configure_handlers("allocations")

    @unittest.mock.patch("nectar_tools.config.os.path.isfile")
    def test_handler(self, mock_isfile):
        mock_isfile.return_value = True

        with unittest.mock.patch('configparser.open',
                   unittest.mock.mock_open(read_data=self.CONTENT)):
            config = slack.SlackConfig('blah', reset=True)

        with managed_config(config, "allocations"):
            my_logger = logging.getLogger('nectar_tools')
            with unittest.mock.patch.object(config.handlers[0], 'emit') as m:
                my_logger.warning("Hi: %s", "a",
                                  extra={'extra': {'other': 'other'}})
                m.assert_called_once()

                m.reset_mock()
                my_logger.warning("Ho: %s, %s", "x", "b",
                                  extra={'extra': {'other': 'other'}})
                m.assert_called_once()

                m.reset_mock()
                my_logger.debug("Hi: %s", "a",
                                extra={'extra': {'other': 'other'}})
                m.assert_not_called()

                m.reset_mock()
                my_logger.warning("Bye: %s", "a",
                                  extra={'extra': {'other': 'other'}})
                m.assert_not_called()

                m.reset_mock()
                my_logger.warning("Hi: %s", "b",
                                  extra={'extra': {'other': 'other'}})
                m.assert_not_called()

                m.reset_mock()
                my_logger.warning("Bye: %s", "a",
                                  extra={'extra': {'other': 'same'}})
                m.assert_not_called()

    @unittest.mock.patch("nectar_tools.config.os.path.isfile")
    @unittest.mock.patch("nectar_tools.audit.cmd.slack.requests.post")
    def test_notifier(self, mock_post, mock_isfile):
        mock_isfile.return_value = True
        mock_post.return_value = fakes.FakeResponse()

        with unittest.mock.patch('configparser.open',
                   unittest.mock.mock_open(read_data=self.CONTENT)):
            config = slack.SlackConfig('blah', reset=True)

        with managed_config(config, "allocations"):
            my_logger = logging.getLogger('nectar_tools')
            my_logger.warning("Hi: %s", "a",
                              extra={'extra': {
                                  'other': 'other',
                                  'site': 'unseen'}})
            mock_post.assert_called_once_with(
                'https://slack',
                '{"type": "mrkdwn", "text": "@alloc-unseen - Hi: a", '
                '"link_names": 1}')

            mock_post.reset_mock()
            my_logger.warning("Hum: %s", "c",
                              extra={'extra': {
                                  'other': 'other',
                                  'site': 'unseen'}})
            mock_post.assert_called_once_with(
                'https://slack',
                '{"type": "mrkdwn", "text": "@alloc-unseen - Weeble - c", '
                '"link_names": 1}')

            # Repeat log should be de-duped
            mock_post.reset_mock()
            my_logger.warning("Hum: %s", "c",
                              extra={'extra': {
                                  'other': 'other',
                                  'site': 'unseen'}})
            mock_post.assert_not_called()
