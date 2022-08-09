import logging

from nectar_tools.audit import base
from nectar_tools import auth
from nectar_tools import config


CONF = config.CONFIG
LOG = logging.getLogger(__name__)


class RatingAuditor(base.Auditor):

    def setup_clients(self):
        super().setup_clients()
        self.n_client = auth.get_nova_client(sess=self.ks_session)
        self.c_client = auth.get_cloudkitty_client(sess=self.ks_session)

    def _find_item(self, items, name, item_id):
        id = None
        for i in items:
            if i.get('name') == name:
                id = i.get(item_id)
                break
        return id

    def _get_group_id(self, name):
        groups = self.c_client.rating.hashmap.get_group()['groups']
        return self._find_item(groups, name, 'group_id')

    def _get_service_id(self, name):
        services = self.c_client.rating.hashmap.get_service()['services']
        return self._find_item(services, name, 'service_id')

    def _get_field_id(self, service, name):
        service_id = self._get_service_id(service)
        fields = self.c_client.rating.hashmap.get_field(
            service_id=service_id)['fields']
        return self._find_item(fields, name, 'field_id')

    def _get_mappings(self, group):
        group_id = self._get_group_id(group)
        mappings = self.c_client.rating.hashmap.get_group_mappings(
            group_id=group_id)['mappings']
        return mappings
