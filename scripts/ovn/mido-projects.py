#!/usr/bin/env python

from nectar_tools import auth


def run():
    session = auth.get_session()
    client = auth.get_neutron_client(session)
    k_client = auth.get_keystone_client(session)
    projects = []
    floatingips = client.list_floatingips()['floatingips']
    for ip in floatingips:
        projects.append(ip.get('tenant_id'))
    routers = client.list_routers()['routers']
    for r in routers:
        projects.append(r.get('tenant_id'))
    networks = client.list_networks()['networks']
    for n in networks:
        projects.append(n.get('tenant_id'))

    all_projects = k_client.projects.list()
    tempest_projects = []
    for p in all_projects:
        if 'tempest' in p.name:
            tempest_projects.append(p.id)
    projects += tempest_projects

    projects = list(set(projects))
    for project_id in projects:
        if k_client.projects.check_tag(project_id, 'legacy-networking'):
            continue
        # Don't tag projects that have ovn tag
        if k_client.projects.check_tag(project_id, 'ovn-networking'):
            continue
        k_client.projects.add_tag(project_id, 'legacy-networking')


if __name__ == '__main__':
    run()
