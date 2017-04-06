#!/usr/bin/env bash

set -o pipefail

TESTRARGS=$1

# --until-failure is not compatible with --subunit see:
#
# https://bugs.launchpad.net/testrepository/+bug/1411804
#
# this work around exists until that is addressed
#python setup.py testr init
if [[ "$TESTARGS" =~ "until-failure" ]]; then
    python setup.py testr --slowest --testr-args="$TESTRARGS"
elif hash subunit-trace 2>/dev/null; then
    python setup.py testr --slowest --testr-args="--subunit $TESTRARGS" | subunit-trace -f
else
    python setup.py testr --slowest --testr-args="$TESTRARGS"
fi
