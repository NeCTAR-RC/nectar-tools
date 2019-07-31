import re


PT_RE = re.compile(r'^pt-\d+$')


def valid_project_trial(project):
    return PT_RE.match(project.name)


def valid_project_allocation(project):
    return not valid_project_trial(project)


def list_resources(list_method, marker_name='id', **list_method_args):
    """get a list of all resources from an api call

    :param func list_method: api call used to generate list
    :param str marker_name: name of marker object in api_call
    :param dict **list_method_args: list_method args to pass through
    """
    results = list_method(**list_method_args)
    if results:
        while (True):
            next = list_method(**list_method_args,
                               marker=results[-1].get(marker_name))
            if len(next) == 0:
                break
            results += next
    return results
