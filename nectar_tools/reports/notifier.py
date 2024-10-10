from nectar_tools import auth
from nectar_tools.common import service_units
from nectar_tools import config
from nectar_tools import notifier
from nectar_tools import utils


CONF = config.CONFIG


class AllocationNotifier(notifier.TaynacNotifier):
    def __init__(self, allocation, ks_session=None, noop=False):
        subject = f'Nectar Service Unit Report: {allocation.project_name}'
        template_dir = 'reports'
        self.ks_session = ks_session
        self.k_client = auth.get_keystone_client(ks_session)
        self.allocation = allocation
        super().__init__(
            ks_session, 'allocation', allocation, template_dir, subject, noop
        )

    def send_over_budget(self):
        su_info = service_units.SUinfo(self.ks_session, self.allocation)
        extra_context = {
            'su_used': f'{su_info.usage:.2f}',
            'su_budget': f'{su_info.budget:.2f}',
            'su_expected': f'{su_info.expected:.2f}',
        }
        email, cc_emails = utils.get_allocation_recipients(
            self.k_client, self.allocation
        )
        self.send_message(
            stage="over-budget",
            owner=email,
            extra_recipients=cc_emails,
            extra_context=extra_context,
            tags=['allocations', f'allocation-{self.allocation.id}'],
        )
