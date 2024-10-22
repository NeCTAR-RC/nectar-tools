from nectar_tools import config
from nectar_tools import notifier


CONF = config.CONFIG


class ProvisioningNotifier(notifier.FreshDeskNotifier):
    def __init__(self, project, noop=False):
        group_id = CONF.freshdesk.provisioning_group
        subject = f'Nectar Allocation Provisioned: {project.name}'
        template_dir = 'provisioning'
        super().__init__(
            'project', project, template_dir, group_id, subject, noop
        )

    def send_message(
        self, stage, allocation, extra_context={}, extra_recipients=[]
    ):
        if stage == 'new':
            tmpl = 'allocation-new.tmpl'
        elif stage == 'update':
            tmpl = 'allocation-update.tmpl'

        text = self.render_template(tmpl, extra_context)
        self._create_ticket(
            email=allocation.contact_email,
            cc_emails=extra_recipients,
            description=text,
            extra_context=extra_context,
            tags=['allocations', f'allocation-{allocation.id}'],
        )
