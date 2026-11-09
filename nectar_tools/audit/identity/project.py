import collections
import logging


from nectar_tools.audit.identity import base
from nectar_tools import auth
from nectar_tools import utils


LOG = logging.getLogger(__name__)


class ProjectAuditor(base.IdentityAuditor):
    def setup_clients(self):
        super().setup_clients()
        self.n_client = auth.get_nova_client(sess=self.ks_session)

    def check_deleted_no_instances(self):
        projects = utils.list_resources(self.k_client.projects.list)
        deleted = {
            project.id: project
            for project in projects
            if getattr(project, 'expiry_status', None) == 'deleted'
        }
        if not deleted:
            return
        # One paged listing of every live instance, not one nova call
        # per deleted project: there are tens of thousands of those and
        # the per-project loop outran the weekly job's deadline.
        servers = utils.list_resources(
            self.n_client.servers.list, search_opts={'all_tenants': True}
        )
        counts = collections.Counter(
            server.tenant_id
            for server in servers
            if server.tenant_id in deleted
        )
        for project_id, count in counts.items():
            LOG.error(
                "Deleted project %s has %s running instances",
                deleted[project_id].name,
                count,
            )
