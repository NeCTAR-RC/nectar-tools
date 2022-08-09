from decimal import Decimal
import logging

from nectar_tools.audit.rating import base
from nectar_tools import auth
from nectar_tools import config


CONF = config.CONFIG
LOG = logging.getLogger(__name__)


class ReservationFlavorAuditor(base.RatingAuditor):

    def setup_clients(self):
        super().setup_clients()
        self.w_client = auth.get_warre_client(sess=self.ks_session)

    def ensure_cost(self):
        RATE_KEY = 'nectar:rate'

        flavors = self.w_client.flavors.list(all_projects=True)
        mappings = self._get_mappings(group='reservation_flavor_id')
        mappings = {m.get('value'): m for m in mappings}
        field_id = self._get_field_id(service='reservation', name='flavor_id')
        group_id = self._get_group_id(name='reservation_flavor_id')

        for flavor in flavors:
            if not flavor.category:
                LOG.debug(f"Skipping {flavor.name}")
                continue

            mapping_id = None
            mapping = mappings.get(flavor.id)
            if mapping:
                cost = Decimal(mapping.get('cost'))
                mapping_id = mapping.get('mapping_id')
            else:
                cost = None

            cost_spec = flavor.extra_specs.get(RATE_KEY)
            if not cost_spec:
                LOG.error(f"No nectar:rate set for {flavor.name}")
                continue
            else:
                computed_cost = round(Decimal(cost_spec), 3)
                computed_cost = Decimal(computed_cost)

            if cost != computed_cost:
                LOG.warning(
                    f"{flavor.name} cost {cost} should be {computed_cost}")
                if mapping_id:
                    self.repair(
                        f"Updating flavor {flavor.name} "
                        f"rate to {computed_cost}",
                        self.c_client.rating.hashmap.update_mapping,
                        mapping_id=mapping_id, cost=str(computed_cost))
                else:
                    self.repair(
                        f"Setting flavor {flavor.name} "
                        f"rate to {computed_cost}",
                        self.c_client.rating.hashmap.create_mapping,
                        field_id=field_id, group_id=group_id, type='flat',
                        value=flavor.id, cost=str(computed_cost))
