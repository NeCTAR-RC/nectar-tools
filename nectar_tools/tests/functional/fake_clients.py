from unittest import mock

from openstack.load_balancer.v2 import quota as lb_quota


FAKE_DESIGNATE = mock.MagicMock()
FAKE_WARRE = mock.MagicMock()
FAKE_KEYSTONE = mock.MagicMock()
FAKE_OPENSTACKSDK = mock.MagicMock()
FAKE_FD_API = mock.MagicMock()
FAKE_FD_API_CLASS = mock.MagicMock(return_value=FAKE_FD_API)
FAKE_GET_SESSION = mock.MagicMock()
FAKE_MANUKA = mock.MagicMock()
FAKE_NOVA = mock.MagicMock()
FAKE_TAYNAC = mock.MagicMock()
SWIFT_QUOTA_KEY = 'x-account-meta-quota-bytes'


class Quota:
    def __init__(self, quotas=[]):
        self.quotas = quotas

    # Used by nova and cinder
    def get(self, project_id):
        return mock.Mock(_info=self.quotas)

    # Used by trove
    def show(self, project_id):
        return self.quotas

    @staticmethod
    def delete(*args, **kwargs):
        pass

    @staticmethod
    def update(*args, **kwargs):
        pass


class CinderClient:
    def __init__(self):
        self.quotas = Quota({'gigabytes': 10, 'volumes': 10})


class SwiftClient:
    @staticmethod
    def get_account():
        return {SWIFT_QUOTA_KEY: 2000}, None

    @staticmethod
    def post_account(*args, **kwargs):
        pass


class NeutronClient:
    @staticmethod
    def show_quota(project_id):
        return {'quota': {'network': 10}}

    @staticmethod
    def show_quota_default(project_id):
        return {'quota': {'network': 5}}

    @staticmethod
    def delete_quota(*args, **kwargs):
        pass

    @staticmethod
    def update_quota(*args, **kwargs):
        pass


class TroveClient:
    def __init__(self):
        self.quota = Quota()


class MagnumQuota:
    def __init__(self, limit):
        self.hard_limit = limit


class MagnumQuotaManager:
    def get(self, *args):
        return MagnumQuota(5)

    def delete(self, *args):
        pass

    def create(self, *args, **kwargs):
        pass


class MagnumClient:
    def __init__(self):
        self.quotas = MagnumQuotaManager()


class ManilaClient:
    class ShareTypes:
        @staticmethod
        def list():
            return []

    def __init__(self):
        self.quotas = Quota({'gigabytes': 10, 'shares': 10})
        self.share_types = self.ShareTypes()


class Openstack:
    fake_quota = lb_quota.Quota(id='fake', load_balancers=10)

    class LoadBalancer:
        def get_quota(self, project_id):
            return Openstack.fake_quota

        def delete_quota(self, project_id):
            return

        def update_quota(self, quota):
            return Openstack.fake_quota

    def __init__(self):
        self.load_balancer = self.LoadBalancer()


def get_keystone(session):
    return FAKE_KEYSTONE


def get_nova(session):
    return FAKE_NOVA


def get_cinder(session):
    return CinderClient()


def get_swift(session, project_id):
    return SwiftClient()


def get_neutron(session):
    return NeutronClient()


def get_trove(session):
    return TroveClient()


def get_manila(session):
    return ManilaClient()


def get_magnum(session):
    return MagnumClient()


def get_designate(sess, project_id):
    return FAKE_DESIGNATE


def get_manuka(session):
    return FAKE_MANUKA


def get_warre(session):
    return FAKE_WARRE


def get_taynac(session):
    return FAKE_TAYNAC


def get_openstacksdk(sess):
    return Openstack()
