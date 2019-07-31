from datetime import datetime
from datetime import timedelta
import logging

from nectar_tools.audit import base
from nectar_tools import auth
from nectar_tools import utils


LOG = logging.getLogger(__name__)

STATES = ['ERROR', 'PENDING']


class DnsAuditor(base.Auditor):

    def __init__(self, ks_session):
        super(DnsAuditor, self).__init__(ks_session=ks_session)
        self.dc = auth.get_designate_client(sess=ks_session,
                                            all_projects=True)

    def check_zone_states(self):
        time_diff = datetime.now() - timedelta(hours=12)
        for state in STATES:
            for zone in utils.list_resources(self.dc.zones.list,
                                             criterion={'status': state}):
                updated_at = datetime.strptime(zone['updated_at'],
                                               '%Y-%m-%dT%H:%M:%S.%f')
                if updated_at < time_diff:
                    LOG.info("zone %s in state %s for more than 12 hours",
                             zone['id'], zone['status'])
