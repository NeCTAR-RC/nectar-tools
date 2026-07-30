import logging
import os

from blazarclient import client as blazarclient
from cinderclient import client as cinderclient
from cloudkittyclient import client as cloudkittyclient
from designateclient import client as designateclient
import glanceclient
from gnocchiclient import client as gnocchiclient
from heatclient import client as heatclient
from keystoneauth1 import loading as ks_loading
from keystoneclient.v3 import client
from kubernetes import client as kube_client
from magnumclient import client as magnumclient
from manilaclient import client as manilaclient
from manukaclient import client as manukaclient
from muranoclient import client as muranoclient
from nectarallocationclient import client as allocationclient
from neutronclient.neutron import client as neutronclient
from novaclient import client as novaclient
import openstack
from openstack import connection as sdkconnection
from placementclient import client as placementclient
from swiftclient import client as swiftclient
from taynacclient import client as taynacclient
from troveclient import client as troveclient
from varroaclient import client as varroaclient
from warreclient import client as warreclient

from nectar_tools import config


CONF = config.CONF

LOG = logging.getLogger(__name__)


def get_session(system_scope=None):
    """Return a keystoneauth session.

    Uses the [service_auth] config section when auth_type is set
    there, otherwise falls back to OS_* environment variables or
    clouds.yaml via openstacksdk.

    :param system_scope: set to 'all' for a system scoped session
                         instead of the configured project scope.
    """
    if CONF[config.SERVICE_AUTH_GROUP].auth_type:
        kwargs = {}
        if system_scope:
            # override the configured project scope
            kwargs = {
                'system_scope': system_scope,
                'project_name': None,
                'project_id': None,
                'project_domain_name': None,
                'project_domain_id': None,
            }
        auth = ks_loading.load_auth_from_conf_options(
            CONF, config.SERVICE_AUTH_GROUP, **kwargs
        )
        return ks_loading.load_session_from_conf_options(
            CONF, config.SERVICE_AUTH_GROUP, auth=auth
        )
    kwargs = {'system_scope': system_scope} if system_scope else {}
    conn = openstack.connect(**kwargs)
    return conn.session


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
    return novaclient.Client('2.87', session=sess)


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
    return designateclient.Client(
        '2',
        session=sess,
        sudo_project_id=project_id,
        all_projects=all_projects,
    )


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
        endpoint = endpoint.replace(
            f'AUTH_{auth_project}', f'AUTH_{project_id}'
        )
        os_opts['object_storage_url'] = f'{endpoint}'
    return swiftclient.Connection(session=sess, os_options=os_opts)


def get_openstacksdk(sess=None):
    if not sess:
        sess = get_session()
    return sdkconnection.Connection(session=sess)


def get_murano_client(sess=None):
    if not sess:
        sess = get_session()
    return muranoclient.Client(
        version='1', session=sess, service_type='application-catalog'
    )


def get_placement_client(sess=None):
    if not sess:
        sess = get_session()
    return placementclient.Client(version='1', session=sess)


def get_manuka_client(sess=None):
    if not sess:
        sess = get_session()
    return manukaclient.Client(version='1', session=sess)


def get_magnum_client(sess=None):
    if not sess:
        sess = get_session()
    return magnumclient.Client(version='1', session=sess)


def get_heat_client(sess=None):
    if not sess:
        sess = get_session()
    return heatclient.Client(version='1', session=sess)


def get_cloudkitty_client(sess=None):
    if not sess:
        sess = get_session()
    return cloudkittyclient.Client(version='2', session=sess)


def get_warre_client(sess=None):
    if not sess:
        sess = get_session()
    return warreclient.Client(version='1', session=sess)


def get_taynac_client(sess=None):
    if not sess:
        sess = get_session()
    return taynacclient.Client(version='1', session=sess)


def get_blazar_client(sess=None):
    if not sess:
        sess = get_session()
    return blazarclient.Client(session=sess, service_type='reservation')


def get_varroa_client(sess=None):
    if not sess:
        sess = get_session()
    return varroaclient.Client(version='1', session=sess)


def get_kube_client():
    host = CONF.kubernetes_client.host or os.environ.get('KUBE_HOST')
    token = CONF.kubernetes_client.token or os.environ.get('KUBE_TOKEN')
    if not host or not token:
        raise Exception(
            'kubernetes_client host and token must be set in the '
            'config file or KUBE_HOST/KUBE_TOKEN environment variables'
        )
    conf = kube_client.Configuration()
    conf.api_key_prefix['authorization'] = 'Bearer'
    conf.host = host
    conf.verify_ssl = False
    conf.api_key['authorization'] = token
    api_client = kube_client.ApiClient(conf)
    return kube_client.CoreV1Api(api_client)
