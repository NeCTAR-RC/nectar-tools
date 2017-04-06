import logging

from cinderclient import client as cinderclient
import glanceclient
from keystoneauth1 import loading
from keystoneauth1 import session
from keystoneclient.v3 import client
from neutronclient.neutron import client as neutronclient
from novaclient import client as novaclient
from swiftclient import client as swiftclient

from nectar_tools.config import configurable


LOG = logging.getLogger(__name__)


@configurable('openstack.client', env_prefix='OS')
def get_session(username, password, tenant_name, auth_url):
    loader = loading.get_plugin_loader('password')
    auth = loader.load_from_options(auth_url=auth_url,
                                    username=username,
                                    password=password,
                                    project_name=tenant_name,
                                    user_domain_id='default',
                                    project_domain_id='default')
    return session.Session(auth=auth)


def get_keystone_client(sess=None):
    if not sess:
        sess = get_session()
    return client.Client(session=sess)


def get_nova_client(sess=None):
    if not sess:
        sess = get_session()
    return novaclient.Client('2.1', session=sess)


def get_cinder_client(sess=None):
    if not sess:
        sess = get_session()
    return cinderclient.Client('2', session=sess)


def get_glance_client(sess=None):
    if not sess:
        sess = get_session()
    return glanceclient.Client('2', session=sess)


def get_neutron_client(sess=None):
    if not sess:
        sess = get_session()
    return neutronclient.Client('2.0', session=sess)


def get_swift_client(sess=None, project_id=None):
    if not sess:
        sess = get_session()
    os_opts = {}
    if project_id:
        endpoint = sess.get_endpoint(service_type='object-store')
        auth_project = sess.get_project_id()
        endpoint = endpoint.replace('AUTH_%s' % auth_project,
                                    'AUTH_%s' % project_id)
        os_opts['object_storage_url'] = '%s' % endpoint
    return swiftclient.Connection(session=sess, os_options=os_opts)
