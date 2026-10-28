import os
from unittest import mock

from keystoneauth1 import loading as ks_loading
from keystoneauth1 import session as ks_session
from kubernetes import client as kube_client

from nectar_tools import auth
from nectar_tools.common import rabbitmq
from nectar_tools import exceptions
from nectar_tools import test

CONF = test.CONF


class SessionTests(test.TestCase):
    def test_get_session_service_auth(self):
        CONF.set_override('auth_type', 'password', group='service_auth')
        auth_plugin = mock.Mock()
        with mock.patch.object(
            ks_loading,
            'load_auth_from_conf_options',
            return_value=auth_plugin,
        ) as load_auth:
            sess = auth.get_session()
        load_auth.assert_called_once_with(CONF, 'service_auth')
        self.assertIsInstance(sess, ks_session.Session)
        self.assertIs(auth_plugin, sess.auth)
        self.assertEqual(auth.CONNECT_RETRIES, sess._connect_retries)

    def test_get_session_service_auth_system_scope(self):
        CONF.set_override('auth_type', 'password', group='service_auth')
        with mock.patch.object(
            ks_loading, 'load_auth_from_conf_options'
        ) as load_auth:
            sess = auth.get_session(system_scope='all')
        load_auth.assert_called_once_with(
            CONF,
            'service_auth',
            system_scope='all',
            project_name=None,
            project_id=None,
            project_domain_name=None,
            project_domain_id=None,
        )
        self.assertEqual(auth.CONNECT_RETRIES, sess._connect_retries)

    def test_get_session_sdk_fallback(self):
        env = {
            'OS_AUTH_URL': 'http://keystone:5000/v3',
            'OS_USERNAME': 'user',
            'OS_PASSWORD': 'secret',
            'OS_PROJECT_NAME': 'project',
            'OS_USER_DOMAIN_NAME': 'Default',
            'OS_PROJECT_DOMAIN_NAME': 'Default',
        }
        with mock.patch.dict(os.environ, env, clear=True):
            sess = auth.get_session()
        self.assertIsInstance(sess, ks_session.Session)
        self.assertEqual('http://keystone:5000/v3', sess.auth.auth_url)
        self.assertEqual(auth.CONNECT_RETRIES, sess._connect_retries)


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
