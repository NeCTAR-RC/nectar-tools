from datetime import datetime, timedelta
import logging

import keystoneauth1

from nectar_tools.audit import base


LOG = logging.getLogger(__name__)

STATES = [
    'ERROR',
    'BUILD',
    'UNKNOWN',
    'VERIFY_RESIZE',
    'REVERT_RESIZE',
    'SUSPENDED',
    'SHUTOFF',
#    'REBUILD',
#    'HARD_REBOOT',
#    'MIGRATING',
#    'REBOOT',
    ]

time_diff = timedelta(days=1)


class InstanceAuditor(base.Auditor):

    def __init__(self, ks_session):
        super(InstanceAuditor, self).__init__(ks_session=ks_session)
        self.instances = self.sdk_client.compute.servers(status=STATES)

    def check_instance_states(self):
        for instance in self.instances:
            updated_at = datetime.strptime(instance.updated_at,
                                           '%Y-%m-%dT%H:%M:%SZ')
            now = datetime.now()
            if updated_at < now - time_diff:
                LOG.info("instance %s in state %s for more than %s",
                         instance.id, instance.status, time_diff)
