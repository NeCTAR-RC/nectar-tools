from nectar_tools import config
from nectar_tools import notifier


CONF = config.CONFIG


class ProvisioningNotifier(notifier.TaynacNotifier):
    def __init__(self, project, ks_session, noop=False):
        subject = f'Nectar Allocation Provisioned: {project.name}'
        template_dir = 'provisioning'
        super().__init__(
            ks_session, 'project', project, template_dir, subject, noop
        )

    def send_provisioning(
        self, stage, allocation, extra_context={}, extra_recipients=[]
    ):
        if stage == 'new':
            tmpl = 'allocation-new'
        elif stage == 'update':
            tmpl = 'allocation-update'
        self.send_message(
            stage=tmpl,
            owner=allocation.contact_email,
            extra_recipients=extra_recipients,
            extra_context=extra_context,
            tags=['allocations', f'allocation-{allocation.id}'],
        )
