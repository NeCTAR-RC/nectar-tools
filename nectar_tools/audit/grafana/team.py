import logging

import keystoneauth1

from nectar_tools.audit.grafana import base
from nectar_tools import config
from nectar_tools.audit.grafana import dashboards

CONF = config.CONFIG
LOG = logging.getLogger(__name__)


class TeamAuditor(base.GrafanaAuditor):

    def __init__(self, ks_session):
        super(TeamAuditor, self).__init__(ks_session=ks_session)
        self.projects = None
        self.role_assignments = None

    def _get_projects(self):
        if self.projects is None:
            self.projects = self.k_client.projects.list(domain='default',
                                                        enabled=True)
        return self.projects

    def get_members(self, project):
        if self.role_assignments is None:
            self.role_assignments = self.k_client.role_assignments.list(
                role=CONF.keystone.member_role_id, include_names=True)
        return members

    def ensure_team_and_members(self):
        for project in self._get_projects():
            team = None
            teams = self.g_client.teams.search_teams(query=project.name)
            if teams:
                team = teams[0]
                continue
            if not team:
                team = self.g_client.teams.create_team(name=project.name)
            try:
                folder = self.g_client.folder.get_folder(project.id)
            except Exception:
                folder = self.g_client.folder.create_folder(project.name,
                                                            project.id)

            if 'teamId' in team:
                team['id'] = team['teamId']
            try:
                perms = {'items': [
                    {'teamId': int(team['id']), "permission": 1}
                ]}
            except Exception:
                print(team)
                continue
            self.g_client.folder.update_folder_permissions(project.id,
                                                           perms)
            keystone_members = self.k_client.role_assignments.list(
                project=project,
                role=CONF.keystone.member_role_id, include_names=True)
            members = self.g_client.teams.get_team_members(team['id'])
            id_name_lookup = {u['login']: u['userId'] for u in members}
            members = set([m['login'] for m in members])
            keystone_members = set([m.user['name'] for m in keystone_members])
            to_remove = list(members - keystone_members)
            to_add = list(keystone_members - members)
            for member in to_remove:
                self.g_client.teams.remove_team_member(team['id'],
                                                       id_name_lookup[member])
            for member in to_add:
                users = self.g_client.users.search_users(query=member)
                if users:
                    user = users[0]
                else:
                    continue
                self.g_client.teams.add_team_member(team['id'],
                                                    user['id'])
            id = None
            uid = None
            dashboard_search = self.g_client.search.search_dashboards(
                folder_ids=folder['id'], query="Running Instances")
            if dashboard_search:
                dashboard = dashboard_search[0]
                uid = dashboard['uid']
                id = dashboard['id']
            dashboard_template = dashboards.running_instances_dashboard(
                id=id,
                uid=uid,
                project=project)
            dashboard = {
                'dashboard': dashboard_template,
                'folderId': folder['id'],
                'overwite': True
            }
            try:
                self.g_client.dashboard.update_dashboard(dashboard)
            except Exception:
                pass
