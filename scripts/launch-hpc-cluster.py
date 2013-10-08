#!/usr/bin/env python

import sys
import os
import re
import time
import datetime
import argparse
import threading
import traceback
import paramiko

from keystoneclient.v2_0 import client as ks_client
from keystoneclient.exceptions import AuthorizationFailure
from novaclient.v1_1 import client as nova_client


def cprint(str1='', color=None, str2='', sep=': '):

    if color == 'red':
        C = '\033[91m'
    elif color == 'green':
        C = '\033[92m'
    elif color == 'yellow':
        C = '\033[93m'
    elif color == 'blue':
        C = '\033[94m'

    ENDC = '\033[0m'

    if color is None:
        if str2 == '':
            print str1
        else:
            print str1 + sep + str2
    else:
        print C + str1 + sep + ENDC + str2


class hpcnode(threading.Thread):

    def __init__(self, node_id, total_nodes, nc, key_name, sg,
                 ipaddrs, event, image, flavor, username, name,
                 extra_cmds, packages, files, key):

        threading.Thread.__init__(self)

        self.node_id = node_id
        if self.node_id == 0:
            self.name = '%s head node' % name
        else:
            self.name = '%s node %s' % (name, node_id)
        self.hostname = self.name.replace(' ', '-').lower()
        self.total_nodes = total_nodes
        self.sg = sg
        self.event = event
        self.image = image
        self.flavor = flavor
        self.username = username
        if username == 'root':
            self.sudo = False
        else:
            self.sudo = True
        self.server = nc.servers.create(name=self.name,
                                        image=self.image,
                                        flavor=self.flavor,
                                        key_name=key_name,
                                        security_groups=[sg.name, ])
        self.extra_cmds = extra_cmds
        init_cmds = []
        init_cmds.append('apt-get update')
        init_cmds.append('aptitude -y full-upgrade')
        init_cmds.append('apt-get -y install %s' % ' '.join(packages))
        self.init_cmds = init_cmds
        self.files = files
        self.ipaddrs = ipaddrs
        self.key = key

    def run(self):
        self.wait_for_boot()
        self.wait_for_ipaddress()

        try:

            self.ssh_connect()

            for cmd in self.init_cmds:
                self.ssh_cmd(cmd)

            self.ssh_disconnect()

            self.reboot()
            self.wait_for_boot()

            self.sftp_transfer()

            while len(self.ipaddrs) != self.total_nodes:
                self.event.wait()

            if self.node_id == 0:
                self.head_node_setup()

        except Exception, e:
            exc = str(e.__class__) + ': ' + str(e)
            cprint('Caught exception: ' + exc, 'red')
            traceback.print_exc()
            try:
                self.cleanup()
            except:
                pass

    def head_node_setup(self):
        self.ssh_connect()
        self.sudo = False

        for ipaddr in self.ipaddrs:
            nc.security_group_rules.create(self.sg.id, 'udp', '1', '65535',
                                           '%s/32' % ipaddr)
            nc.security_group_rules.create(self.sg.id, 'tcp', '1', '65535',
                                           '%s/32' % ipaddr)
            mpi_cmds = ['echo %s >> mpi_hosts' % ipaddr,
                        'ssh-keyscan -v -T 10 %s >> .ssh/known_hosts' % ipaddr]
            for cmd in mpi_cmds:
                self.ssh_cmd(cmd)

        for cmd in self.extra_cmds:
            self.ssh_cmd(cmd)

        print 'Once the other nodes have finished booting you can ssh to'
        print '"%s" and run mpi commands. e.g.' % self.name
        print '# ssh %s@%s' % (self.username, self.ipaddress)
        print '$ mpirun -v -np %s --hostfile mpi_hosts hostname' % self.total_nodes

        self.ssh_disconnect()

    def check_boot(self):
        try:
            output = self.server.get_console_output()
            boot_finished = output.find('cloud-init boot finished')
            if boot_finished > 0:
                return True
        except Exception:
            return False

    def wait_for_boot(self):
        boot_finished = self.check_boot()
        cprint(self.name, 'blue', 'Waiting for VM to boot...')
        while boot_finished is not True:
            try:
                boot_finished = self.check_boot()
            except Exception:
                pass
            time.sleep(5)
        cprint(self.name, 'blue', 'Boot finished.')

    def reboot(self):
        cprint(self.name, 'blue', 'Rebooting...')
        self.server.reboot()
        time.sleep(15)

    def wait_for_ipaddress(self):
        cprint(self.name, 'blue', 'Waiting for IP address...')
        self.ipaddress = 0
        while self.ipaddress == 0:
            try:
                self.ipaddress = self.server.networks.values()[0][0]
            except IndexError:
                pass
            time.sleep(5)
        self.ipaddrs.append(self.ipaddress)
        self.init_cmds.insert(0, 'sh -c "echo %s %s >> /etc/hosts"'
                              % (self.ipaddress, self.hostname))
        self.event.set()
        cprint(self.name, 'blue', 'IP address: %s' % self.ipaddress)

    def ssh_cmd(self, cmd):
        if self.sudo and cmd[0:3] != 'cd ':
            full_cmd = 'sudo %s' % cmd
        else:
            full_cmd = cmd
        stdin, stdout, stderr = self.client.exec_command(full_cmd)
        prompt = '%s@%s' % (self.username, self.ipaddress)
        cprint(prompt, 'yellow', full_cmd, '$ ')
        channel = stdout.channel
        status = channel.recv_exit_status()
        for line in stdout:
            cprint(line.strip('\n'), 'green', sep='')
        if status != 0:
            cprint('An error occured running remote commands:', 'red')
            for line in stderr:
                print line.strip('\n')
            raise

    def ssh_connect(self):
        try:
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.client.connect(hostname=self.ipaddress,
                                username=self.username)
        except:
            raise

    def ssh_disconnect(self):
        try:
            self.client.close()
        except:
            pass

    def sftp_transfer(self):
        if len(self.files) > 0:
            transport = paramiko.Transport((self.ipaddress, 22))
            transport.start_client()
            transport.auth_publickey(self.username, self.key)
            sftp = paramiko.SFTPClient.from_transport(transport)
            for f in self.files:
                sftp.put(f, os.path.basename(f))
            sftp.close()
            transport.close()

    def cleanup(self):
        self.ssh_disconnect()
        cprint(self.name, 'blue', 'Terminating instance.')
        self.server.delete()
        if self.node_id == 0:
            self.sg.delete()

    def stop(self):
        self.cleanup()


def collect_args():

    parser = argparse.ArgumentParser(description='Launch a HPC cluster')
    parser.add_argument('-n', '--nodes', type=int,
                        required=False, default=3,
                        help='Number of nodes to launch')
    parser.add_argument('-i', '--image-id', type=str,
                        required=False,
                        default='374bfaec-70ad-4d84-9c08-c03938b2de41',
                        help='ID of the image to use for all nodes')
    parser.add_argument('-f', '--flavor', type=str,
                        required=False, default=0,
                        help='Instance flavor to use for all nodes')
    parser.add_argument('-c', '--commands-file', type=str,
                        required=False, default=None,
                        help='External file containing a list of commands to run on the head node')
    parser.add_argument('-u', '--username', type=str,
                        required=False, default='ubuntu',
                        help='Username to login to the nodes')
    parser.add_argument('-j', '--job-name', type=str,
                        required=False, default='HPC',
                        help='Optional job name to identify nodes')
    parser.add_argument('-p', '--packages', type=str,
                        required=False, nargs='+',
                        default=['openmpi1.5-bin', 'libopenmpi1.5-dev', 'gcc', 'make'],
                        help='Additional packages to install')
    parser.add_argument('-F', '--files', type=str, default=[],
                        required=False, nargs='+',
                        help='Files to upload to each node')
    return parser


def get_extra_commands(commands_file):

    extra_cmds = []

    if commands_file is not None:
        try:
            f = open(commands_file, 'r')
            for line in f:
                extra_cmds.append(line)
            f.close()
        except Exception as e:
            cprint('Error opening file %s: %s' % (commands_file, e), 'red')

    return extra_cmds


def create_security_group(jobname, nc):

    sg_name = args.job_name + ' SG ' + str(datetime.datetime.now())
    sg_name = re.sub('[ :.]', '-', sg_name)
    sg = nc.security_groups.create(sg_name, sg_name)
    nc.security_group_rules.create(sg.id, 'tcp', '22', '22', '0.0.0.0/0')

    return sg


def get_keystone_client():

    auth_username = os.environ.get('OS_USERNAME')
    auth_password = os.environ.get('OS_PASSWORD')
    auth_tenant = os.environ.get('OS_TENANT_NAME')
    auth_url = os.environ.get('OS_AUTH_URL')

    try:
        kc = ks_client.Client(username=auth_username,
                              password=auth_password,
                              tenant_name=auth_tenant,
                              auth_url=auth_url)
    except AuthorizationFailure as e:
        print e
        print 'Authorization failed, have you sourced your openrc?'
        sys.exit(1)

    return kc


def get_nova_client():

    auth_username = os.environ.get('OS_USERNAME')
    auth_password = os.environ.get('OS_PASSWORD')
    auth_tenant = os.environ.get('OS_TENANT_NAME')
    auth_url = os.environ.get('OS_AUTH_URL')

    nc = nova_client.Client(auth_username,
                            auth_password,
                            auth_tenant,
                            auth_url,
                            service_type='compute')
    return nc


def get_keys(nova_keys):

    ssh_agent = paramiko.Agent()
    agent_keys = ssh_agent.get_keys()
    if len(agent_keys) == 0:
        cprint('No ssh-agent keys found.', 'red')
        print 'Start an agent using the following command:'
        print '# eval `ssh-agent`'
        print 'and add a key:'
        print '# ssh-add'
        print
        print 'If you don\'t have a keypair, you can create one as follows:'
        print '# ssh-keygen'
        return False

    if len(nova_keys) == 0:
        cprint('No nova keys found.', 'red')
        print 'Please upload your ssh key using nova or the dashboard'
        return False

    matching_key = False
    for agent_key in agent_keys:
        for nova_key in nova_keys:
            key1 = agent_key.get_name() + ' ' + agent_key.get_base64()
            key2 = nova_key.public_key[0:len(key1)]
            if key1 == key2:
                matching_key = True
                key_contents = key1
                break

    if matching_key:
        key = nova_key.name
        cprint('Found a matching nova ssh key in your agent => %s' % key, 'green')
        cprint(key_contents, 'yellow')
        print 'Using this key to ssh to the cluster.'
        return key, agent_key
    else:
        cprint('No matching ssh keys found in your agent or in nova.', 'red')
        print 'Please add your key using ssh-add and then upload it to nova'
        return False


def check_files(files):

    for f in files:
        if not os.path.isfile(f):
            cprint('Specified file does not exist', 'red', f)
            sys.exit(1)


def launch_cluster(nc, nova_key, local_key, args):

    extra_cmds = get_extra_commands(args.commands_file)
    sg = create_security_group(args.job_name, nc)

    threads = []
    ipaddrs = []
    event = threading.Event()

    try:
        for n in range(0, args.nodes):
            thread = hpcnode(node_id=n,
                             total_nodes=args.nodes,
                             nc=nc,
                             key_name=nova_key,
                             sg=sg,
                             ipaddrs=ipaddrs,
                             event=event,
                             image=args.image_id,
                             flavor=args.flavor,
                             username=args.username,
                             name=args.job_name,
                             extra_cmds=extra_cmds,
                             packages=args.packages,
                             files=args.files,
                             key=local_key)
            thread.start()
            threads.append(thread)
    except Exception as e:
        cprint('Unable to start thread: %s' % e, 'red')

    for thread in threads:
        thread.join()


if __name__ == '__main__':

    args = collect_args().parse_args()

    kc = get_keystone_client()
    nc = get_nova_client()

    nova_key, local_key = get_keys(nc.keypairs.list())
    if not nova_key or not local_key:
        sys.exit(1)

    check_files(args.files)

    launch_cluster(nc, nova_key, local_key, args)
