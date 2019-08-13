from nectar_tools import config
from nectar_tools import notifier


CONF = config.CONFIG


class ProvisioningNotifier(notifier.FreshDeskNotifier):

    def __init__(self, project, noop=False):
        group_id = CONF.freshdesk.provisioning_group
        subject = 'Nectar Allocation Provisioned: {}'.format(project.name)
        template_dir = 'provisioning'
        super(ProvisioningNotifier, self).__init__(
            'project', project, template_dir, group_id, subject, noop)

    def send_message(self, stage, owner, extra_context={},
                     extra_recipients=[]):
        if stage == 'new':
            tmpl = 'allocation-new.tmpl'
        elif stage == 'update':
            tmpl = 'allocation-update.tmpl'

        text = self.render_template(tmpl, extra_context)

        self._create_ticket(email=owner,
                            cc_emails=extra_recipients,
                            description=text,
                            extra_context=extra_context,
                            tags=['allocations'])
