import logging

from cinderclient import client as cinderclient
from designateclient import client as designateclient
import glanceclient
from gnocchiclient import client as gnocchiclient
from keystoneauth1 import loading
from keystoneauth1 import session
from keystoneclient.v3 import client
from manilaclient import client as manilaclient
from manukaclient import client as manukaclient
from muranoclient import client as muranoclient
from nectarallocationclient import client as allocationclient
from neutronclient.neutron import client as neutronclient
from novaclient import client as novaclient
from openstack import connection as sdkconnection
from placementclient import client as placementclient
from swiftclient import client as swiftclient
from troveclient import client as troveclient

from nectar_tools.config import configurable


LOG = logging.getLogger(__name__)


@configurable('openstack.client', env_prefix='OS')
def get_session(username, password, project_name, auth_url):
    loader = loading.get_plugin_loader('password')
    auth = loader.load_from_options(auth_url=auth_url,
                                    username=username,
                                    password=password,
                                    project_name=project_name,
                                    user_domain_id='default',
                                    project_domain_id='default')
    return session.Session(auth=auth)


def get_keystone_client(sess=None):
    if not sess:
        sess = get_session()
    return client.Client(session=sess)


def get_allocation_client(sess=None):
    if not sess:
        sess = get_session()
    return allocationclient.Client(1, session=sess)


def get_nova_client(sess=None):
    if not sess:
        sess = get_session()
    return novaclient.Client('2.60', session=sess)


def get_cinder_client(sess=None):
    if not sess:
        sess = get_session()
    return cinderclient.Client('3', session=sess)


def get_manila_client(sess=None):
    if not sess:
        sess = get_session()
    return manilaclient.Client('2.40', session=sess)


def get_glance_client(sess=None):
    if not sess:
        sess = get_session()
    return glanceclient.Client('2', session=sess)


def get_neutron_client(sess=None):
    if not sess:
        sess = get_session()
    return neutronclient.Client('2.0', session=sess)


def get_trove_client(sess=None):
    if not sess:
        sess = get_session()
    return troveclient.Client('1.0', session=sess)


def get_designate_client(sess=None, project_id=None, all_projects=False):
    if not sess:
        sess = get_session()
    return designateclient.Client('2', session=sess,
                                  sudo_project_id=project_id,
                                  all_projects=all_projects)


def get_gnocchi_client(sess=None):
    if not sess:
        sess = get_session()
    return gnocchiclient.Client('1', session=sess)


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


def get_openstacksdk(sess=None):
    if not sess:
        sess = get_session()
    return sdkconnection.Connection(session=sess)


def get_murano_client(sess=None):
    if not sess:
        sess = get_session()
    return muranoclient.Client(version='1', session=sess,
                               service_type='application-catalog')


def get_placement_client(sess=None):
    if not sess:
        sess = get_session()
    return placementclient.Client(version='1', session=sess)


def get_manuka_client(sess=None):
    if not sess:
        sess = get_session()
    return manukaclient.Client(version='1', session=sess)
