import datetime
from dateutil.relativedelta import relativedelta
from nectar_tools.audit import base
from nectar_tools import auth

DATE_FORMAT = '%Y-%m-%d'


class ProjectAuditor(base.Auditor):

    def __init__(self, ks_session, project, repair=False, dry_run=True):
        super().__init__(ks_session, repair, dry_run)
        self.project = project
        self.now = datetime.datetime.now()

    def setup_clients(self):
        super().setup_clients()
        self.k_client = auth.get_keystone_client(sess=self.ks_session)

    def _past_next_step(self, date_string, days=3):
        # Return True when 'date_string' is at least 3 days in the past.
        # This allows for occasional expiry system glitches ...
        if not date_string:
            return False
        date = datetime.datetime.strptime(date_string, DATE_FORMAT)
        date_with_slack = date + relativedelta(days=days)
        return date_with_slack < self.now
