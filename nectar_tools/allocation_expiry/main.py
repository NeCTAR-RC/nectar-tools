#!/usr/bin/env python


#Automated query of Allocation Management System db run once a day to find upcoming expiry allocations (proposing to send when 80% of time allocated is reached or 1 month to expiry whichever is less).


#Email sent (see above) to tenant manager and all users ccd and alert put in dashboard notifying of upcoming expiry.


#Query Allocation Management System db for expired projects and also check that allocation extension request has not been logged. If allocation extension request submitted dont start expiry process if status is pending.

#Restrict access to expired allocations initially by reducing quota to zero for one month following expiry. 

#After 1 month from expiry, archive snapshots of images and volume data to Swift and suspend object data already on Swift for allocations that have expired and do not have an allocation extension request currently logged at time of expiry date 

#Update Allocation Management System DB to change allocation status to archived noting upcoming deletion date.


#Upon expiry date an email is sent to the tenant manager notifying that instances, volume data and object data has been suspended/archived and will be available for retrieval for 3 months and how they can retrieve the archived images and data. Also advise, that after 3 months (date to be provided) the archived instances and data will be deleted and wont be available for retrieval.


#Upon deletion date (3 months after expiry date) delete images and data for allocation.


#Update allocation record in Allocation Management System with status as deleted and date of deletion.

import logging

from nectar_tools import log
from nectar_tools.allocation_expiry import expirer
LOG = logging.getLogger(__name__)



def main():
    log.setup()
    k_client = auth.get_keystone_client()
    projects = [k_client.projects.get('44c797584c8241bb9a8de708ba0a072f')]
    expirer = expirer.NectarExpirer()
    for project in projects:
        expirer.handle_project(project)
    #allocation = session.get_pending_allocation('44c797584c8241bb9a8de708ba0a072f')
    #import pdb; pdb.set_trace()


if __name__ == '__main__':
    main()
