#!/bin/bash

MODULE_ROOT=/etc/puppet/modules/testing

for module in `ls $MODULE_ROOT`
do
    cd $MODULE_ROOT/$module
    if [ -d ".git" ]
    then
        git add .
        git commit -am "End of day cleanse"
        today=`date --iso-8601`
        git branch $today
        git checkout master
        git reset --hard origin/master
    fi
done
