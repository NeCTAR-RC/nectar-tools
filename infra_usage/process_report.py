from collections import defaultdict
import time

from util_nova import returnNodes, statsCount, totalVMType
from util_nova import returnServers, getResources
from util_nova import getAvailFlav, filterAz
from util_report import printPretty2, printPretty3, processConfig
from multiprocessing import Process, Queue


def compute_stats(node_name, zone, cell_name, client):
    node_info = returnNodes(client, zone, cell_name)
    nodes_count = len(node_info)
    nodes_rc = statsCount(getResources(node_info, client))
    stats = {'node_name': node_name,
             'node_count': nodes_count}
    for metric, value in nodes_rc.items():
        stats[metric] = value
    return stats


def flavor_stats(node_name, _az2, dic, client):
    type_ = totalVMType(dic, returnServers(client, _az2))
    if 'others' in list(type_.elements()):
        others = type_['others']
    else:
        others = 0

    stats = {'node_name': node_name,
             'total_s': type_['m1.small'],
             'total_m': type_['m1.medium'],
             'total_l': type_['m1.large'],
             'total_xl': type_['m1.xlarge'],
             'total_xxl': type_['m1.xxlarge'],
             'oth': others}
    return stats


def gather_all_stats(node_name, _az2, dic, zone, cell_name, client, queue=None):

    startTime = time.time()

    print "Getting data from zone %s" % node_name
    stats = {"cell_name": cell_name}
    stats.update(compute_stats(node_name, zone, cell_name, client))
    stats.update(flavor_stats(node_name, _az2, dic, client))
    print "%s done , took %0.2f secs" % (node_name, (time.time() - startTime))

    if queue:
        queue.put(stats)
    else:
        return stats


def gather_compute_stats(node_name, zone, cell_name, client, queue=None):

    startTime = time.time()

    print "Getting data from zone %s" % node_name
    stats = {"cell_name": cell_name}
    stats.update(compute_stats(node_name, zone, cell_name, client))
    print "%s done , took %0.2f secs" % (node_name, (time.time() - startTime))

    if queue:
        queue.put(stats)
    else:
        return stats


def combineResource(cells_data):
    result = defaultdict(int)

    for cell_data in cells_data:
        for metric, value in cell_data.items():
            if metric in ["node_name", "cell_name"]:
                continue
            result[metric] += value

    result["percent_cores_utilised"] = (float(result["used_cores"])
                                        / result["total_cores"]) * 100
    result["percent_memory_utilised"] = (float(result["used_memory"])
                                         / result["total_memory"]) * 100
    return result


def collect_all(client, zone, opt=None):
    flav = getAvailFlav(client)
    cells = filterAz(client, zone)
    timeout = processConfig('config', 'timeout')
    if opt is True:
        jobs = []
        for i, cell in enumerate(cells):
            cell["queue"] = Queue()

            p = Process(name=i, target=gather_all_stats,
                        args=(cell["cell"], cell["host_name"], flav,
                              zone, cell["fq_cell"], client, cell["queue"]))
            jobs.append(p)
            p.start()

        for p in jobs:
            p.join(int(timeout))
            if p.is_alive():
                p.terminate()
                return False

        html_array = []
        for cell in cells:
            html_array.append(cell["queue"].get())

        return html_array
    else:
        if cell in cells:
            index_id = cell['cell'].index(opt)
        a_name = cell['fq_cell'][index_id]
        c_name = cell['host_name'][index_id]

        return gather_all_stats(opt, c_name, flav, zone, a_name, client)


def collect_compute(client, zone, target_cell=None):
    cells = filterAz(client, zone)
    timeout = processConfig('config', 'timeout')
    if target_cell is None:
        jobs = []
        for i, cell in enumerate(cells):
            cell["queue"] = Queue()

            p = Process(name=i, target=gather_compute_stats,
                        args=(cell["cell"], zone,
                              cell["fq_cell"], client,
                              cell["queue"]))
            jobs.append(p)
            p.start()

        for p in jobs:
            p.join(int(timeout))
            if p.is_alive():
                p.terminate()
                return False

        html_array = []
        for cell in cells:
            html_array.append(cell["queue"].get())

        return html_array
    else:
        for cell in cells:
            if cell["cell"] == target_cell:
                a_name = cell['fq_cell']
                break
        else:
            raise Exception("Can't find cell.")

        return [gather_compute_stats(target_cell, zone, a_name, client)]


def printOptions(data1, data_2=None, options=None):

    if options is None:
        printPretty2(data1, wrap=60)
    elif options == 'all':
        for i in data1:
            printPretty2(i, wrap=60)
        printPretty3(data_2, wrap=60)
