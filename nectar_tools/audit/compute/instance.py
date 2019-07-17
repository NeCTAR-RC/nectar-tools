from datetime import datetime
from datetime import timedelta
import logging

from nectar_tools.audit import base


LOG = logging.getLogger(__name__)

STATES = [
    'BUILD',
    'ERROR',
    'REVERT_RESIZE',
    'VERIFY_RESIZE',
    'HARD_REBOOT',
    'REBOOT',
    'REBUILD',
]

now = datetime.now()
time_diff = timedelta(days=7)


def chunks(l, n):
    """Yield successive n-sized chunks from l."""
    for i in range(0, len(l), n):
        yield l[i:i + n]


class InstanceAuditor(base.Auditor):

    def __init__(self, ks_session):
        super(InstanceAuditor, self).__init__(ks_session=ks_session)

    def check_instance_states(self):
        # NOTE: trying to get more than 4 states at once seems to
        # also return ACTIVE instances so work around it for now
        for states in chunks(STATES, 4):
            for instance in list(self.sdk_client.compute.servers(
                all_projects=True, status=states)):
                updated_at = datetime.strptime(instance.updated_at,
                                               '%Y-%m-%dT%H:%M:%SZ')
                if updated_at < now - time_diff:
                    LOG.info("instance %s in state %s for more than %s",
                             instance.id, instance.status, time_diff)
