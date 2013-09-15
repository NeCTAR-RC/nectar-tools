from report_options import getArgs
import sys
from util_report import templateLoader, multiCSVNode
from util_report import createCSVFileCloud, emailUser
from util_report import createCSVFileNode, processConfig
from util_nova import createNovaConnection
from process_report import runCollect, combineResource, printOptions


def main():

    username = processConfig('production', 'user')
    key = processConfig('production', 'passwd')
    tenant_name = processConfig('production', 'name')
    url = processConfig('production', 'url')
    zone = processConfig('config', 'zone')
    client = createNovaConnection(username, key, tenant_name, url)
    az = processConfig('config', 'az')
    opt_ = getArgs()

    if opt_.t is None:
        data = runCollect(client, zone, opt=True)
        data2 = combineResource(data)

        if opt_.o is 'n':
            printOptions(data, data_2=data2, options='all')

        elif opt_.o == 'html':
            templateLoader(data, data2)

        elif opt_.o == 'csv':
            multiCSVNode(data)
            createCSVFileCloud(data2)

        elif opt_.o == 'both':
            templateLoader(data, data2)
            multiCSVNode(data)
            createCSVFileCloud(data2)

        elif opt_.o == 'email':
            file_l = templateLoader(data, data2, opt='email')
            emailUser(file_l)

    elif opt_.t in az:
        data = runCollect(client, zone, opt=opt_.t)
        if opt_.o is 'n':
            printOptions(data)

        elif opt_.o == 'html':
            templateLoader(data, cell=opt_.t)

        elif opt_.o == 'csv':
            createCSVFileNode(data)

        elif opt_.o == 'both':
            templateLoader(data, cell=opt_.t)
            createCSVFileNode(data)

        elif opt_.o == 'email':
            file_l = templateLoader(data, cell=opt_.t, opt='email')
            emailUser(file_l)

    else:
        print "Error!, cell %s not found. Current cell %s " % (opt_.t,
                                                               az)
        return sys.exit(1)
