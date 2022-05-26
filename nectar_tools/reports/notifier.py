from nectar_tools import auth
from nectar_tools.common import service_units
from nectar_tools import config
from nectar_tools import notifier
from nectar_tools import utils


CONF = config.CONFIG


class AllocationNotifier(notifier.FreshDeskNotifier):

    def __init__(self, allocation, ks_session=None, noop=False):
        group_id = CONF.freshdesk.service_units_group
        subject = f'Nectar Service Unit Report: {allocation.project_name}'
        template_dir = 'reports'
        self.ks_session = ks_session
        self.k_client = auth.get_keystone_client(ks_session)
        self.allocation = allocation
        super().__init__(
            'allocation', allocation, template_dir, group_id, subject, noop)

    def send_over_budget(self):
        su_info = service_units.SUinfo(self.ks_session, self.allocation)
        extra_context = {
            'su_used': f'{su_info.usage:.2f}',
            'su_budget': f'{su_info.budget:.2f}',
            'su_expected': f'{su_info.expected:.2f}',
        }
        text = self.render_template("over-budget.tmpl", extra_context)
        self.send_message(text, extra_context)

    def send_message(self, text, extra_context):
        email, cc_emails = utils.get_allocation_recipients(
            self.k_client, self.allocation)

        self._create_ticket(email=email,
                            cc_emails=cc_emails,
                            description=text,
                            extra_context=extra_context,
                            tags=['allocations',
                                  f'allocation-{self.allocation.id}'])
