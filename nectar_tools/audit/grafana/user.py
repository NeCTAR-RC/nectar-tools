import logging

from nectar_tools.audit.grafana import base


LOG = logging.getLogger(__name__)


class UserAuditor(base.GrafanaAuditor):

    def __init__(self, ks_session):
        super(UserAuditor, self).__init__(ks_session=ks_session)
        self.users = None

    def _get_users(self):
        if self.users is None:
            self.users = self.k_client.users.list(domain='default',
                                                  enabled=True)
        return self.users

    def ensure_user_for_user(self):
        for k_user in self._get_users():
            user = None
            users = self.g_client.users.search_users(query=k_user.name)
            if users:
                user = users[0]
            if not user:
                try:
                    user = self.g_client.users.create_user(login=k_user.name,
                                                           password='none')
                except Exception:
                    pass
