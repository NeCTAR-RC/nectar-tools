import logging

from nectar_tools.audit.rating import base
from nectar_tools import config


CONF = config.CONFIG
LOG = logging.getLogger(__name__)


class FlavorAuditor(base.RatingAuditor):

    def ensure_flavor_spec(self):
        FLAVOR_KEY = 'nectar:rate'

        flavors = self.n_client.flavors.list(is_public=None)
        mappings = self._get_mappings()
        mappings = {m.get('value'): m for m in mappings}

        for flavor in flavors:
            if flavor.name.startswith('reservation:'):
                LOG.debug(f"Skipping {flavor.name}")
                continue

            mapping = mappings.get(flavor.id)
            if mapping:
                cost = round(float(mapping.get('cost')), 3)
            else:
                cost = None
            try:
                flavor_rate = float(flavor.extra_specs.get(FLAVOR_KEY))
            except TypeError:
                flavor_rate = None

            if not cost and flavor_rate:
                LOG.warn(f"Flavor {flavor.name} has no cost")
                self.repair(f"Removing rate metadata for {flavor.name}",
                            flavor.unset_keys, keys=[FLAVOR_KEY])
                continue

            if flavor_rate != cost:
                LOG.warn(f"Flavor {flavor.name} cost out of sync. "
                         f"Current {flavor_rate}")
                self.repair(f"Setting flavor {flavor.name} metadata "
                            f"rate to {cost}",
                            flavor.set_keys, metadata={FLAVOR_KEY: cost})

    def ensure_cost(self):
        cpu_weight = 0.00494
        ram_weight = 0.0118

        prefix_weights = {
            'p3': 0.25,
            'm1': 1.2,
            'm2': 1.2,
            'r2': 2,
            'c2': 2,
        }

        flavors = self.n_client.flavors.list(is_public=None)
        mappings = self._get_mappings()
        mappings = {m.get('value'): m for m in mappings}

        group_id = self._get_group_id()
        field_id = self._get_field_id()

        for flavor in flavors:
            if flavor.name.startswith('reservation:'):
                LOG.debug(f"Skipping {flavor.name}")
                continue

            mapping = mappings.get(flavor.id)
            if mapping:
                cost = round(float(mapping.get('cost')), 3)
            else:
                cost = None

            disabled = flavor.extra_specs.get('nectar:rate:disabled')

            if disabled is not None:
                if cost:
                    mapping_id = mapping.get('mapping_id')
                    LOG.warning(f"{flavor.name} cost {cost} should be None")
                    self.repair(
                        f"Removing mapping for {flavor.name}",
                        self.c_client.rating.hashmap.delete_mapping,
                        mapping_id=mapping_id)
                LOG.debug(f"Skipping {flavor.name}, disabled")
                continue

            multiplier = float(flavor.extra_specs.get(
                'nectar:rate:multiplier', 1))
            addition = float(flavor.extra_specs.get(
                'nectar:rate:addition', 0))
            cpu_shares = flavor.extra_specs.get('quota:cpu_shares')
            if cpu_shares:
                cpu_shares_weight = int(cpu_shares) / (flavor.vcpus * 64)
            else:
                cpu_shares_weight = 1

            prefix_weight = prefix_weights.get(
                flavor.name.split('.')[0], 1)
            computed_cost = (
                ((flavor.vcpus * cpu_weight * cpu_shares_weight)
                 + (flavor.ram / 1024 * ram_weight)) * prefix_weight
                * multiplier) + addition
            computed_cost = round(computed_cost, 3)
            formula = (f"(({flavor.vcpus} * {cpu_weight} "
                       f"* {cpu_shares_weight}) + ({flavor.ram} / 1024 "
                       f"* {ram_weight})) * {prefix_weight}")
            formula_text = ("((flavor.vcpus * cpu_weight "
                            "* cpu_shares_weight) + (flavor.ram / 1024 "
                            "* ram_weight)) * prefix_weight")

            LOG.debug(formula_text)
            LOG.debug(formula)

            if cost != computed_cost:
                LOG.warning(
                    f"{flavor.name} cost {cost} should be {computed_cost}")
                self.repair(
                    f"Setting flavor {flavor.name} rate to {computed_cost}",
                    self.c_client.rating.hashmap.create_mapping,
                    field_id=field_id, group_id=group_id, type='flat',
                    value=flavor.id, cost=computed_cost)
