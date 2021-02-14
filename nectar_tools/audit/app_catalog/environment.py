from datetime import datetime
from datetime import timedelta
import logging

from nectar_tools.audit import base
from nectar_tools import auth


LOG = logging.getLogger(__name__)

DAYS = 7
TIME_DIFF = datetime.now() - timedelta(days=DAYS)


class EnvironmentAuditor(base.Auditor):

    def setup_clients(self):
        super().setup_clients()
        self.mc = auth.get_murano_client(sess=self.ks_session)
        self.k_client = auth.get_keystone_client(sess=self.ks_session)

    def check_environment_states(self):
        for env in self.mc.environments.list(all_tenants=True):
            packages = []
            if env.status != 'ready':
                updated_at = datetime.strptime(env.updated,
                                               '%Y-%m-%dT%H:%M:%S')
                if updated_at < TIME_DIFF:
                    try:
                        current_env = self.mc.environments.get(env.id)
                        if current_env.services:
                            for services in current_env.services:
                                for val in services.values():
                                    if type(val) == dict:
                                        t = val.get('type')
                                        if t and t.find('/') > 0:
                                            packages.append(t.split('/')[0])
                    except Exception as e:
                        LOG.warning('Failed to get package details'
                                    'in environment %s: %s', env.id, e)
                    # NOTE: apparently its valid for an environment
                    # to have no packages
                    if not packages:
                        packages = 'N/A'
                    LOG.info('environment %s in state %s for more '
                             'than %s days (packages: %s)\n',
                             env.id, env.status, DAYS, ','.join(packages))

    def check_environment_deleted_project(self):
        for env in self.mc.environments.list(all_tenants=True):
            project = self.k_client.projects.get(env.tenant_id)
            if not project.enabled or getattr(
                    project, 'expiry_status', 'active') == 'deleted':
                LOG.error("Environment %s belongs to a deleted project %s",
                          env.id, project.id)
                if self.repair:
                    try:
                        self.mc.environments.delete(env.id, abandon=True)
                        LOG.info("Removed environment %s", env.id)
                    except Exception:
                        pass
