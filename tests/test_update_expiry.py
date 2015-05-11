from nectar_tools.update_expiry import main as update_expiry

import datetime
from freezegun import freeze_time
import mock
import pytest


update_expiry.DRY_RUN = True

USAGE_LIMIT_HOURS = update_expiry.USAGE_LIMIT_HOURS
CPULimit = update_expiry.CPULimit


pytest_mock_fixtures = [
    'nectar_tools.update_expiry.main.send_email',
    'nectar_tools.update_expiry.main.set_status',
    'nectar_tools.update_expiry.main.set_nova_quota',
    'nectar_tools.update_expiry.main.check_cpu_usage',
    'nectar_tools.update_expiry.main.suspend_tenant',
    'nectar_tools.update_expiry.main.notify_at_limit',
    'nectar_tools.update_expiry.main.lock_instance',
    'nectar_tools.update_expiry.main.suspend_instance',
    'nectar_tools.update_expiry.main.get_instances',
    'nectar_tools.update_expiry.main.do_email_send',
]


@pytest.fixture()
def user():
    class User(object):
        username = 'user@thecloud.com'
        tenantId = 1
        email = 'user@thecloud.com'
        enabled = True
    return User()


@pytest.fixture()
def tenant(user):
    class Tenant(object):
        name = 'pt-1'
        id = 1
        status = ''
        expires = ''
        owner = user
    return Tenant()


@pytest.fixture()
def tenants(tenant):
    return [tenant]


@pytest.fixture()
def usage():
    class Usage(object):
        total_vcpus_usage = None
    return Usage()


@pytest.fixture()
def nova(usage):
    nc = mock.Mock()
    nc.usage.get.return_value = usage
    return nc


@pytest.fixture()
def keystone():
    return None


@pytest.fixture()
def now():
    return datetime.datetime(2014, 1, 1, 0, 0)


def test_admin_tenant_is_ignored(tenant):
    tenant.status = 'admin'
    should = update_expiry.should_process_tenant(tenant)
    assert not should


def test_non_personal_tenant_is_ignored(tenant):
    tenant.name = 'MeritAllocation'
    should = update_expiry.should_process_tenant(tenant)
    assert not should


def test_tenant_at_next_step_date(tenant, now):
    tenant.expires = '2013-12-31'
    with freeze_time(now):
        expired = update_expiry.tenant_at_next_step_date(tenant)
    assert expired


def test_tenant_is_not_expired(tenant, now):
    tenant.expires = '2014-01-02'
    with freeze_time(now):
        expired = update_expiry.tenant_at_next_step_date(tenant)
    assert not expired


def test_check_cpu_usage_gets_nova_usage(tenant, keystone, nova, now):
    with freeze_time(now):
        update_expiry.check_cpu_usage(keystone, nova, tenant)
    nova.usage.get.assert_called_with(
        tenant.id,
        datetime.datetime(2011, 1, 1, 0, 0),
        now + datetime.timedelta(days=1))


@pytest.mark.parametrize("percentage, expected_limit", [
    (0.8, CPULimit.UNDER_LIMIT),
    (1.0, CPULimit.NEAR_LIMIT),
    (1.2, CPULimit.AT_LIMIT),
    (1.201, CPULimit.OVER_LIMIT),
])
def test_check_cpu_usage(percentage, expected_limit,
                         tenant, keystone, nova, usage):
    usage.total_vcpus_usage = USAGE_LIMIT_HOURS * percentage - 1
    limit = update_expiry.check_cpu_usage(keystone, nova, tenant)
    assert limit == expected_limit


@pytest.mark.parametrize("limit, notification", [
    (CPULimit.UNDER_LIMIT, None),
    (CPULimit.NEAR_LIMIT, 'first'),
    (CPULimit.AT_LIMIT, 'second'),
])
def test_notify_sends_email(limit, notification,
                            tenant, keystone, nova, send_email):
    update_expiry.notify(keystone, nova, tenant, limit)
    if notification is None:
        assert not send_email.called
    else:
        send_email.assert_called_with(tenant, notification)


def test_over_limit_calls_notify_at_limit(tenant, keystone, nova,
                                          notify_at_limit):
    tenant.status = 'not pending suspension'
    update_expiry.notify(keystone, nova, tenant,
                         CPULimit.OVER_LIMIT)
    assert notify_at_limit.called


def test_first_warning_for_near_limit(tenant, keystone, nova, now,
                                      suspend_tenant, check_cpu_usage,
                                      set_status, send_email):
    check_cpu_usage.return_value = CPULimit.NEAR_LIMIT
    with freeze_time(now):
        update_expiry.process_tenant(keystone, nova, tenant)
    set_status.assert_called_with(keystone, tenant,
                                  'quota warning')
    send_email.assert_called_with(tenant, 'first')
    assert not suspend_tenant.called


def test_second_warning_for_over_limit(tenant, keystone, nova, now,
                                       suspend_tenant, check_cpu_usage,
                                       set_status, set_nova_quota):
    tenant.status = 'quota warning'
    check_cpu_usage.return_value = CPULimit.OVER_LIMIT
    with freeze_time(now):
        update_expiry.process_tenant(keystone, nova, tenant)
    expires = '2014-02-01'
    set_status.assert_called_with(keystone, tenant,
                                  'pending suspension', expires)
    set_nova_quota.assert_called_with(nova, tenant.id,
                                      ram=0, instances=0, cores=0)
    assert not suspend_tenant.called


def test_over_limit_but_not_expired(tenant, keystone, nova, now,
                                    suspend_tenant, check_cpu_usage,
                                    set_status):
    tenant.status = 'pending suspension'
    tenant.expires = '2014-06-01'
    check_cpu_usage.return_value = CPULimit.OVER_LIMIT
    with freeze_time(now):
        update_expiry.process_tenant(keystone, nova, tenant)
    # Do nothing.
    assert not suspend_tenant.called
    assert not set_status.called


def test_suspend_expired_and_pending_suspension_tenant(tenant,
                                                       keystone,
                                                       nova,
                                                       now,
                                                       suspend_tenant,
                                                       check_cpu_usage):
    tenant.status = 'pending suspension'
    tenant.expires = '2013-12-31'
    check_cpu_usage.return_value = CPULimit.OVER_LIMIT
    with freeze_time(now):
        update_expiry.process_tenant(keystone, nova, tenant)
    suspend_tenant.assert_called_with(keystone, nova, tenant)


def test_suspend_tenant(nova, keystone, tenant, now,
                        get_instances, set_nova_quota, set_status,
                        suspend_instance, lock_instance, send_email):
    new_expires = '2014-02-01'  # 1 month from 'now'
    instances = ['1', '2']
    get_instances.return_value = instances

    with freeze_time(now):
        update_expiry.suspend_tenant(keystone, nova, tenant)

    set_nova_quota.assert_called_with(nova, tenant.id,
                                      ram=0, instances=0, cores=0)
    get_instances.assert_called_with(nova, tenant.id)
    calls = [mock.call(instance) for instance in instances]
    suspend_instance.assert_has_calls(calls)
    lock_instance.assert_has_calls(calls)
    set_status.assert_called_with(keystone, tenant, 'suspended',
                                  new_expires)
    send_email.assert_called_with(tenant, 'final')


@pytest.mark.parametrize("status", ['first', 'second', 'final'])
def test_render_template(tenant, status, do_email_send):
    tenant.expires = '2014-01-01'
    update_expiry.send_email(tenant, status)

    assert do_email_send.called
    args = do_email_send.call_args[0]
    subject, body, to = args
    assert to == tenant.owner.email
    assert tenant.name in subject
    assert tenant.name in body
    if status == 'second':
        assert tenant.expires in body


def test_disabled_user_doesnt_get_emailed(tenant, do_email_send):
    tenant.owner.enabled = False
    update_expiry.send_email(tenant, 'first')
    assert not do_email_send.called


def test_set_status(keystone, tenant):
    status = 'suspended'
    expires = '2014-01-01'
    update_expiry.set_status(keystone, tenant,
                             status=status, expires=expires)
    assert tenant.status == status
    assert tenant.expires == expires
