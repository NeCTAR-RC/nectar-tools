import re
import collections
import time
from util_report import process_config
from novaclient.v1_1 import client
from novaclient.exceptions import ClientException, BadRequest


def createNovaConnection(username, key, tenant_id, a_url):
    try:
        conn = client.Client(username=username, api_key=key,
                             project_id=tenant_id, auth_url=a_url)
        return conn
    except ClientException:
        return False


def filter_az(client, zone):
    fil_az, fil_name, fil_cell, fil_pcell, fil_host = ([] for i in range(5))
    try:
        host_server = RequestRetries('host_list_all', client, zone)
        while host_server:
            for i in host_server:
                fil_pcell.append(i.host_name.split('@')[0])    
                fil_name = sorted(list(set(fil_pcell)))
        
            for i in fil_name:
                fil_az.append(i.split('!'))
    
            for i in fil_az:
                if len(i) > 2:
                    fil_cell.append(i[2])
                else:
                    fil_cell.append(i[1])
                    
                    

            return fil_name, fil_cell
        return False

    except BadRequest:
        return False


def return_nodes(client, zone, search_):

    query = re.compile(r'%s@' % search_)
    host_count = []
    for i in client.hosts.list_all(zone):
        if query.search(i.host_name):
            host_count.append(i.host_name)

    return host_count



def hypervisor_count(client, search_):
    query = re.compile(r'%s@' % search_)
    server_list = RequestRetries('host_list', client)
        
    
    data = [x for x in server_list if query.search(x.id)]

    return data


def hypervisor_usage(data):
    total_avail = total_used = total_avail_mem = total_used_mem = 0
    for i in data:
        print i.__dict__
        total_avail += int(i.vcpus)
        total_used += int(i.vcpus_used)
        total_avail_mem += int(i.memory_mb)
        total_used_mem += int(i.memory_mb_used)

    resources = {'avail_cpu': total_avail, 'avail_mem': total_avail_mem,
                    'used_cpu': total_used, 'used_mem': total_used_mem}
    return resources


def stats_count(_data):
    fc = _data.get('avail_cpu')
    fm = (_data.get('avail_mem') / 1024)
    uc = _data.get('used_cpu')
    um = (_data.get('used_mem') / 1024)
    ac = fc - uc
    am = fm - um
    resources = {'nac': fc, 'nam': fm, 'nuc': uc, 'num': um,
                'nfc': ac, 'nfm': am}
    return resources


def get_Resources(cell, client):

    res_l = []
    total_avail = total_used = total_avail_mem = total_used_mem = 0

    for i in cell:
        out_ = RequestRetries('gr', client, i)
        if out_:
            res_l.append(out_)

    for r in res_l:
        total_avail += int(r[0]._info['resource'].
                           get('cpu'))
        total_used += int(r[1]._info['resource'].
                          get('cpu'))
        total_avail_mem += int(r[0]._info['resource'].
                               get('memory_mb'))
        total_used_mem += int(r[1]._info['resource']
                              .get('memory_mb'))

    resources = {'avail_cpu': total_avail, 'avail_mem': total_avail_mem,
                    'used_cpu': total_used, 'used_mem': total_used_mem}

    return resources


def returnServers(client, data):
    count_all = []
    for d in data:
        args_a = {'all_tenants': 1, 
                  'host': d.hypervisor_hostname.split('.')[0]
                  }
        server = client.servers.list(search_opts=args_a)
        
        if not server:
            args_a = {'all_tenants': 1, 
                  'host': d.hypervisor_hostname
                  }
            server = client.servers.list(search_opts=args_a)
            
        for i in server:
            if isinstance(i.__dict__.get('OS-EXT-SRV-ATTR:host'), unicode):
                count_all.append(i.flavor.get('id'))
    return count_all
                

def totalVMType(flavour_list, host):
    count = []
    for i in host:
        if i in flavour_list.values():
            for key, value in flavour_list.items():
                if value == i:
                    count.append(key)
        else:
            count.append('others')

    return collections.Counter(count)


def list_flavors(client):
    data_flav = {}
    for i in client.flavors.list(False):
        data_flav[i.name] = i.id

    return data_flav


def RequestRetries(meth, client, var_=None):

    attempt = process_config('config', 'retries')

    for x in xrange(int(attempt)):
        try:
            if meth == 'gr':
                return client.hosts.get(var_)
                break
            if meth == 'host_list':
                return client.hypervisors.list()
            if meth == 'host_list_all':
                return client.hosts.list_all(var_)
        except Exception:
            time.sleep(5)
    return False


    
