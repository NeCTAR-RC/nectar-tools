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

DAYS = 7
TIME_DIFF = datetime.now() - timedelta(days=DAYS)


def chunks(seq, n):
    """Yield successive n-sized chunks from seq."""
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


class InstanceAuditor(base.Auditor):

    def check_instance_states(self):
        # NOTE: trying to get more than 4 states at once seems to
        # also return ACTIVE instances so work around it for now
        for states in chunks(STATES, 4):
            for instance in self.sdk_client.compute.servers(
                all_projects=True, status=states):
                updated_at = datetime.strptime(instance.updated_at,
                                               '%Y-%m-%dT%H:%M:%SZ')
                if updated_at < TIME_DIFF:
                    LOG.info("instance %s in state %s for more than %s days",
                             instance.id, instance.status, DAYS)
