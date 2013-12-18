#!/usr/bin/env python

import sys
import os
import argparse
import re
import time

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from create_db import VM

from novaclient.exceptions import ClientException
from novaclient.v1_1 import client as nova_client


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
    actions = ['lock', 'unlock', 'suspend', 'resume', 'db_add', 'db_update']
    views = ['all', 'suspending', 'failed', 'unmodified', 'suspended']

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

    args = parser.parse_args()

    if not 'view' in args and not 'action' in args:
        print "Please specify --view or --action"
        sys.exit(1)
    if 'view' in args and 'action' in args:
        print "Please specify --view or --action, but not both."
        sys.exit(1)

    return args


def db_connection():
    engine = create_engine('sqlite:///vm_backup.db', echo=False)
    Session = sessionmaker(bind=engine)
    return Session()


def get_hosts(nodes):
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


#def vm_from_servers(client, servers_list):
#    instance_uuid = []
#    hypers = client.hypervisors.search(servers_list, servers=True)
#    servers = [y for x in hypers for y in x.servers]
#    for u in servers:
#        instance_uuid.append(u['uuid'])
#
#    return instance_uuid


def get_instances_from_host(client, host):
    instances = []
    search_opts = {'all_tenants': 1,
                   'host': host}
    servers = client.servers.list(search_opts=search_opts)
    for server in servers:
        instances.append(server.id)

    return instances


def add_vms_to_db(client, session, vms):
    vm_ids = [i for k in vms for i in k[1]]
    for vm in vm_ids:
        manager = client.servers
        instance = manager.get(''.join(vm))
        get_vm_details(instance, session)


def unlock(client, vms):
    vm_ids = [i for k in vms for i in k[1]]
    for vm in vm_ids:
        manager = client.servers
        instance = manager.get(''.join(vm))
        host = instance.__dict__.get('OS-EXT-SRV-ATTR:host')
        print "UnLocking %s on %s" % (instance.id, host)
        instance.unlock()


def lock(client, vms):
    vm_ids = [i for k in vms for i in k[1]]
    for vm in vm_ids:
        manager = client.servers
        instance = manager.get(''.join(vm))
        host = instance.__dict__.get('OS-EXT-SRV-ATTR:host')
        print "Locking %s on %s" % (instance.id, host)
        instance.lock()


def get_vm_details(instance, session):
    host = instance.__dict__.get('OS-EXT-SRV-ATTR:host')
    uuid = instance.id
    state = instance.status
    print "Adding %s on %s to database (state=%s)" % (uuid, host, state)
    vm_data = VM(host=host, uuid=uuid, original_state=state,
                 current_state=state, task_state='initial')
    session.add(vm_data)
    session.commit()


def get_instances_from_db(session, hosts):
    instances = []
    for host in hosts:
        res = session.query(VM).filter(VM.host == host)
        for record in res:
            instances.append(record)
    return instances


def suspend_instances(client, session, vms):
    manager = client.servers
    for vm in vms:
        instance = manager.get(vm.uuid)
        host = instance.__dict__.get('OS-EXT-SRV-ATTR:host')
        if instance.status == 'ACTIVE':
            print "Locking & suspending %s on %s" % (instance.id, host)
            instance.lock()
            time.sleep(30)
            try:
                instance.suspend()
                update_task_state(vm.uuid, session, 'suspending')
            except ClientException as e:
                print e
                update_task_state(vm.uuid, session, 'failed')
        else:
            print "Skipping %s on %s (state=%s)" % (instance.id, host, instance.status)
            if instance.status == 'SUSPENDED' and vm.task_state != 'suspended':
                update_task_state(vm.uuid, session, 'suspended')
            if instance.status == 'ERROR' and vm.task_state != 'failed':
                update_task_state(vm.uuid, session, 'failed')


def resume_instances(client, session, vms):
    manager = client.servers
    for vm in vms:
        if vm.current_state == 'SUSPENDED' and vm.task_state == 'suspended':
            instance = manager.get(vm.uuid)
            host = instance.__dict__.get('OS-EXT-SRV-ATTR:host')
            try:
                print "Resuming & unlocking %s on %s" % (instance.id, host)
                instance.resume()
                time.sleep(30)
                instance.unlock()
            except ClientException as e:
                print e
                update_task_state(vm.uuid, session, 'failed')

        update_current_state(vm.uuid, session, 'ACTIVE')


def update_vm_states(client, session, vms):

    manager = client.servers
    for vm in vms:
        instance = manager.get(vm.uuid)
        host = instance.__dict__.get('OS-EXT-SRV-ATTR:host')
        if vm.current_state != instance.status:
            print "Updating VM state for %s on %s (old=%s, new=%s)" % \
                (instance.id, host, vm.current_state, instance.status)
            update_current_state(vm.uuid, session, state=instance.status)
        else:
            print "No update required for %s on %s (state=%s)" % \
                (instance.id, host, instance.status)
        if instance.status == 'SUSPENDED' and vm.task_state != 'suspended':
            update_task_state(vm.uuid, session, 'suspended')
        if instance.status == 'ERROR' and vm.task_state != 'failed':
            update_task_state(vm.uuid, session, 'failed')


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


def update_current_state(vm_uuid, session, state=None):
    res = session.query(VM).filter(VM.uuid == vm_uuid).first()
    res.current_state = state
    session.commit()


def update_task_state(vm_uuid, session, state=None):
    res = session.query(VM).filter(VM.uuid == vm_uuid).first()
    res.task_state = state
    session.commit()


def suspend(cs, session, db_vms):
    suspend_instances(cs, session, db_vms)
    update_vm_states(cs, session, db_vms)


def resume(cs, session, db_vms):
    resume_instances(cs, session, db_vms)
    update_vm_states(cs, session, db_vms)


def main():

    args = parse_args()

    hosts = get_hosts(args.nodes)

    session = db_connection()
    db_vms = get_instances_from_db(session, hosts)

    if 'view' in args:
        display_current_state(args.view, db_vms)
        sys.exit(0)

    elif 'action' in args:
        nc = get_nova_client()
        nova_vms = []
        for host in hosts:
            host_vms = (host, get_instances_from_host(nc, host))
            nova_vms.append(host_vms)

        if args.action == 'db_update':
            update_vm_states(nc, session, db_vms)
        elif args.action == 'db_add':
            add_vms_to_db(nc, session, nova_vms)
        elif args.action == 'suspend':
            suspend(nc, session, db_vms)
        elif args.action == 'resume':
            resume(nc, session, db_vms)
        elif args.action == 'lock':
            lock(nc, nova_vms)
        elif args.action == 'unlock':
            unlock(nc, nova_vms)


if __name__ == '__main__':
    main()
