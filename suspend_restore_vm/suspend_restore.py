#!/usr/bin/env python

import sys
import os
import argparse
import re
import time

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError as SqlIntegrityError

from novaclient.exceptions import ClientException
from novaclient.v1_1 import client as nova_client

from create_db import VM, Base


def get_nova_client():

    auth_username = os.environ.get('OS_USERNAME', None)
    auth_password = os.environ.get('OS_PASSWORD', None)
    auth_tenant_name = os.environ.get('OS_TENANT_NAME', None)
    auth_url = os.environ.get('OS_AUTH_URL', None)

    auth_vars = (auth_username, auth_password, auth_tenant_name, auth_url)
    for var in auth_vars:
        if not var:
            print "Missing nova environment variables, exiting."
            sys.exit(1)

    nc = nova_client.Client(auth_username,
                            auth_password,
                            auth_tenant_name,
                            auth_url,
                            service_type='compute')
    return nc


def parse_args():
    actions = ['lock', 'unlock', 'suspend', 'resume', 'updatedb']
    views = ['all', 'suspending', 'failed', 'unmodified', 'suspended',
             'resuming', 'active', 'shutoff']

    parser = argparse.ArgumentParser(argument_default=argparse.SUPPRESS)
    parser.add_argument('-n', '--nodes', action='store',
                        required=True,
                        help='list of nodes e.g. np-rcc[5-84]')
    parser.add_argument('-a', '--action', action='store',
                        choices=actions,
                        required=False,
                        help='action to perform on the nodes')
    parser.add_argument('-v', '--view', action='store',
                        choices=views,
                        required=False,
                        help='view the status of the vms in the database')
    parser.add_argument('-d', '--database', action='store',
                        required=False, default='vms.db',
                        help='path to the sqlite database')

    args = parser.parse_args()

    if not 'view' in args and not 'action' in args:
        print "Please specify --view or --action"
        sys.exit(1)
    if 'view' in args and 'action' in args:
        print "Please specify --view or --action, but not both."
        sys.exit(1)

    return args


def db_connection(database):
    dbpath = 'sqlite:///' + os.path.abspath(database)
    engine = create_engine(dbpath, echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def parse_hosts(nodes):
    hosts = []
    hostname = nodes.split('[')[0]
    m = re.search(r"\[([A-Za-z0-9-]+)\]", nodes)
    if m is not None:
        host_start = int(m.group(1).split('-')[0])
        try:
            host_end = int(m.group(1).split('-')[1])
        except IndexError:
            host_end = host_start
        for x in range(host_start, host_end + 1):
            host = hostname + str(x)
            hosts.append(host)
    else:
        hosts.append(nodes)
    return hosts


def get_vms_from_host(client, host):
    vms = []
    search_opts = {'all_tenants': 1,
                   'host': host}
    servers = client.servers.list(search_opts=search_opts)
    for server in servers:
        vms.append(client.servers.get(server.id))

    return vms


def get_vm_details(instance):
    host = getattr(instance, 'OS-EXT-SRV-ATTR:host')
    uuid = instance.id
    state = instance.status
    return host, uuid, state


def unlock(servers):
    for instance in servers:
        host, uuid, state = get_vm_details(instance)
        print "UnLocking %s on %s" % (uuid, host)
        instance.unlock()


def lock(servers):
    for instance in servers:
        host, uuid, state = get_vm_details(instance)
        print "Locking %s on %s" % (uuid, host)
        instance.lock()


def add_vm_to_db(session, instance):
    host, uuid, state = get_vm_details(instance)
    try:
        print "Adding %s on %s to database (state=%s)" % (uuid, host, state)
        vm_data = VM(host=host, uuid=uuid, original_state=state,
                     current_state=state, task_state='initial')
        session.add(vm_data)
        session.commit()
    except SqlIntegrityError as e:
        print e
        session.rollback()


def get_vms_from_db(session, hosts):
    vms = []
    for host in hosts:
        res = session.query(VM).filter(VM.host == host)
        for record in res:
            vms.append(record)
    return vms


def get_vm_from_db(session, uuid):
    res = session.query(VM).filter(VM.uuid == uuid).first()
    return res


def get_vms_from_nova(hosts):
    nc = get_nova_client()
    servers = []
    for host in hosts:
        host_vms = get_vms_from_host(nc, host)
        for host_vm in host_vms:
            servers.append(host_vm)
    return servers


def suspend_instances(session, servers):
    for instance in servers:
        vm = get_vm_from_db(session, instance.id)
        if not vm:
            add_vm_to_db(session, instance)
            vm = get_vm_from_db(session, instance.id)
        suspend_instance(session, vm)


def suspend_instance(session, instance, vm):
    host, uuid, state = get_vm_details(instance)
    if state == 'ACTIVE':
        print "Locking & suspending %s on %s" % (uuid, host)
        instance.lock()
        # nova does not return a value for the lock status and it takes a
        # while for the child cell db to be updated, so we have to sleep
        time.sleep(30)
        try:
            instance.suspend()
            update_task_state(vm.uuid, session, 'suspending')
        except ClientException as e:
            print e
            update_task_state(vm.uuid, session, 'failed')
    else:
        print "Skipping %s on %s (state=%s)" % (uuid, host, state)


def resume_instances(session, servers):
    for instance in servers:
        vm = get_vm_from_db(session, instance.id)
        if vm is not None:
            resume_instance(session, instance, vm)
        else:
            print "%s not found in db." % instance.id


def resume_instance(session, instance, vm):
    host, uuid, state = get_vm_details(instance)
    if vm.current_state == 'SUSPENDED' and \
       vm.task_state == 'suspended' and \
       vm.original_state == 'ACTIVE':
        try:
            print "Unlocking & resuming %s on %s" % (uuid, host)
            instance.resume()
            update_task_state(vm.uuid, session, 'resuming')
            # nova does not return a value for the lock status and it takes a
            # while for the child cell db to be updated, so we have to sleep
            time.sleep(30)
            instance.unlock()
        except ClientException as e:
            print e
            update_task_state(vm.uuid, session, 'failed')


def update_db(session, servers):
    for instance in servers:
        host, uuid, state = get_vm_details(instance)
        vm = get_vm_from_db(session, uuid)
        if vm is not None:
            update_vm_state(session, vm, state, host)
        else:
            add_vm_to_db(session, instance)


def update_vm_state(session, vm, state, host):
    if vm.current_state != state:
        print "Updating VM state for %s on %s (old=%s, new=%s)" % \
            (vm.uuid, host, vm.current_state, state)
        update_current_state(vm.uuid, session, state=state)
    else:
        print "No state update required for %s on %s (state=%s)" % \
            (vm.uuid, host, state)
    if state == 'SUSPENDED' and vm.task_state != 'suspended':
        update_task_state(vm.uuid, session, 'suspended')
    if state == 'ERROR' and vm.task_state != 'failed':
        update_task_state(vm.uuid, session, 'failed')
    if state == 'ACTIVE' and vm.task_state != 'active':
        update_task_state(vm.uuid, session, 'active')
    if state == 'SHUTOFF' and vm.task_state != 'shutoff':
        update_task_state(vm.uuid, session, 'shutoff')


def print_vm(vm):
    print vm.id, vm.uuid, vm.host, vm.original_state, \
        vm.current_state, vm.task_state


def display_current_state(view, vms):

    for vm in vms:
        if view == 'all':
            print_vm(vm)
        elif view == 'suspending':
            if vm.task_state == 'suspending':
                print_vm(vm)
        elif view == 'suspended':
            if vm.task_state == 'suspended':
                print_vm(vm)
        elif view == 'failed':
            if vm.task_state == 'failed':
                print_vm(vm)
        elif view == 'unmodified':
            if vm.task_state == 'initial':
                print_vm(vm)
        elif view == 'resuming':
            if vm.task_state == 'resuming':
                print_vm(vm)
        elif view == 'active':
            if vm.task_state == 'active':
                print_vm(vm)
        elif view == 'shutoff':
            if vm.task_state == 'shutoff':
                print_vm(vm)


def update_current_state(uuid, session, state=None):
    res = session.query(VM).filter(VM.uuid == uuid).first()
    res.current_state = state
    session.commit()


def update_task_state(uuid, session, state=None):
    res = session.query(VM).filter(VM.uuid == uuid).first()
    res.task_state = state
    session.commit()


def main():

    args = parse_args()
    hosts = parse_hosts(args.nodes)
    session = db_connection(args.database)

    if 'view' in args:
        vms = get_vms_from_db(session, hosts)
        display_current_state(args.view, vms)
        sys.exit(0)
    elif 'action' in args:
        servers = get_vms_from_nova(hosts)
        if args.action == 'updatedb':
            update_db(session, servers)
        elif args.action == 'suspend':
            suspend_instances(session, servers)
            servers = get_vms_from_nova(hosts)
            update_db(session, servers)
        elif args.action == 'resume':
            resume_instances(session, servers)
            servers = get_vms_from_nova(hosts)
            update_db(session, servers)
        elif args.action == 'lock':
            lock(servers)
        elif args.action == 'unlock':
            unlock(servers)


if __name__ == '__main__':
    main()
