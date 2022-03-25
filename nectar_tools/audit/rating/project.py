import datetime
import logging
import sys

from nectar_tools.audit.rating import base
from nectar_tools import config


CONF = config.CONFIG
LOG = logging.getLogger(__name__)


class ProjectAuditor(base.RatingAuditor):

    def check_instance_totals(self):
        project_id = self.extra_args.get('project_id')
        if not project_id:
            print("Must specify --project-id/-p")
            return sys.exit(1)

        opts = {'all_tenants': True,
                'tenant_id': project_id}

        flavors = self.n_client.flavors.list(is_public=None)
        mappings = self._get_mappings()

        mappings = {m.get('value'): m.get('cost', 0) for m in mappings}

        flavor_costs = {}
        for f in flavors:
            flavor_costs[f.name] = mappings.get(f.id, 0)
        instances = self.n_client.servers.list(search_opts=opts)
        flavors = []
        for instance in instances:
            if instance.status == 'SHELVED_OFFLOADED':
                continue
            flavors.append(instance.flavor.get('original_name'))

        nova_cost = 0
        for f in flavors:
            nova_cost += float(flavor_costs.get(f, 0))
        now = datetime.datetime.utcnow()

        begin = str(now - datetime.timedelta(hours=3))
        end = str(now)
        usage_data = self.c_client.summary.get_summary(
            begin=begin, end=end,
            filters={'type': 'instance', 'project_id': project_id},
            groupby=['time'], response_format='object').get('results')

        last_record = None
        for i in usage_data:
            if i.get('rate') is not None:
                last_record = i

        LOG.debug(f"Last Record {last_record}")
        nova_hours = len(flavors)
        cloudkitty_hours = last_record.get('qty')
        error = False
        LOG.info(f"Hours: nova={nova_hours}, cloudkitty={cloudkitty_hours}")
        if nova_hours != cloudkitty_hours:
            LOG.error("Mismatch hours!!!")
            error = True

        nova_cost = round(nova_cost, 2)
        cloudkitty_cost = round(last_record.get('rate'), 2)
        LOG.info(f"Rate: nova={nova_cost}, cloudkitty={cloudkitty_cost}")
        if nova_cost != cloudkitty_cost:
            LOG.error("Mismatch rate!!!")
            error = True

        if error:
            dataframes = self.c_client.dataframes.get_dataframes(
                begin=last_record['begin'], end=last_record['end'],
                filters={'type': 'instance', 'project_id': project_id})
            dataframes = dataframes.get(
                'dataframes')[0].get('usage').get('instance')
            df_instance_ids = set([x['groupby']['id'] for x in dataframes])
            nova_instance_ids = set([x.id for x in instances])
            instance_id_diff = df_instance_ids.symmetric_difference(
                nova_instance_ids)
            LOG.error(f"Instance IDs different = {instance_id_diff}")
