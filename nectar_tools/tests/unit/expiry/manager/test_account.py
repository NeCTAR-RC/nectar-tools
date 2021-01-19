import datetime
from freezegun import freeze_time
from unittest import mock

from nectar_tools import config
from nectar_tools import test

from nectar_tools.expiry import expirer as expierer_base
from nectar_tools.expiry.manager import account as expirer


CONF = config.CONFIG
YESTERDAY = '2016-12-31'


@freeze_time("2017-01-01")
@mock.patch('nectar_tools.expiry.notifier.ExpiryNotifier',
            new=mock.Mock())
@mock.patch('nectar_tools.auth.get_session', new=mock.Mock())
class AccountExpiryTests(test.TestCase):

    def setUp(self):
        super().setUp()

        last_login = datetime.datetime.strptime(
            YESTERDAY, expierer_base.DATE_FORMAT)
        account = mock.Mock(id='fake', last_login=last_login)
        self.account = account

    def test_ready_for_warning_negative(self):
        ex = expirer.AccountExpirer(self.account)
        self.assertFalse(ex.ready_for_warning())

    def test_ready_for_warning(self):
        self.account.last_login = datetime.datetime(2012, 1, 1)
        ex = expirer.AccountExpirer(self.account)
        self.assertTrue(ex.ready_for_warning())

    @mock.patch('nectar_tools.auth.get_manuka_client')
    def test_update_resource(self, mock_get_manuka):
        client = mock_get_manuka.return_value
        ex = expirer.AccountExpirer(self.account)

        ex._update_resource(foo='bar')
        client.users.update.assert_called_once_with(ex.account.id, foo='bar')

    @mock.patch('nectar_tools.auth.get_keystone_client')
    def test_deactivate_account(self, mock_get_keystone):
        keystone = mock_get_keystone.return_value
        ex = expirer.AccountExpirer(self.account)
        with mock.patch.object(ex, '_update_resource') as update:
            ex.deactivate_account()
            update.assert_called_once_with(expiry_status='inactive',
                                           expiry_next_step=None)
        keystone.users.update.assert_called_once_with(
            ex.account.id, enabled=False, inactive=True)
