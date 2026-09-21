import os
from unittest import mock

from kubernetes import client as kube_client

from nectar_tools import auth
from nectar_tools.common import rabbitmq
from nectar_tools import exceptions
from nectar_tools import test

CONF = test.CONF


class KubeClientTests(test.TestCase):
    def test_get_kube_client(self):
        client = auth.get_kube_client()
        self.assertIsInstance(client, kube_client.CoreV1Api)
        conf = client.api_client.configuration
        self.assertEqual('https://k8s:6443', conf.host)
        self.assertEqual('Bearer', conf.api_key_prefix['authorization'])
        self.assertEqual('fake_token', conf.api_key['authorization'])

    def test_get_capi_client(self):
        client = auth.get_capi_client()
        self.assertIsInstance(client, kube_client.CustomObjectsApi)
        conf = client.api_client.configuration
        self.assertEqual('https://capi:6443', conf.host)
        self.assertEqual('Bearer', conf.api_key_prefix['authorization'])
        self.assertEqual('fake_token', conf.api_key['authorization'])

    def test_get_capi_client_env_fallback(self):
        CONF.set_override('host', None, group='capi_client')
        CONF.set_override('token', None, group='capi_client')
        env = {'CAPI_HOST': 'https://env-capi:6443', 'CAPI_TOKEN': 'env'}
        with mock.patch.dict(os.environ, env):
            client = auth.get_capi_client()
        conf = client.api_client.configuration
        self.assertEqual('https://env-capi:6443', conf.host)
        self.assertEqual('env', conf.api_key['authorization'])

    def test_get_capi_client_unconfigured(self):
        CONF.set_override('host', None, group='capi_client')
        CONF.set_override('token', None, group='capi_client')
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertRaises(exceptions.ConfigError, auth.get_capi_client)


class TroveRabbitMQClientTests(test.TestCase):
    def test_get_trove_rabbitmq_client(self):
        client = auth.get_trove_rabbitmq_client()
        self.assertIsInstance(client, rabbitmq.ManagementClient)
        self.assertEqual('https://rabbit:15671', client.url)
        self.assertEqual(('trove', 'secret'), client.session.auth)

    def test_get_trove_rabbitmq_client_unconfigured(self):
        CONF.set_override('rabbitmq_password', None, group='trove')
        self.assertRaises(
            exceptions.ConfigError, auth.get_trove_rabbitmq_client
        )
