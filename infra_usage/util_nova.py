import re
import collections
import time
from util_report import processConfig
from novaclient.v1_1 import client
from novaclient.exceptions import ClientException


def createNovaConnection(username, key, tenant_id, a_url):
    try:
        conn = client.Client(username=username, api_key=key,
                             project_id=tenant_id, auth_url=a_url)
        return conn
    except ClientException:
        return False


def filterAz(client, zone):

    fil_az, fil_name, fil_cell, fil_pcell, fil_host = ([] for i in range(5))
    for i in client.hosts.list_all(zone):
        fil_pcell.append(i.host_name.split('@')[0])
        fil_host.append(re.split(r'\d',
                                 i.host_name.split('@')[1].split('-')[0])[0])

    fil_name = sorted(list(set(fil_pcell)))
    for i in fil_name:
        fil_az.append(i.split('!'))

    for i in fil_az:
        if len(i) > 2:
            fil_cell.append(i[2])
        else:
            fil_cell.append(i[1])

    return fil_name, fil_cell, list(set(fil_host))


def returnNodes(client, zone, search_):

    query = re.compile(r'%s@' % search_)
    host_count = []
    for i in client.hosts.list_all(zone):
        if query.search(i.host_name):
            host_count.append(i.host_name)

    return host_count


def statsCount(_data):
    fc = _data.get('avail_cpu')
    fm = (_data.get('avail_mem') / 1024)
    uc = _data.get('used_cpu')
    um = (_data.get('used_mem') / 1024)
    ac = fc - uc
    am = fm - um
    resources = {'nac': fc, 'nam': fm, 'nuc': uc, 'num': um,
                'nfc': ac, 'nfm': am}
    return resources


def getResources(cell, client):

    res_l = []
    total_avail = total_used = total_avail_mem = total_used_mem = 0

    for i in cell:
        out_ = requestRetries('gr', client, i)
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


def returnServers(client, cell):

    count_all = []
    args_a = {'all_tenants': 1, 'host': cell}
    instances = client.servers.list(search_opts=args_a)
    for i in instances:
        if getattr(i, 'OS-EXT-SRV-ATTR:host') is not None:
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


def getAvailFlav(client):
    data_flav = {}
    for i in client.flavors.list(False):
        data_flav[i.name] = i.id

    return data_flav


def requestRetries(meth, client, var_=None):

    attempt = processConfig('config', 'retries')

    for x in xrange(int(attempt)):
        try:
            if meth == 'gr':
                return client.hosts.get(var_)
                break
        except ClientException:
            time.sleep(5)
    return False
