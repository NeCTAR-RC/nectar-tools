#!/usr/bin/env python

import os
import sys
from keystoneclient import client as ksclient
from novaclient import client as novaclient
from cinderclient import client as cinderclient
import glanceclient
from keystoneclient.exceptions import AuthorizationFailure
from keystoneauth1.identity import v3
from keystoneauth1 import session
from keystoneclient.v3 import client

from nectar_tools.config import configurable


@configurable('openstack.client', env_prefix='OS')
def get_session(username, password, tenant_name, auth_url):

    auth = v3.Password(auth_url=auth_url,
                       username=username,
                       password=password,
                       project_name=tenant_name,
                       user_domain_id='default',
                       project_domain_id='default')
    return session.Session(auth=auth)


def get_keystone_client():
    sess = get_session()
    return client.Client(session=sess)


def get_nova_client():
    sess = get_session()
    return novaclient.Client('2.1', session=session)


def get_cinder_client():
    sess = get_session()
    return cinderclient.Client('2', session=session)


def get_glance_client():
    sess = get_session()
    return glanceclient.Client('2', session=session)


def get_swift_client():
    sess = get_session()
