from datetime import datetime
from datetime import timedelta
from designateclient.v2.client import Client as dns_client
import logging

from nectar_tools.audit import base


LOG = logging.getLogger(__name__)

STATES = ['ERROR', 'PENDING']

time_diff = timedelta(minutes=5)


class DnsAuditor(base.Auditor):

    def __init__(self, ks_session):
        super(DnsAuditor, self).__init__(ks_session=ks_session)
        self.dc = dns_client(session=ks_session, all_projects=True)
        self.zones = self.dc.zones.list()
        while (True):
            z = self.dc.zones.list(marker=self.zones[-1].get('id'))
            if len(z) == 0:
                break
            self.zones += z
            

    def check_zone_states(self):
        for zone in self.zones:
            if zone['status'] in STATES:
                updated_at = datetime.strptime(zone['updated_at'],
                                               '%Y-%m-%dT%H:%M:%S.%f')
                now = datetime.now()
                if updated_at < now - time_diff:
                    LOG.info("zone %s in state %s for more than %s",
                             zone['id'], zone['status'], time_diff)
