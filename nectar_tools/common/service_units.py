import datetime

from nectar_tools import auth


DATE_FORMAT = '%Y-%m-%d'


class SUinfo(object):

    def __init__(self, session, allocation):
        self.allocation = allocation
        self.session = session
        self._usage = None
        self._budget = None
        self.allocation_start = datetime.datetime.strptime(
            self.allocation.start_date, DATE_FORMAT)
        self.allocation_end = datetime.datetime.strptime(
            self.allocation.end_date, DATE_FORMAT)
        self.allocation_total_days = (self.allocation_end
                                      - self.allocation_start).days

    def over_budget(self):
        if self.budget == 0:
            return False
        return self.usage >= self.budget

    def over_80_percent(self):
        if self.budget == 0:
            return False

        if self.usage >= (self.budget * 0.8):
            return True

    @property
    def usage(self):
        if self._usage is None:
            self._usage = 0
            client = auth.get_cloudkitty_client(self.session)
            summary = client.summary.get_summary(
                begin=str(self.allocation.start_date),
                end=str(self.allocation.end_date),
                filters={'type': 'instance',
                         'project_id': self.allocation.project_id},
                response_format='object')

            results = summary.get('results')
            if results:
                self._usage = results[0].get('rate')
        return self._usage

    @property
    def budget(self):
        if self._budget is None:
            b = self.allocation.get_allocated_cloudkitty_quota().get('budget')
            if not b:
                b = 0
            self._budget = b
        return self._budget

    @property
    def daily_average_budget(self):
        return self.budget / self.allocation_total_days

    @property
    def expected(self):
        today = datetime.datetime.today()
        days_used = (today - self.allocation_start).days
        return self.daily_average_budget * days_used

    def is_tracking_over(self):
        if self.budget == 0:
            return False

        today = datetime.datetime.today()
        if today < self.allocation_start:
            return False
        days_used = (today - self.allocation_start).days
        return (self.usage / self.budget
                > days_used / self.allocation_total_days)
