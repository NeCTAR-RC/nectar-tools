from datetime import datetime
from datetime import timedelta
from designateclient.client import Client as designateclient
import logging

from nectar_tools.audit import base
from nectar_tools import utils


LOG = logging.getLogger(__name__)

STATES = ['ERROR', 'PENDING', 'ACTIVE']

time_diff = timedelta(hours=12)


class DnsAuditor(base.Auditor):

    def __init__(self, ks_session):
        super(DnsAuditor, self).__init__(ks_session=ks_session)
        self.dc = designateclient('2', session=ks_session,
                                  all_projects=True)

    def check_zone_states(self):
        self.zones = []
        now = datetime.now()
        for state in STATES:
            self.zones += utils.list_resources(self.dc.zones.list, 'id',
                                               criterion={'status': state})
        for zone in self.zones:
            updated_at = datetime.strptime(zone['updated_at'],
                                           '%Y-%m-%dT%H:%M:%S.%f')
            if updated_at < now - time_diff:
                LOG.info("zone %s in state %s for more than %s",
                         zone['id'], zone['status'], time_diff)
