import re

from ordered_set import OrderedSet

from nectar_tools import auth
from nectar_tools import config
from nectar_tools.expiry import archiver


CONF = config.CONFIG
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
    if allocation.national:
        return []
    elif allocation.associated_site is not None:
        return zone_map.get(allocation.associated_site, [])
    else:
        # This should not happen.  A local allocation should always
        # have a non-null associated site.  If it does happen, we
        # treat it like a national allocation.
        return []


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


def get_emails(users):
    """Returns a list of emails for a list of keystone users"""
    emails = []
    for user in users:
        if user.enabled or getattr(user, 'inactive', False):
            email = getattr(user, 'email', None)
            if is_email_address(email):
                emails.append(email.lower())
    return emails


def get_project_users(client, project, role):
    """Returns a list of users of a project based on role"""
    members = client.role_assignments.list(
        project=project, role=role)
    users = []
    for member in members:
        users.append(client.users.get(member.user['id']))
    return users


# Freshdesk limits us to 49 CC's on an email ... sigh
MAX_CC_COUNT = 49


def get_project_recipients(client, project):
    """Returns emails for a project

    Will return a tuple with the first item
    being the primary recipient and the second
    being all other project managers and members
    """

    return _do_get_recipients(client, project)


def get_allocation_recipients(client, allocation):
    """Returns emails for a allocation

    Will return a tuple with the first item
    being the owner of the allocation and the second
    being all other project managers and members.
    Also included is the approver of the allocation
    """
    # For allocation case, the 'to' field of the notification email
    # should be the project allocation owner
    owner_email = allocation.contact_email.lower()
    approver_email = (allocation.approver_email.lower()
                      if is_email_address(allocation.approver_email) else None)

    return _do_get_recipients(client, allocation.project_id,
                              owner=owner_email, approver=approver_email)


def _do_get_recipients(client, project, owner=None, approver=None,
                       limit=MAX_CC_COUNT):
    managers = get_project_users(
        client, project,
        role=CONF.keystone.manager_role_id)
    members = get_project_users(
        client, project,
        role=CONF.keystone.member_role_id)
    manager_emails = get_emails(managers)
    member_emails = get_emails(members)
    approver_emails = [approver] if approver else []
    extra_emails = list(OrderedSet(manager_emails + approver_emails
                                   + member_emails))
    recipient = (owner if owner
                 else manager_emails[0] if manager_emails
                 else approver if approver
                 else member_emails[0])
    if recipient in extra_emails:
        extra_emails.remove(recipient)
    return (recipient, extra_emails[0:limit])
