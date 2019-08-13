import datetime
import logging
import re

from dateutil.relativedelta import relativedelta

from nectar_tools import auth
from nectar_tools import exceptions
from nectar_tools.expiry import archiver

from nectarallocationclient import exceptions as allocation_exceptions
from nectarallocationclient import states as allocation_states
from nectarallocationclient.v1 import allocations


PT_RE = re.compile(r'^pt-\d+$')
LOG = logging.getLogger(__name__)

DATE_FORMAT = '%Y-%m-%d'
DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%SZ'


def valid_project_trial(project):
    return PT_RE.match(project.name)


def valid_project_allocation(project):
    return not valid_project_trial(project)


def get_compute_zones(session, allocation):
    """Returns a list of zones based on allocation home

    If national or no mapping then return []
    """
    a_client = auth.get_allocation_client(session)
    zone_map = a_client.zones.compute_homes()
    return zone_map.get(allocation.allocation_home, [])


def get_out_of_zone_instances(session, allocation, project):
    """Returns list of instances that a project has running in
    zones that it shouldn't based on its allocation home.
    """
    zones = get_compute_zones(session, allocation)
    if not zones:
        return []
    nova_archiver = archiver.NovaArchiver(
        {'project': project}, session)
    instances = nova_archiver._all_instances()
    out_of_zone = []
    for instance in instances:
        az = getattr(instance, 'OS-EXT-AZ:availability_zone')
        if az not in zones:
            # We set this attribute so we can use it in templating
            setattr(instance, 'availability_zone', az)
            out_of_zone.append(instance)
    return out_of_zone


def get_allocation(session, project_id, ignored=False,
                   force_no_allocation=False):
    a_client = auth.get_allocation_client(session)
    try:
        allocation = a_client.allocations.get_current(
            project_id=project_id)
    except allocation_exceptions.AllocationDoesNotExist:
        if ignored:
            return
        LOG.warn("%s: Allocation can not be found", project_id)
        if force_no_allocation:
            allocation = allocations.Allocation(
                None,
                {'id': 'NO-ALLOCATION',
                 'status': allocation_states.APPROVED,
                 'quotas': [],
                 'start_date': '1970-01-01',
                 'end_date': '1970-01-01'},
                None)
        else:
            raise exceptions.AllocationDoesNotExist(
                project_id=project_id)

    allocation_status = allocation.status

    if allocation_status in (allocation_states.UPDATE_DECLINED,
                             allocation_states.UPDATE_PENDING,
                             allocation_states.DECLINED):

        six_months_ago = datetime.datetime.now() - relativedelta(months=6)
        mod_time = datetime.datetime.strptime(
            allocation.modified_time, DATETIME_FORMAT)
        if mod_time < six_months_ago:
            approved = a_client.allocations.get_last_approved(
                project_id=project_id)
            if approved:
                LOG.debug("%s: Allocation has old unapproved application, "
                          "using last approved allocation",
                          project_id)
                LOG.debug("%s: Changing allocation from %s to %s",
                          project_id, allocation.id,
                          approved.id)
                allocation = approved

    allocation_status = allocation.status
    allocation_start = datetime.datetime.strptime(
        allocation.start_date, DATE_FORMAT)
    allocation_end = datetime.datetime.strptime(
        allocation.end_date, DATE_FORMAT)
    LOG.debug("%s: Allocation id=%s, status='%s', start=%s, end=%s",
              project_id, allocation.id,
              allocation_states.STATES[allocation_status],
              allocation_start.date(), allocation_end.date())
    return allocation
