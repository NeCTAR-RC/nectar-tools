import contextlib
import os

import freezegun
from kubernetes import client as kube_client
import testtools

from nectar_tools import config

filename = os.path.realpath(
    os.path.join(os.path.dirname(__file__), 'tests/nectar-tools.conf')
)

CONF = config.CONF
config.init(args=[], default_config_files=[filename])


# The kubernetes client declares its models as pydantic classes and
# imports them lazily, on first access through kubernetes.client's
# module __getattr__. pydantic cannot build a schema for freezegun's
# FakeDatetime, so any model first imported while time is frozen fails
# to import, and a failure inside freezegun's start() leaves time
# frozen for the rest of the worker process. Two things trigger such
# imports:
#
# 1. freezegun's start() reads every attribute of every loaded module
#    to swap datetime references, which pulls in every kubernetes API
#    class and model. Skip the kubernetes modules in that scan.
# 2. Code under test building a kube client (ExpiryNotifier does this
#    in __init__) imports the API class it needs. Load the API classes
#    the code uses here, while datetime is still the real class.
freezegun.configure(extend_ignore_list=['kubernetes'])


def _load_kubernetes_models():
    for api in ('CoreV1Api', 'CustomObjectsApi'):
        getattr(kube_client, api)


_load_kubernetes_models()


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
