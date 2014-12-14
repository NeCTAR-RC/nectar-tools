import sys
from report_options import get_args
from util_report import templateLoader, multiCSVNode
from util_report import createCSVFileCloud, email_user
from util_report import createCSVFileNode, process_config
from util_report import send_alert
from process_report import add_results, print_options, collect_data
from nova_connection import create_connection


def main():

    zone = process_config('config', 'zone')
    client = create_connection()
    az = process_config('config', 'az')
    opt_ = get_args()

    if opt_.t is None:
        data = collect_data(client, zone, opt=True)
        if data != False:
            data2 = add_results(data)
            if opt_.o is 'n':
                print_options(data, data_2=data2, options='all')

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
                email_user(file_l)
        else:
            send_alert()
            print "Error!, failed to contact api server1"
            return sys.exit(1)

    elif opt_.t in az:
        data = collect_data(client, zone, opt=opt_.t)
        if data !=False:
            if opt_.o is 'n':
                print_options(data)

            elif opt_.o == 'html':
                templateLoader(data, cell=opt_.t)

            elif opt_.o == 'csv':
                createCSVFileNode(data)

            elif opt_.o == 'both':
                templateLoader(data, cell=opt_.t)
                createCSVFileNode(data)

            elif opt_.o == 'email':
                file_l = templateLoader(data, cell=opt_.t, opt='email')
                email_user(file_l)
        else:
            print "Error!, failed to contact api server"
            return sys.exit(1)

    else:
        print "Error!, cell %s not found. Current cell %s " % (opt_.t,
                                                               az)
        return sys.exit(1)
