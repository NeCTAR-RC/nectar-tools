from .. import update_expiry

import datetime
from freezegun import freeze_time
import mock
import unittest


update_expiry.DRY_RUN = True

USAGE_LIMIT_HOURS = update_expiry.USAGE_LIMIT_HOURS


class UpdateExpiryTestCase(unittest.TestCase):
    def setUp(self):
        super(UpdateExpiryTestCase, self).setUp()

        class User(object):
            name = 'user@thecloud.com'
            tenantId = 1

        class Tenant(object):
            name = 'pt-1'
            id = 1

        class Usage(object):
            total_vcpus_usage = 12

        self.tenant = Tenant()
        self.user = User()
        self.users = [self.user.name]
        self.usage = Usage()

        self.kc = mock.Mock()
        self.kc.users.get.return_value = self.user
        self.kc.tenants.get.return_value = self.tenant
        self.nc = mock.Mock()
        self.nc.usage.get.return_value = self.usage

        self.now = datetime.datetime(2014, 1, 1, 0, 0)

    def call_update(self):
        with freeze_time(self.now):
            update_expiry.update(self.kc, self.nc, self.users)

        self.kc.users.get.assert_called_with(self.user.name)
        self.kc.tenants.get.assert_called_with(self.tenant.id)
        self.nc.usage.get.assert_called_with(
            self.user.tenantId,
            datetime.datetime(2011, 1, 1, 0, 0),
            self.now + datetime.timedelta(days=1))

    def test_non_personal_tenant_is_ignored(self):
        self.tenant.name = 'MeritAllocation'

        with freeze_time(self.now):
            update_expiry.update(self.kc, self.nc, self.users)

        self.kc.users.get.assert_called_with(self.user.name)
        self.kc.tenants.get.assert_called_with(self.tenant.id)
        assert not self.nc.usage.get.called

    @mock.patch('scripts.update_expiry.set_status')
    def test_set_unset_status(self, set_status):
        self.call_update()
        set_status.assert_called_with(self.kc, self.user.tenantId, None)

    @mock.patch('scripts.update_expiry.set_status')
    def test_tenant_already_suspended(self, set_status):
        self.tenant.status = 'suspended'
        self.call_update()
        assert not set_status.called

    @mock.patch('scripts.update_expiry.set_status')
    def test_tenant_status_is_admin(self, set_status):
        self.tenant.status = 'admin'
        self.call_update()
        assert not set_status.called

    @mock.patch('scripts.update_expiry.suspend_tenant')
    @mock.patch('scripts.update_expiry.set_status')
    def test_tenant_not_expired(self, set_status, suspend_tenant):
        self.tenant.status = 'first'
        self.tenant.expires = '2014-05-01'
        self.call_update()
        assert not set_status.called
        assert not suspend_tenant.called

    @mock.patch('scripts.update_expiry.suspend_tenant')
    @mock.patch('scripts.update_expiry.set_status')
    def test_tenant_expired(self, set_status, suspend_tenant):
        self.tenant.status = 'first'
        self.tenant.expires = '2013-12-31'
        self.call_update()
        assert not set_status.called
        suspend_tenant.assert_called_with(self.kc, self.nc,
                                          self.user, self.tenant)

    @mock.patch('scripts.update_expiry.notify_120')
    @mock.patch('scripts.update_expiry.notify_100')
    @mock.patch('scripts.update_expiry.notify_80')
    @mock.patch('scripts.update_expiry.set_status')
    def test_under_80_percent(self, set_status, notify_80, notify_100,
                              notify_120):
        self.usage.total_vcpus_usage = USAGE_LIMIT_HOURS * 0.8 - 1
        self.tenant.status = None
        self.tenant.expires = '2014-05-01'
        self.call_update()
        assert not set_status.called
        assert not notify_80.called
        assert not notify_100.called
        assert not notify_120.called

    @mock.patch('scripts.update_expiry.notify_120')
    @mock.patch('scripts.update_expiry.notify_100')
    @mock.patch('scripts.update_expiry.notify_80')
    @mock.patch('scripts.update_expiry.set_status')
    def test_under_100_percent(self, set_status, notify_80, notify_100,
                               notify_120):
        self.usage.total_vcpus_usage = USAGE_LIMIT_HOURS * 1.0 - 1
        self.tenant.status = None
        self.tenant.expires = '2014-05-01'
        self.call_update()
        assert not set_status.called
        notify_80.assert_called_with(self.kc, self.user, self.tenant)
        assert not notify_100.called
        assert not notify_120.called

    @mock.patch('scripts.update_expiry.notify_120')
    @mock.patch('scripts.update_expiry.notify_100')
    @mock.patch('scripts.update_expiry.notify_80')
    @mock.patch('scripts.update_expiry.set_status')
    def test_under_120_percent(self, set_status, notify_80, notify_100,
                               notify_120):
        self.usage.total_vcpus_usage = USAGE_LIMIT_HOURS * 1.2 - 1
        self.tenant.status = None
        self.tenant.expires = '2014-05-01'
        self.call_update()
        assert not set_status.called
        assert not notify_80.called
        notify_100.assert_called_with(self.kc, self.nc, self.user, self.tenant)
        assert not notify_120.called

    @mock.patch('scripts.update_expiry.notify_120')
    @mock.patch('scripts.update_expiry.notify_100')
    @mock.patch('scripts.update_expiry.notify_80')
    @mock.patch('scripts.update_expiry.set_status')
    def test_over_120_percent(self, set_status, notify_80, notify_100,
                              notify_120):
        self.usage.total_vcpus_usage = USAGE_LIMIT_HOURS * 1.2
        self.tenant.status = None
        self.tenant.expires = '2014-05-01'
        self.call_update()
        assert not set_status.called
        assert not notify_80.called
        assert not notify_100.called
        notify_120.assert_called_with(self.kc, self.nc, self.user, self.tenant)

    @mock.patch('scripts.update_expiry.lock_instance')
    @mock.patch('scripts.update_expiry.suspend_instance')
    @mock.patch('scripts.update_expiry.set_status')
    @mock.patch('scripts.update_expiry.set_nova_quota')
    @mock.patch('scripts.update_expiry.get_instances')
    def test_suspend_tenant(self, get_instances, set_nova_quota, set_status,
                            suspend_instance, lock_instance):
        instances = ['1', '2']
        get_instances.return_value = instances

        update_expiry.suspend_tenant(self.kc, self.nc, self.user, self.tenant)

        set_status.assert_called_with(self.kc, self.tenant.id, 'suspended')
        set_nova_quota.assert_called_with(self.nc, self.tenant.id,
                                          ram=0, instances=0, cores=0)
        get_instances.assert_called_with(self.nc, self.tenant.id)
        calls = [mock.call(instance) for instance in instances]
        suspend_instance.assert_has_calls(calls)
        lock_instance.assert_has_calls(calls)
