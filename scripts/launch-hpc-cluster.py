#!/usr/bin/env python

import sys
import os
import time
import datetime
import threading
import traceback
import paramiko

from keystoneclient.v2_0 import client as ks_client
from novaclient.v1_1 import client as nova_client
import glanceclient as glance_client


class launch_hpcnode(threading.Thread):

    def __init__(self, node_id, total, nc, key_name, sg, ipaddrs, event):
        threading.Thread.__init__(self)
        self.node_id = node_id
        if node_id == 0:
            self.name = "Head Node"
        else:
            self.name = "Node %s" % node_id
        self.total = total
        self.sg = sg
        self.ipaddrs = ipaddrs
        self.event = event
        self.server = nc.servers.create(name="%s" % self.name,
                                        image="0824aac4-91a9-4e1d-ad86-02ce6443d4b1",
                                        flavor="0",
                                        key_name=key_name,
                                        security_groups=[sg.name, ])
        self.username = 'ubuntu'

    def run(self):

        self.wait_for_boot()
        self.wait_for_ipaddress()

        try:
            self.ssh_connect()
            init_cmds = ['apt-get update', 'aptitude -y full-upgrade',
                         'apt-get -y install openmpi1.5-bin libopenmpi1.5-dev gcc make']
            for cmd in init_cmds:
                self.ssh_cmd(cmd, sudo=True)
            self.client.close()
            self.server.reboot()
            time.sleep(10)
            self.wait_for_boot()
            while len(self.ipaddrs) != self.total:
                self.event.wait()
            if self.node_id == 0:
                self.ssh_connect()
                for ipaddr in self.ipaddrs:
                    self.sg_rules_udp = nc.security_group_rules.create(self.sg.id,
                                                                       'udp', '1', '65535', "%s/32" % ipaddr)
                    self.sg_rules_tcp = nc.security_group_rules.create(self.sg.id,
                                                                       'tcp', '1', '65535', "%s/32" % ipaddr)
                    mpi_cmds = ["echo %s >> mpi_hosts" % ipaddr,
                                "ssh-keyscan %s >> .ssh/known_hosts" % ipaddr]
                    for cmd in mpi_cmds:
                        self.ssh_cmd(cmd)

        except Exception, e:
            print '*** Caught exception: ' + str(e.__class__) + ': ' + str(e)
            traceback.print_exc()
            try:
                self.cleanup()
            except:
                pass

    def check_boot(self):
        try:
            boot_finished = self.server.get_console_output().find("cloudinit boot finished")
            if boot_finished > 0:
                return True
        except Exception:
            return False

    def wait_for_boot(self):
        boot_finished = self.check_boot()
        print "%s: Waiting for VM to boot, please be patient." % self.name
        while boot_finished is not True:
            try:
                boot_finished = self.check_boot()
            except Exception:
                pass
            time.sleep(5)
        print "%s: Boot finished." % self.name

    def wait_for_ipaddress(self):
        print "%s: Waiting for IP address, please be patient." % self.name
        self.ipaddress = 0
        while self.ipaddress == 0:
            try:
                self.ipaddress = self.server.networks.values()[0][0]
            except IndexError:
                pass
            time.sleep(5)
        self.ipaddrs.append(self.ipaddress)
        self.event.set()
        print "%s IP address: %s" % (self.name, self.ipaddress)

    def ssh_cmd(self, cmd, sudo=False):
        if sudo:
            full_cmd = "sudo %s" % cmd
        else:
            full_cmd = cmd
        stdin, stdout, stderr = self.client.exec_command(full_cmd)
        print "%s@%s $ %s" % (self.username, self.ipaddress, full_cmd)
        channel = stdout.channel
        status = channel.recv_exit_status()
        for line in stdout:
            print line.strip('\n')
        if status != 0:
            print '*** An error occured running remote commands:'
            for line in stderr:
                print line.strip('\n')
            raise

    def ssh_connect(self):
        try:
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.client.connect(hostname=self.ipaddress, username=self.username)
        except:
            raise

    def cleanup(self):
        try:
            self.client.close()
        except:
            pass
        self.server.delete()
        if self.node_id == 0:
            self.sg.delete()

    def stop(self):
        self.cleanup()

if __name__ == '__main__':

    auth_username = os.environ.get('OS_USERNAME')
    auth_password = os.environ.get('OS_PASSWORD')
    auth_tenant = os.environ.get('OS_TENANT_NAME')
    auth_url = os.environ.get('OS_AUTH_URL')

    if not auth_username or not auth_password or not auth_tenant or not auth_url:
        print '*** The following opentstack environment variables were not found:'
        print 'OS_USERNAME'
        print 'OS_PASSwORD'
        print 'OS_TENANT_NAME'
        print 'OS_AUTH_URL'
        print
        print 'Have you run "source openrc.sh"?'
        sys.exit(1)

    kc = ks_client.Client(username=auth_username,
                          password=auth_password,
                          tenant_name=auth_tenant,
                          auth_url=auth_url)

    token = kc.auth_token
    image_endpoint = kc.service_catalog.url_for(service_type='image')

    gc = glance_client.Client('1', image_endpoint, token=token)
    nc = nova_client.Client(auth_username,
                            auth_password,
                            auth_tenant,
                            auth_url,
                            service_type="compute")

    ssh_agent = paramiko.Agent()
    agent_keys = ssh_agent.get_keys()
    if agent_keys == ():
        print '*** No ssh-agent keys found.'
        print 'Start an agent using the following command:'
        print '# eval `ssh-agent`'
        print 'and add a key:'
        print '# ssh-add'
        print
        print 'If no keys are found, you can create one using the following command:'
        print '# ssh-keygen'
        sys.exit(1)

    nova_keys = nc.keypairs.list()
    if len(nova_keys) == 0:
        print '*** No nova keys found.'
        print 'Please upload your ssh key using nova or the dashboard'
        sys.exit(1)

    matching_key = False
    for agent_key in agent_keys:
        for nova_key in nova_keys:
            key1 = agent_key.get_name() + ' ' + agent_key.get_base64()
            key2 = nova_key.public_key[0:len(key1)]
            if key1 == key2:
                matching_key = True
                break

    if matching_key:
        print 'Found matching nova ssh key in your agent: %s' % nova_key.name
        print key1
        print 'Using this key to ssh to the cluster.'
    else:
        print '*** No matching ssh keys found in your agent or in nova.'
        print 'Please add your key using ssh-add and then upload it to nova'
        sys.exit(1)

    total_nodes = 3
    ipaddrs = []
    threads = []
    event = threading.Event()
    sg_name = 'SG-' + str(datetime.datetime.now()).replace(' ', '-').replace(':', '-').replace('.', '-')
    sg = nc.security_groups.create(sg_name, sg_name)
    sg_rules_ssh = nc.security_group_rules.create(sg.id, 'tcp', '22', '22', '0.0.0.0/0')

    try:
        for n in range(0, total_nodes):
            thread = launch_hpcnode(node_id=n,
                                    total=total_nodes,
                                    nc=nc,
                                    key_name=nova_key.name,
                                    sg=sg,
                                    ipaddrs=ipaddrs,
                                    event=event)
            thread.start()
            threads.append(thread)
    except Exception as e:
        print "*** Unable to start thread: %s" % e

    for thread in threads:
        thread.join()
