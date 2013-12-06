#!/usr/bin/env python

import os
import sys
from keystoneclient.v2_0 import client as ks_client
from keystoneclient.exceptions import AuthorizationFailure
from novaclient.v1_1 import client as nova_client

auth_username = os.environ.get('OS_USERNAME')
auth_password = os.environ.get('OS_PASSWORD')
auth_tenant = os.environ.get('OS_TENANT_NAME')
auth_url = os.environ.get('OS_AUTH_URL')


def get_keystone_client():

    try:
        kc = ks_client.Client(username=auth_username,
                            password=auth_password,
                            tenant_name=auth_tenant,
                            auth_url=auth_url)
    except AuthorizationFailure as e:
        print e
        print 'Have you sourced your openrc?'
        sys.exit(1)
    return kc


def get_nova_client():

    nc = nova_client.Client(auth_username,
                        auth_password,
                        auth_tenant,
                        auth_url,
                        service_type="compute")
    return nc
