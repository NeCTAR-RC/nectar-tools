from unittest import mock


FAKE_DESIGNATE = mock.MagicMock()
FAKE_KEYSTONE = mock.MagicMock()
FAKE_FD_API = mock.MagicMock()
FAKE_FD_API_CLASS = mock.MagicMock(return_value=FAKE_FD_API)
FAKE_GET_SESSION = mock.MagicMock()
FAKE_MANUKA = mock.MagicMock()
SWIFT_QUOTA_KEY = 'x-account-meta-quota-bytes'


class Quota(object):

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


class NovaClient(object):

    class Servers(object):
        def list(*args, **kwargs):
            return []

    def __init__(self):
        self.quotas = Quota({'cores': 20,
                             'ram': 400,
                             'instances': 10})
        self.servers = self.Servers()


class CinderClient(object):

    def __init__(self):
        self.quotas = Quota({'gigabytes': 10,
                             'volumes': 10})


class SwiftClient(object):

    @staticmethod
    def get_account():
        return {SWIFT_QUOTA_KEY: 2000}, None

    @staticmethod
    def post_account(*args, **kwargs):
        pass


class NeutronClient(object):

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


class TroveClient(object):

    def __init__(self):
        self.quota = Quota()


class ManilaClient(object):

    class ShareTypes(object):
        @staticmethod
        def list():
            return []

    def __init__(self):
        self.quotas = Quota({'gigabytes': 10,
                             'shares': 10})
        self.share_types = self.ShareTypes()


def get_keystone(session):
    return FAKE_KEYSTONE


def get_nova(session):
    return NovaClient()


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


def get_designate(sess, project_id):
    return FAKE_DESIGNATE


def get_manuka(session):
    return FAKE_MANUKA
