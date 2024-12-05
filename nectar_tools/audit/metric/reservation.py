import logging


from nectar_tools.audit.metric import base


LOG = logging.getLogger(__name__)


class ReservationAuditor(base.ResourceAuditor):
    def ensure_az_cat(self):
        flavors = self.g_client.resource.search(
            resource_type='reservation-flavor',
        )

        flavor_map = {
            flavor['id']: {
                'availability_zone': flavor['availability_zone'],
                'category': flavor['category'],
            }
            for flavor in flavors
        }

        reservations = self.g_client.resource.search(
            resource_type='reservation', query='category=null'
        )

        for reservation in reservations:
            flavor_data = flavor_map.get(reservation['flavor_id'])
            if not flavor_data:
                LOG.warning(
                    "No Flavor found for ID %s", reservation['flavor_id']
                )
                continue
            if flavor_data['category'] is None:
                LOG.warning(
                    "Flavor has no category for ID %s",
                    reservation['flavor_id'],
                )
                continue
            if flavor_data['availability_zone'] is None:
                LOG.warning(
                    "Flavor has no availability_zone for ID %s",
                    reservation['flavor_id'],
                )
                continue

            self.repair(
                f"Updating reservation {reservation['id']} with {flavor_data}",
                self.g_client.resource.update,
                resource_type='reservation',
                resource_id=reservation['id'],
                resource=flavor_data,
            )
