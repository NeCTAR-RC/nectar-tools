#!/usr/bin/env python

# image_test.py

import subprocess
import sys

"""
USAGE: ssh user@guest python < image_test.py

"""

oneliners = [
    ("ephemeral disk is ext4, read-write mounted on vdb",
        "grep '/dev/vdb.*ext4.*rw' /proc/mounts"),
    ("heat-cfn-tools installed",
        "which cfn-create-aws-symlinks cfn-get-metadata"
     + " cfn-push-stats cfn-hup cfn-init cfn-signal"),
    ("single ssh key for root",
        "/usr/bin/[ \"$(sudo wc -l /root/.ssh/authorized_keys |"
     + " cut -d ' ' -f1 )\" -eq 1 ]"),
    ("single ssh key for current user",
        "/usr/bin/[ $(wc -l ${HOME}/.ssh/authorized_keys |"
     + " cut -d ' ' -f1 ) -eq 1 ]"),
    ("fail2ban running", "pgrep fail2ban"),
    ("ntp running", "pgrep ntp"),
    ("no passwords in /etc/shadow", "test \"$(sudo cut -d ':'"
     + " -f 2 /etc/shadow | cut -d '$' -sf3)\" = ''"),
    ]


def shellout(cmd):
    out = subprocess.call(cmd, shell=True)
    return out


def main():
    total_result = 0
    for i in oneliners:
        result = shellout(i[-1])
        total_result += result
        print("%s returned %s" % (i[0], str(result)))
    if total_result > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
