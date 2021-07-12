import datetime
import logging

import placementclient

from nectar_tools.audit.metric import base
from nectar_tools import auth


LOG = logging.getLogger(__name__)


class FloatingIPAuditor(base.ResourceAuditor):

    def setup_clients(self):
        super().setup_clients()
        self.n_client = auth.get_placement_client(sess=self.ks_session)

