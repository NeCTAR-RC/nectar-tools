from util_nova import returnNodes, statsCount, totalVMType
from util_nova import returnServers, getResources
from util_nova import getAvailFlav, filterAz
from util_report import printPretty2, printPretty3, processConfig
from multiprocessing import Process, Queue
import time


def computeStats(node_name, _az2, dic, zone, i, client, r_outs=None, opt=None):

    startTime = time.time()

    print "Getting data from zone %s" % node_name

    node_info = returnNodes(client, zone, i)
    nodes_count = len(node_info)

    nodes_rc = statsCount(getResources(node_info,
                                          client))
    type_ = totalVMType(dic, returnServers(client, _az2))
    if 'others' in list(type_.elements()):
        others = type_['others']
    else:
        others = 0

    print "%s done , took %0.2f secs" % (node_name, (time.time() - startTime))

    stats_q = {'node_name': node_name, 'node_count': nodes_count,
                'nac': nodes_rc.get('nac'), 'nam': nodes_rc.get('nam'),
                'nuc': nodes_rc.get('nuc'), 'num': nodes_rc.get('num'),
                'nfc': nodes_rc.get('nfc'), 'nfm': nodes_rc.get('nfm'),
                't_s': type_['m1.small'], 't_m': type_['m1.medium'],
                't_l': type_['m1.large'], 't_xl': type_['m1.xlarge'],
                't_xxl': type_['m1.xxlarge'], 'oth': others
                }

    if opt == True:
        r_outs.put(stats_q)
    else:
        return stats_q


def combineResource(data_array):
    t_nodes = t_cores = t_mem = 0
    u_cores = u_mem = f_cores = f_mem = 0
    t_s = t_m = t_l = t_xl = t_xxl = oth = 0

    for i in data_array:
        t_nodes += i.get('node_count')
        t_cores += i.get('nac')
        t_mem += i.get('nam')
        u_cores += i.get('nuc')
        u_mem += i.get('num')
        f_cores += i.get('nfc')
        f_mem += i.get('nfm')
        t_s += i.get('t_s')
        t_m += i.get('t_m')
        t_l += i.get('t_l')
        t_xl += i.get('t_xl')
        t_xxl += i.get('t_xxl')
        oth += i.get('oth')

    data_dict = {'total_nodes': t_nodes, 'total_cores': t_cores,
              'total_mem': t_mem, 'used_cores': u_cores,
              'used_mem': u_mem, 'free_cores': f_cores,
              'free_mem': f_mem, 'total_small': t_s,
              'total_medium': t_m, 'total_large': t_l,
              'total_xl': t_xl, 'total_xxl': t_xxl,
              'oth': oth
              }

    return data_dict


def runCollect(client, zone, opt=None):
    flav = getAvailFlav(client)
    cell = filterAz(client, zone)
    timeout = processConfig('config', 'timeout')
    if opt == True:
        jobs = []
        r_outs = [Queue() for q in range(len(cell) + 1)]

        for z, i in enumerate(cell[0]):
            p = Process(name=z, target=computeStats,
                    args=(cell[1][z], cell[2][z], flav,
                          zone, i, client, r_outs[z],
                          True)
                        )
            jobs.append(p)
            p.start()

        for p in jobs:
            p.join(int(timeout))
            if p.is_alive():
                p.terminate()
                return False

        html_array = []
        for q in r_outs:
            html_array.append(q.get())

        return html_array
    else:
        if opt in cell[1]:
            index_id = cell[1].index(opt)
        a_name = cell[0][index_id]
        c_name = cell[2][index_id]

        return computeStats(opt, c_name, flav, zone, a_name, client,
                                        r_outs=None, opt=None)


def printOptions(data1, data_2=None, options=None):

    if options == None:
        printPretty2(data1, wrap=60)
    elif options == 'all':
        for i in data1:
            printPretty2(i, wrap=60)
        printPretty3(data_2, wrap=60)
