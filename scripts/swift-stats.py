#!/usr/bin/env python

import swiftclient
from keystoneclient.exceptions import AuthorizationFailure
import os
import sys
import MySQLdb
import time
import requests
import json

from keystoneauth1 import loading
from keystoneauth1 import session
from keystoneclient.v3 import client


SWIFT_QUOTA_KEY = 'x-account-meta-quota-bytes'


def get_session():
    username = os.environ.get('OS_USERNAME')
    password = os.environ.get('OS_PASSWORD')
    tenant_name = os.environ.get('OS_TENANT_NAME')
    auth_url = os.environ.get('OS_AUTH_URL')
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
    return swiftclient.client.Connection(session=sess, os_options=os_opts)


class NectarApiSession(requests.Session):
    """Class to encapsulate the rest api endpoint with a requests session.

    """
    def __init__(self, api_url=None, api_username=None,
                 api_password=None, *args, **kwargs):
        username = os.environ.get('NECTAR_ALLOCATIONS_USERNAME', api_username)
        password = os.environ.get('NECTAR_ALLOCATIONS_PASSWORD', api_password)
        self.api_url = os.environ.get('NECTAR_ALLOCATIONS_URL', api_url)
        assert username and password and self.api_url
        requests.Session.__init__(self, *args, **kwargs)
        self.auth = (username, password)

    def _api_get(self, rel_url, *args, **kwargs):
        return self.get("%s%s" % (self.api_url, rel_url), *args, **kwargs)

    def get_allocations(self):
        req = self._api_get('/rest_api/allocations')
        req.raise_for_status()
        return req.json()

    def get_quotas(self, allocation, resource='object', zone='nectar'):
        url = '/rest_api/quotas/?resource=%s&zone=%s' % (resource, zone)
        if allocation:
            url += '&allocation=%s' % allocation
        req = self._api_get(url)
        req.raise_for_status()
        return req.json()


def set_swift_quota(client, tenant, quota):

    attempt = 0
    max_attempts = 10
    while attempt <= max_attempts:
        try:
            client.post_account(headers={SWIFT_QUOTA_KEY: quota})
            sys.stderr.write("Set quota for %s to %s\n" % (tenant.name, quota))
        except:
            sys.stderr.write(
                "Failed to set quota for %s to %s\n" % (tenant.name, quota))
            time.sleep(5)
            attempt += 1
            continue
        return


def swift_data(sclient):

    account_details = sclient.head_account()
    bytes_used = int(account_details['x-account-bytes-used'])
    quota = int(account_details.get(SWIFT_QUOTA_KEY, -1))
    containers = int(account_details.get('x-account-container-count'))
    objects = int(account_details.get('x-account-object-count'))
    gbs = bytes_used
    return gbs, quota, containers, objects


def allocation_is_valid(allocation):
    if not allocation['tenant_uuid']:
        return False
    if allocation['parent_request'] is not None:
        return False
    if allocation['status'] not in ('A', 'X'):
        return False
    return True


if __name__ == '__main__':
    ksession = get_session()
    kc = get_keystone_client(ksession)

    allocation_api = NectarApiSession()
    allocations = allocation_api.get_allocations()

    quota_dict = {}
    for allocation in allocations:
        if not allocation_is_valid(allocation):
            continue
        tenant = allocation['tenant_uuid']
        quota = allocation_api.get_quotas(allocation=allocation['id'])
        if len(quota) == 1:
            quota_dict[tenant] = int(quota[0]['allocation']) * 1024 * 1024 * 1024
    projects = kc.projects.list()

    #t = kc.projects.get('25')
    #projects = [t]
    for project in projects:
        if not project.enabled:
            continue
        #if not project.name.startswith('pt-'):
        #    continue

        role_assignments = kc.role_assignments.list(project=project.id, include_names=True)
        user_emails = []
        for ra in role_assignments:
            if ra.user['name'] not in user_emails:
                user_emails.append(ra.user['name'])

        allocated = quota_dict.get(project.id, None)
        sclient = get_swift_client(ksession, project.id)
        gbs, quota, containers, objects = swift_data(sclient)

        if project.name.startswith('pt-'):
            allocated = 10 * 1024 * 1024 * 1024

            if gbs < allocated and quota == -1:
                set_swift_quota(sclient, project, allocated)
                quota = allocated
        else:
            if allocated and quota == -1 and gbs <= allocated:
                set_swift_quota(sclient, project, allocated)
                quota = allocated
        #if allocated is None or quota < 0:
        print "%s,%s,%s,%s,%s,%s,%s,%s" % (
            project.id, project.name, "; ".join(user_emails),
            containers, objects, gbs, allocated, quota)
