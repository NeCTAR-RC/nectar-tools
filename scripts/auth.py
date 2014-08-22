#!/usr/bin/env python

import os
import sys
import keystoneclient.v2_0.client as ksclient
import novaclient.v1_1.client as novaclient
import cinderclient.client as cinderclient
import glanceclient
from keystoneclient.exceptions import AuthorizationFailure

auth_username = os.environ.get('OS_USERNAME')
auth_password = os.environ.get('OS_PASSWORD')
auth_tenant = os.environ.get('OS_TENANT_NAME')
auth_url = os.environ.get('OS_AUTH_URL')
auth_cacert = os.environ.get('OS_CACERT')


def get_keystone_client():

    try:
        kc = ksclient.Client(username=auth_username,
                             password=auth_password,
                             tenant_name=auth_tenant,
                             auth_url=auth_url,
                             cacert=auth_cacert)
    except AuthorizationFailure as e:
        print e
        print 'Have you sourced your openrc?'
        sys.exit(1)
    return kc


def get_nova_client():

    nc = novaclient.Client(auth_username,
                           auth_password,
                           auth_tenant,
                           auth_url,
                           cacert=auth_cacert,
                           service_type="compute")
    return nc


def get_cinder_client():

    cc = cinderclient.Client('1', auth_username,
                             auth_password,
                             auth_tenant,
                             auth_url,
                             cacert=auth_cacert)
    return cc


def get_glance_client(glance_url, token):

    gc = glanceclient.Client('1', glance_url, token=token, cacert=auth_cacert)
    return gc
