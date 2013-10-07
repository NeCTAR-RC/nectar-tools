import re
import collections
import time
from functools import wraps
from util_report import processConfig
from novaclient.v1_1 import client
from novaclient.exceptions import ClientException


def retries(func):
    attempt = processConfig('config', 'retries')

    @wraps(func)
    def _decorator(*args, **kwargs):
        for x in xrange(int(attempt)):
            try:
                return func(*args, **kwargs)
            except ClientException:
                time.sleep(5)
        return func(*args, **kwargs)
    return _decorator


def createNovaConnection(username, key, tenant_id, auth_url):
    try:
        conn = client.Client(username=username, api_key=key,
                             project_id=tenant_id, auth_url=auth_url)
        return conn
    except ClientException:
        return False


def filterAz(client, zone):
    cells = []
    fq_cells = []  # the fully qualified cell names
    hosts = []
    for host in client.hosts.list_all(zone):
        cell_name, host_name = host.host_name.split('@')
        fq_cells.append(cell_name)
        hosts.append(re.split(r'\d', host_name.split('-')[0])[0])

    fq_cells = sorted(list(set(fq_cells)))
    for cell_name in fq_cells:
        cell_name = cell_name.split('!')
        if len(cell_name) > 2:
            cells.append(cell_name[2])
        else:
            cells.append(cell_name[1])

    return [dict([("fq_cell", fq_cell), ("cell", cell),
                  ("host_name", host_name)])
            for fq_cell, cell, host_name
            in zip(fq_cells, cells, list(set(hosts)))]


def returnNodes(client, zone, search_):

    query = re.compile(r'%s@' % search_)
    host_count = []
    for i in client.hosts.list_all(zone):
        if query.search(i.host_name):
            host_count.append(i.host_name)

    return host_count


def statsCount(data):
    total_cores = data.get('avail_cpu')
    total_memory = data.get('avail_mem') / 1024
    used_cores = data.get('used_cpu')
    used_memory = data.get('used_mem') / 1024
    free_cores = total_cores - used_cores
    free_memory = total_memory - used_memory
    resources = {'total_cores': total_cores,
                 'total_memory': total_memory,
                 'used_cores': used_cores,
                 'used_memory': used_memory,
                 'free_cores': free_cores,
                 'free_memory': free_memory}
    return resources


def getResources(cell, client):

    resources = []
    total_avail = total_used = total_avail_mem = total_used_mem = 0

    for i in cell:
        out = hosts(client, i)
        if out:
            resources.append(out)

    for r in resources:
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


@retries
def hosts(client, cell):
    return client.hosts.get(cell)


def returnServers(client, cell):

    count_all = []
    args_a = {'all_tenants': 1, 'host': cell}
    instances = client.servers.list(search_opts=args_a)
    for i in instances:
        if getattr(i, 'OS-EXT-SRV-ATTR:host', None):
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
