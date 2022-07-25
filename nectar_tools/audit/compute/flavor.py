from datetime import datetime
from datetime import timedelta
import logging

from nectar_tools.audit import base
from nectar_tools import auth


LOG = logging.getLogger(__name__)

YEAR = 365
LAST_YEAR = (datetime.today() - timedelta(days=YEAR)).date()


class FlavorAuditor(base.Auditor):

    def setup_clients(self):
        super().setup_clients()
        self.n_client = auth.get_nova_client(sess=self.ks_session)
        self.g_client = auth.get_gnocchi_client(sess=self.ks_session)
        self.k_client = auth.get_keystone_client(sess=self.ks_session)

    def flavor_in_use(self):
        flavors = self.n_client.flavors.list(is_public=None)

        for flavor in flavors:
            if flavor.name.startswith('reservation:'):
                continue

            opts = {'all_tenants': True,
                    'flavor': flavor.id}

            servers = len(self.n_client.servers.list(
                search_opts=opts, limit=1))
            if not servers:
                instances = self.g_client.resource.search(
                    resource_type='instance',
                    query=f"flavor_name = '{flavor.name}'",
                    limit=1,
                    sorts=["ended_at:desc"],
                )
                if not instances:
                    LOG.error(f"Flavor {flavor.name} han't been used ever!")
                    continue
                try:
                    last_date = datetime.strptime(instances[0].get('ended_at'),
                                                  "%Y-%m-%dT%H:%M:%S.%f%z")
                except ValueError:
                    last_date = datetime.strptime(instances[0].get('ended_at'),
                                                  "%Y-%m-%dT%H:%M:%S%z")

                if last_date.date() < LAST_YEAR:
                    LOG.warning(
                        f"Flavor {flavor.name} last used {last_date}")

    def flavor_accessible(self):
        flavors = self.n_client.flavors.list(is_public=None)

        for flavor in flavors:
            if flavor.name.startswith('reservation:'):
                continue

            if not flavor.is_public:
                access = self.n_client.flavor_access.list(flavor=flavor.id)
                if not access:
                    LOG.warning(
                        f"Flavor {flavor.name} isn't accessable to anyone")
                    continue
                active = False
                for a in access:
                    project = self.k_client.projects.get(a.tenant_id)
                    if project.enabled and getattr(
                            project, 'expiry_status', 'active') != 'deleted':
                        active = True
                        break
                if not active:
                    LOG.warning(
                        f"Flavor {flavor.name} isn't accessable to any "
                        "active project")
