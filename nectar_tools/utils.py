import re

from nectar_tools import auth
from nectar_tools.expiry import archiver


PT_RE = re.compile(r'^pt-\d+$')


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


def read_file(uuid_file):
    """Get a list of UUIDs from a file.

    Can be project or user or image IDs
    """
    data = uuid_file.read()
    return data.split('\n')
