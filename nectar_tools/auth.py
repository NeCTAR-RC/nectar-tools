#!/usr/bin/env python

import os
import sys
import keystoneclient.v2_0.client as ksclient
import novaclient.v1_1.client as novaclient
import cinderclient.client as cinderclient
import glanceclient
from keystoneclient.exceptions import AuthorizationFailure


from nectar_tools.config import configurable


@configurable('openstack.client', env_prefix='OS')
def get_keystone_client(username, password, tenant_name, auth_url):
    kc = ksclient.Client(username=username,
                         password=password,
                         tenant_name=tenant_name,
                         auth_url=auth_url)
    return kc


@configurable('openstack.client', env_prefix='OS')
def get_nova_client(username, password, tenant_name, auth_url):
    nc = novaclient.Client(username,
                           password,
                           tenant_name,
                           auth_url,
                           service_type="compute")
    return nc


@configurable('openstack.client', env_prefix='OS')
def get_cinder_client(username, password, tenant_name, auth_url):
    cc = cinderclient.Client('1',
                             username,
                             password,
                             tenant_name,
                             auth_url)
    return cc


def get_glance_client(glance_url, token):
    gc = glanceclient.Client('1', glance_url, token=token)
    return gc
