import contextlib
import os
import testtools

from nectar_tools import config

filename = os.path.realpath(
    os.path.join(os.path.dirname(__file__), 'tests/nectar-tools.conf')
)

CONF = config.CONFIG
CONF.read(filename)
OSLO_CONF = config.OSLO_CONF
OSLO_CONF([], default_config_files=[filename])


@contextlib.contextmanager
def nested(*contexts):
    with contextlib.ExitStack() as stack:
        yield [stack.enter_context(c) for c in contexts]


class TestCase(testtools.TestCase):
    def setUp(self):
        super().setUp()
