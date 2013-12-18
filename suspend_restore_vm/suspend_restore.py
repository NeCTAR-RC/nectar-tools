import sys
import os
import argparse
import re
import time
from novaclient.v1_1 import client as client_nova
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from create_database import VM
from novaclient.exceptions import ClientException

AUTH_USER = os.environ.get('OS_USERNAME', None)
AUTH_PASSWORD = os.environ.get('OS_PASSWORD', None)
AUTH_TENANT_NAME = os.environ.get('OS_TENANT_NAME', None)
AUTH_URL = os.environ.get('OS_AUTH_URL', None)
AUTH_REGION = os.environ.get('OS_REGION_NAME', None)

for auth_variable in (AUTH_USER, AUTH_PASSWORD,
                      AUTH_TENANT_NAME, AUTH_URL):
    if not auth_variable:
        print "Missing Nova environment variables!"
        sys.exit(1)


def get_args():
    parser = argparse.ArgumentParser(argument_default=argparse.SUPPRESS)
    parser.add_argument('-n', action='store',
                        required=True,
                        help='list of nodes e.g. np-rcc[5-84]')
    parser.add_argument('-c', action='store',
                        required=False,
                        help='number of servers to run concurrently')
    parser.add_argument('-i', action='store', choices=['suspend',
                        'update', 'resume', 'lock', 'unlock', 'view_pass',
                        'view_fail', 'view_hold'],
                        required=True,
                        help='action')

    return parser.parse_args()


def client_conn():
        client = client_nova.Client(username=AUTH_USER,
                                    insecure=True,
                                    api_key=AUTH_PASSWORD,
                                    project_id=AUTH_TENANT_NAME,
                                    auth_url=AUTH_URL,
                                    region_name=AUTH_REGION)
        return client


def db_connection():
    engine = create_engine('sqlite:///vm_backup.db', echo=False)
    Session = sessionmaker(bind=engine)
    return Session()


def get_servers(servers):
    server_domain_name = servers.split('[')[0]
    m = re.search(r"\[([A-Za-z0-9-]+)\]", servers)
    if m is not None:
        server_start = m.group(1).split('-')[0]
        server_end = m.group(1).split('-')[1]
        return server_domain_name, server_start, server_end
    else:
        return server_domain_name


def vm_frm_servers(client, servers_list):
    instance_uuid = []
    hypers = client.hypervisors.search(servers_list, servers=True)
    servers = [y for x in hypers for y in x.servers]
    for u in servers:
        instance_uuid.append(u['uuid'])

    return instance_uuid


def vms_from_host(client, servers_list):
    instance_uuid = []
    search_opts = {'all_tenants': 1,
                   'host': servers_list}
    server = client.servers.list(search_opts=search_opts)
    for i in server:
        instance_uuid.append(i.id)

    return instance_uuid


def get_vm_status(client, vm_list, session):
    vm_id = [i for k in vm_list for i in k[1]]
    for i in vm_id:
        manager = client.servers
        vms = manager.get(''.join(i))
        get_vm_details(vms, session)


def unlock(client, vm_list):
    vm_id = [i for k in vm_list for i in k[1]]
    for i in vm_id:
        manager = client.servers
        vms = manager.get(''.join(i))
        vms.unlock()


def lock(client, vm_list):
    vm_id = [i for k in vm_list for i in k[1]]
    for i in vm_id:
        manager = client.servers
        vms = manager.get(''.join(i))
        vms.lock()


def get_vm_details(vm_, session):
    vm_data = VM(host=vm_.__dict__.get('OS-EXT-SRV-ATTR:host'),
                 uuid_vm=vm_.id, vm_state=vm_.status, update_state='NULL')
    session.add(vm_data)
    session.commit()


def suspend_instances(client, session):
    res = session.query(VM).all()
    manager = client.servers
    for vm in res:
        if vm.vm_state == 'ACTIVE':
            vms = manager.get(vm.uuid_vm)
            vms.lock()
            time.sleep(30)
            try:
                print "Lock & suspend %s" % vms.id
                vms.suspend()
                update_vm_op(vm.uuid_vm, 'us', session, 'True')
            except ClientException:
                update_vm_op(vm.uuid_vm, 'us', session, 'Failed')
        else:
            print "Skipping %r" % vms.id
            update_vm_op(vm.uuid_vm, 'us', session, 'False')


def unsuspend_instances(client, session):
    res = session.query(VM).all()
    manager = client.servers
    for vm in res:
        if vm.vm_state == 'SUSPENDED' and vm.update_state == 'True':
            vms = manager.get(vm.uuid_vm)
            print "Resume & unlock %s" % vms.id
            vms.resume()
            time.sleep(30)
            vms.unlock()

        update_vm_op(vm.uuid_vm, 'vs', session, 'ACTIVE')


def update_instances_state(client, session):
    res = session.query(VM).all()
    manager = client.servers
    for vm in res:
        vms = manager.get(vm.uuid_vm)
        print "Updating VM State for %r" % vms.id
        update_vm_op(vm.uuid_vm, 'vs', session, state=vms.status)


def display_current(session, opt):
    res = session.query(VM).all()
    for vm in res:
        if opt == 'view_pass':
            if vm.update_state == 'True':
                print vm.id, vm.uuid_vm, vm.host, vm.vm_state, vm.update_state
        elif opt == 'view_fail':
            if vm.update_state == 'Failed':
                print vm.id, vm.uuid_vm, vm.host, vm.vm_state, vm.update_state
        elif opt == 'view_hold':
            if vm.update_state == 'False':
                print vm.id, vm.uuid_vm, vm.host, vm.vm_state, vm.update_state


def update_vm_op(vm_uuid, op, session, state=None):
    res = session.query(VM).filter(VM.uuid_vm == vm_uuid).first()
    if op == 'us':
        res.update_state = state
    else:
        res.vm_state = state
    session.commit()


def run_action(method, cs, session, server_list=None):
    if method == 'suspend':
        get_vm_status(cs, server_list, session)
        suspend_instances(cs, session)
        update_instances_state(cs, session)
    elif method == 'resume':
        unsuspend_instances(cs, session)
        update_instances_state(cs, session)


def main():
    options = get_args()
    session = db_connection()
    if 'c' not in options:
        options.c = 0

    vm_list_all = []
    cs = client_conn()
    server_data = get_servers(options.n)
    if isinstance(server_data, tuple):
        server_start = int(server_data[1])
        server_end = int(server_data[2]) + 1
        for x in range(server_start, server_end):
            server = server_data[0] + str(x)
            vm_list = (server, vms_from_host(cs, server))
            vm_list_all.append(vm_list)

        if options.i == 'update':
            update_instances_state(cs, session)
        elif options.i == 'suspend':
            run_action(options.i, cs, session, vm_list_all)
        elif options.i == 'resume':
            run_action(options.i, cs, session, vm_list_all)
        elif options.i == 'lock':
            lock(cs, vm_list)
        elif options.i == 'unlock':
            unlock(cs, vm_list)
        else:
            display_current(session, options.i)
    else:
        vm_list = (server_data, vms_from_host(cs, server_data))
        vm_list_all.append(vm_list)
        if options.i == 'update':
            update_instances_state(cs, session)
        elif options.i == 'suspend':
            run_action(options.i, cs, session, vm_list_all)
        elif options.i == 'resume':
            run_action(options.i, cs, session)
        elif options.i == 'lock':
            lock(cs, vm_list)
        elif options.i == 'unlock':
            unlock(cs, vm_list)
        else:
            display_current(session, options.i)


if __name__ == '__main__':
    main()
