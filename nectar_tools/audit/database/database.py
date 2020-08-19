import logging

import troveclient

from nectar_tools.audit import base
from nectar_tools import auth
from nectar_tools import config


CONF = config.CONFIG
LOG = logging.getLogger(__name__)


class DatabaseAuditor(base.Auditor):

    def setup_clients(self):
        super().setup_clients()
        self.t_client = auth.get_trove_client(sess=self.ks_session)
        self.n_client = auth.get_nova_client(sess=self.ks_session)
        self.k_client = auth.get_keystone_client(sess=self.ks_session)

    def check_status(self):
        # Can't list all trove DBs via trove api so list all instances and work
        # that way
        instance_list = self.n_client.servers.list(
            search_opts={"all_tenants": True,
                         'tenant_id': CONF.trove.project_id})

        for i in instance_list:
            project_id = i.metadata.get('project_id')
            project = self.k_client.projects.get(project_id)
            if i.status != 'ACTIVE':
                LOG.warning("Nova Instance %s status %s", i.id, i.status)
            trove_id = i.metadata.get('trove_id')
            if not trove_id:
                LOG.error("No trove ID metadata for instance %s", i.id)
                continue

            try:
                trove_db = self.t_client.instances.get(trove_id)
            except troveclient.apiclient.exceptions.NotFound:
                LOG.error("Can't find trove DB %s for instance %s", trove_id,
                          i.id)

            if project.name == 'tempest-operator':
                if self.repair:
                    LOG.info('deleting tempest DB %s', trove_id)
                    trove_db.delete()
                else:
                    LOG.warn("%s owned by tempest-operator", trove_id)
                continue
            if not project.enabled:
                if self.repair:
                    LOG.info('deleting DB from disabled project %s', trove_id)
                    trove_db.delete()
                else:
                    LOG.warn("%s owned by disabled project", trove_id)
                continue

            if trove_db.status != 'ACTIVE':
                LOG.warning("Trove %s status %s", trove_db.id, trove_db.status)

            try:
                dbs = self.t_client.databases.list(trove_db)
                if dbs and dbs[0].name.startswith('tempest'):
                    if self.repair:
                        LOG.info('deleting tempest DB %s', trove_id)
                        trove_db.delete()
                    else:
                        LOG.warn("%s owned by tempest project", trove_id)
            except Exception as e:
                LOG.error("Can't communicate with Trove DB %s", trove_id)
                LOG.exception(e)
