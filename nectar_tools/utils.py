import re


PT_RE = re.compile(r'^pt-\d+$')


def valid_project_trial(project):
    return PT_RE.match(project.name)


def valid_project_allocation(project):
    return not valid_project_trial(project)


def get_resources(api_call, mark_name, **kwargs):
    results = api_call(kwargs)
    while (True):
        next = api_call(kwargs, marker=results[-1].get(mark_name))
        if len(next) == 0:
            break
        results += next
    return results
