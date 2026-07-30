import contextlib
import os

import testtools

from nectar_tools import config

filename = os.path.realpath(
    os.path.join(os.path.dirname(__file__), 'tests/nectar-tools.conf')
)

CONF = config.CONF
config.init(args=[], default_config_files=[filename])


@contextlib.contextmanager
def nested(*contexts):
    with contextlib.ExitStack() as stack:
        yield [stack.enter_context(c) for c in contexts]


class TestCase(testtools.TestCase):
    def setUp(self):
        super().setUp()
        # CONF.reset() in tearDown also unloads the config files, so
        # reload the test fixture for every test
        config.init(args=[], default_config_files=[filename])

    def tearDown(self):
        super().tearDown()
        CONF.reset()
