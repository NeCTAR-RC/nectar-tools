from dateutil.relativedelta import relativedelta
import logging

from nectar_tools import auth
from nectar_tools import config

from nectar_tools.expiry import expirer as base
from nectar_tools.expiry import expiry_states
from nectar_tools.expiry import notifier as expiry_notifier


CONF = config.CONFIG
LOG = logging.getLogger(__name__)


class AccountExpirer(base.Expirer):

    EVENT_PREFIX = 'expiry.account'

    def __init__(self, account, ks_session=None, dry_run=False):
        notifier = expiry_notifier.ExpiryNotifier(
            resource_type='account', resource=account, template_dir='accounts',
            group_id=CONF.freshdesk.accounts_group,
            subject="Deactivation of your Nectar Research Cloud Account",
            ks_session=ks_session, dry_run=dry_run)
        self.account = account
        self.m_client = auth.get_manuka_client(ks_session)
        super().__init__('account', account, notifier, ks_session, dry_run)

    def ready_for_warning(self):
        # TODO(sorrison) - Also warn when new terms not accepted
        six_months_ago = self.now - relativedelta(months=6)
        if self.account.last_login < six_months_ago:
            return True
        LOG.debug("%s: Account has had recent login, skipping",
                  self.account.id)
        return False

    def _update_resource(self, **kwargs):
        if self.dry_run:
            msg = '%s: Would update %s' % (self.account.id, kwargs)
        else:
            msg = '%s: Updated %s' % (self.account.id, kwargs)
            self.m_client.users.update(self.account.id, **kwargs)
        LOG.info(msg)

    def deactivate_account(self):
        if self.dry_run:
            LOG.info("%s: Would disable user", self.account.id)
        else:
            self.k_client.users.update(self.account.id, enabled=False,
                                       inactive=True)
            LOG.info("%s: Disabled user", self.account.id)

        self._update_resource(expiry_status='inactive',
                              expiry_next_step=None)
        self.send_event('disabled')

    def _get_recipients(self):
        return self.account.email, []

    def _get_notification_context(self):
        return {'account': self.account.to_dict()}

    def process(self):
        status = self.get_status()

        if status == 'inactive':
            return False

        elif status == expiry_states.WARNING:
            if self.at_next_step():
                self.deactivate_account()
                return True

        elif self.ready_for_warning():
            self.send_warning()
            return True
