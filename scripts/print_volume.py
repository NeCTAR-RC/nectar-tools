#============================================================#
#                                                            #
# print_volume.py                                            #
#                                                            #
# Retrieves & prints volume information.                     #
#                                                            #
# Copyright 2011 Network Appliance, Inc. All rights          #
# reserved. Specifications subject to change without notice. #
#                                                            #
# This SDK sample code is provided AS IS, with no support or #
# warranties of any kind, including but not limited to       #
# warranties of merchantability or fitness of any kind,      #
# expressed or implied.  This code is subject to the license #
# agreement that accompanies the SDK.                        #
#                                                            #
# Requirements:                                              #
#                                                            #
#     NetApp SDK zip archive can be downloaded from:         #
#     http://115.146.87.0/netapp/                            #
#                                                            #
#     Unzip the SDK archive and export an absolute path to   #
#     lib/python/NetApp directory as NETAPPSDK_PATH variable #
#                                                            #
#============================================================#

import os
import sys
sdk_path = os.environ.get('NETAPPSDK_PATH')
if not sdk_path:
    print 'Run `export NETAPPSDK_PATH="<path to NetApp SDK>"`'
    sys.exit(1)
sys.path.append(sdk_path)
from NaServer import NaServer

def get_volume_info():


    args = len(sys.argv) - 1

    if(args < 3):
        print_usage()

    filer = sys.argv[1]
    user = sys.argv[2]
    pw = sys.argv[3]

    if(args == 4):
        volume = sys.argv[4]

    s = NaServer(filer, 1, 3)
    response = s.set_style('LOGIN')
    if(response and response.results_errno() != 0 ):
        r = response.results_reason()
        print ("Unable to set authentication style " + r + "\n")
        sys.exit (2)

    s.set_admin_user(user, pw)
    response = s.set_transport_type('HTTP')

    if(response and response.results_errno() != 0 ):
        r = response.results_reason()
        print ("Unable to set HTTP transport " + r + "\n")
        sys.exit (2)

    if(args == 3):
        out = s.invoke("volume-get-iter")

    else:
        out = s.invoke("volume-get-iter", "volume", volume)

    if(out.results_status() == "failed"):
        print (out.results_reason() + "\n")
        sys.exit (2)

    result = out.child_get('attributes-list').children_get()

    fmt = '{0:25} {1:25} {2:7} {3:>12} / {4:15}'
    print fmt.format('Volume Owner', 'Volume Name', 'State', 'Total Space', 'Used Space')
    print "-"*90
    for vol in result:
        vol_name = vol.child_get("volume-id-attributes").child_get_string("name")
        vol_owner = vol.child_get("volume-id-attributes").child_get_string("owning-vserver-name")
        state = vol.child_get("volume-state-attributes").child_get_string("state")
        if state != "online":
            fmt = '{0:25} {1:25} {2:>6}'
            print fmt.format(vol_owner, vol_name, state)
        else:
            size_total = vol.child_get("volume-space-attributes").child_get_string("size-total")
            size_total = float(size_total) / 1024 / 1024 / 1024
            size_used = vol.child_get("volume-space-attributes").child_get_string("size-used")
            size_used = float(size_used) / 1024 / 1024 / 1024
            fmt = '{0:25} {1:25} {2:>6} {3:10g} GB / {4:2g} GB'
            print fmt.format(vol_owner, vol_name, state, size_total, size_used)

def print_usage():
    print ("Usage: \n")
    print ("python print_volume.py <filer> <user> <password>")
    print (" [<volume>]\n")
    sys.exit (1)

get_volume_info()
