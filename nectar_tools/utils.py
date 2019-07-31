import re


PT_RE = re.compile(r'^pt-\d+$')


def valid_project_trial(project):
    return PT_RE.match(project.name)


def valid_project_allocation(project):
    return not valid_project_trial(project)


def list_resources(list_method, marker_name, **kwargs):
    results = list_method(**kwargs)
    if results:
        while (True):
            next = list_method(**kwargs, marker=results[-1].get(marker_name))
            if len(next) == 0:
                break
            results += next
    return results
