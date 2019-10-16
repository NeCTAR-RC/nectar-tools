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
    nova_archiver = archiver.NovaArchiver(project, session)
    instances = nova_archiver._all_instances()
    out_of_zone = []
    for instance in instances:
        az = getattr(instance, 'OS-EXT-AZ:availability_zone')
        if az and az not in zones:
            # We set this attribute so we can use it in templating
            setattr(instance, 'availability_zone', az)
            out_of_zone.append(instance)
    return out_of_zone


def list_resources(list_method, marker_name='id', **list_method_kwargs):
    """get a list of all resources from an api call

    :param func list_method: api call used to generate list
    :param str marker_name: name of marker object in api_call
    :param kwargs (optional) **list_method_kwargs:
                             list_method **kwargs to pass through
    """
    results = list_method(**list_method_kwargs)
    if results:
        while (True):
            next = list_method(**list_method_kwargs,
                               marker=results[-1].get(marker_name))
            if len(next) == 0:
                break
            results += next
    return results


def read_file(uuid_file):
    """Get a list of UUIDs from a file.

    Can be project or user or image IDs
    """
    data = uuid_file.read()
    return data.split('\n')


def is_email_address(mail):
    if not mail:
        return False
    regex = re.compile(r"[^@]+@[^@]+\.[^@]+")
    return True if regex.match(mail) else False
