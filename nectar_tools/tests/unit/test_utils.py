from unittest import mock

from nectar_tools import auth
from nectar_tools import config
from nectar_tools import test
from nectar_tools import utils

from nectar_tools.tests import fakes


PROJECT = fakes.FakeProject('active')
CONF = config.CONFIG


class UtilsTests(test.TestCase):
    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        self.allocation = fakes.get_allocation()

    def test_get_compute_zones_national(self):
        self.allocation.associated_site = 'monash'
        self.allocation.national = True
        with mock.patch.object(
            auth, 'get_allocation_client'
        ) as mock_get_client:
            a_client = mock_get_client.return_value
            a_client.zones.compute_homes.return_value = fakes.COMPUTE_HOMES
            zones = utils.get_compute_zones(None, self.allocation)
            self.assertEqual([], zones)

    def test_get_compute_zones_local(self):
        self.allocation.associated_site = 'qcif'
        self.allocation.national = False
        with mock.patch.object(
            auth, 'get_allocation_client'
        ) as mock_get_client:
            a_client = mock_get_client.return_value
            a_client.zones.compute_homes.return_value = fakes.COMPUTE_HOMES
            zones = utils.get_compute_zones(None, self.allocation)
            self.assertEqual(['QRIScloud'], zones)

    def test_get_compute_zones_multiple(self):
        self.allocation.associated_site = 'monash'
        self.allocation.national = False
        with mock.patch.object(
            auth, 'get_allocation_client'
        ) as mock_get_client:
            a_client = mock_get_client.return_value
            a_client.zones.compute_homes.return_value = fakes.COMPUTE_HOMES
            zones = utils.get_compute_zones(None, self.allocation)
            self.assertEqual(['monash-01', 'monash-02', 'monash-03'], zones)

    def test_get_compute_zones_local_no_site(self):
        # Test for anomalous 'associated_site' setting ...
        self.allocation.associated_site = None
        self.allocation.national = False
        with mock.patch.object(
            auth, 'get_allocation_client'
        ) as mock_get_client:
            a_client = mock_get_client.return_value
            a_client.zones.compute_homes.return_value = fakes.COMPUTE_HOMES
            zones = utils.get_compute_zones(None, self.allocation)
            self.assertEqual([], zones)

    def test_get_out_of_zone_instances_no_instances(self):
        project = fakes.FakeProject()
        with test.nested(
            mock.patch.object(utils, 'get_compute_zones'),
            mock.patch('nectar_tools.expiry.archiver.NovaArchiver'),
        ) as (mock_get_zones, mock_archiver):
            mock_get_zones.return_value = ['nova', 'nova-2']
            nova = mock.Mock()
            mock_archiver.return_value = nova
            nova._all_instances.return_value = []

            instances = utils.get_out_of_zone_instances(
                None, self.allocation, project
            )
            self.assertEqual([], instances)

    def test_get_out_of_zone_instances_out_of_zone(self):
        project = fakes.FakeProject()
        with test.nested(
            mock.patch.object(utils, 'get_compute_zones'),
            mock.patch('nectar_tools.expiry.archiver.NovaArchiver'),
        ) as (mock_get_zones, mock_archiver):
            mock_get_zones.return_value = ['nova', 'nova-2']
            nova = mock.Mock()
            mock_archiver.return_value = nova
            instance = fakes.FakeInstance(availability_zone='wrong')
            nova._all_instances.return_value = [
                instance,
                fakes.FakeInstance(availability_zone='nova'),
                fakes.FakeInstance(availability_zone=''),
            ]

            instances = utils.get_out_of_zone_instances(
                None, self.allocation, project
            )
            self.assertEqual([instance], instances)

    def test_get_out_of_zone_instances_instances_in_zone(self):
        project = fakes.FakeProject()
        with test.nested(
            mock.patch.object(utils, 'get_compute_zones'),
            mock.patch('nectar_tools.expiry.archiver.NovaArchiver'),
        ) as (mock_get_zones, mock_archiver):
            mock_get_zones.return_value = ['nova', 'nova-2']
            nova = mock.Mock()
            mock_archiver.return_value = nova
            nova._all_instances.return_value = [
                fakes.FakeInstance(availability_zone='nova-2'),
                fakes.FakeInstance(availability_zone='nova-2'),
                fakes.FakeInstance(availability_zone='nova'),
            ]

            instances = utils.get_out_of_zone_instances(
                None, self.allocation, project
            )
            self.assertEqual([], instances)

    def test_is_email_address_valid(self):
        email = "name@fake.org"
        self.assertEqual(True, utils.is_email_address(email))

    def test_is_email_address_invalid(self):
        email1 = "fake@name@fake.org"
        email2 = "@fake.org"
        email3 = "fake"
        self.assertEqual(False, utils.is_email_address(email1))
        self.assertEqual(False, utils.is_email_address(email2))
        self.assertEqual(False, utils.is_email_address(email3))

    def test_get_emails(self):
        user1 = mock.Mock(email='fake1@fake.com', enabled=True)
        user2 = mock.Mock(
            spec=['email', 'enabled'], email='fake2@fake.com', enabled=False
        )
        user3 = mock.Mock(email='fake3@fake.com', enabled=False, inactive=True)
        user4 = mock.Mock(
            email='fake4@fake.com', enabled=False, inactive=False
        )
        user5 = mock.Mock(spec=['enabled'], enabled=True)
        user6 = mock.Mock(email='fake6-bogus', enabled=True)
        users = [user1, user2, user3, user4, user5, user6]
        emails = utils.get_emails(users)
        self.assertEqual(['fake1@fake.com', 'fake3@fake.com'], emails)

    def test_get_project_users(self):
        project = fakes.FakeProject()
        role = 'fakerole'
        role_assignments = [mock.Mock(), mock.Mock()]
        role_assignments[0].user = {}
        role_assignments[1].user = {}
        role_assignments[0].user['id'] = 'fakeuser1'
        role_assignments[1].user['id'] = 'fakeuser2'

        mock_keystone = mock.Mock()

        def user_side_effect(value):
            mock_user = mock.Mock()
            mock_user.id = value
            return mock_user

        mock_keystone.role_assignments.list.return_value = role_assignments
        mock_keystone.users.get.side_effect = user_side_effect

        users = utils.get_project_users(mock_keystone, project, 'fakerole')

        mock_keystone.role_assignments.list.assert_called_with(
            project=project, role=role
        )
        mock_keystone.users.get.assert_has_calls(
            [mock.call('fakeuser1'), mock.call('fakeuser2')]
        )
        self.assertEqual(['fakeuser1', 'fakeuser2'], [x.id for x in users])

    @mock.patch("nectar_tools.utils.get_project_users")
    def test_get_project_recipients(self, mock_get):
        def get_users_side_effect(client, project, role):
            if role == CONF.keystone.manager_role_id:
                return [
                    fakes.FakeUser(id="tm1", email="tm1@fake.com"),
                    fakes.FakeUser(id="tm2", email="tm2@fake.com"),
                ]
            else:
                return [
                    fakes.FakeUser(id="member1", email="member1@fake.com"),
                    fakes.FakeUser(id="member2", email="member2@fake.com"),
                ]

        mock_get.side_effect = get_users_side_effect
        mock_client = mock.Mock()
        mock_project = mock.Mock()

        (to, cc) = utils.get_project_recipients(mock_client, mock_project)

        self.assertEqual("tm1@fake.com", to)
        self.assertEqual(
            ["tm2@fake.com", "member1@fake.com", "member2@fake.com"], cc
        )

    @mock.patch("nectar_tools.utils.get_project_users")
    def test_get_project_recipients_mixed(self, mock_get):
        def get_users_side_effect(client, project, role):
            if role == CONF.keystone.manager_role_id:
                return [
                    fakes.FakeUser(id="tm1", email="tm1@fake.com"),
                    fakes.FakeUser(id="tm2", email="tm2@fake.com"),
                ]
            else:
                return [
                    fakes.FakeUser(id="member1", email="member1@fake.com"),
                    fakes.FakeUser(id="tm1", email="tm1@fake.com"),
                    fakes.FakeUser(id="member2", email="member2@fake.com"),
                    fakes.FakeUser(id="tm2", email="tm2@fake.com"),
                    fakes.FakeUser(id="member3", email="member3@fake.com"),
                ]

        mock_get.side_effect = get_users_side_effect
        mock_client = mock.Mock()
        mock_project = mock.Mock()

        (to, cc) = utils.get_project_recipients(mock_client, mock_project)

        self.assertEqual("tm1@fake.com", to)
        self.assertEqual(
            [
                "tm2@fake.com",
                "member1@fake.com",
                "member2@fake.com",
                "member3@fake.com",
            ],
            cc,
        )

    @mock.patch("nectar_tools.utils.get_project_users")
    def test_get_project_recipients_no_tm(self, mock_get):
        def get_users_side_effect(client, project, role):
            if role == CONF.keystone.manager_role_id:
                return []
            else:
                return [
                    fakes.FakeUser(id="member1", email="member1@fake.com"),
                    fakes.FakeUser(id="member2", email="member2@fake.com"),
                    fakes.FakeUser(id="member3", email="member3@fake.com"),
                ]

        mock_get.side_effect = get_users_side_effect
        mock_client = mock.Mock()
        mock_project = mock.Mock()

        (to, cc) = utils.get_project_recipients(mock_client, mock_project)

        self.assertEqual("member1@fake.com", to)
        self.assertEqual(["member2@fake.com", "member3@fake.com"], cc)

    @mock.patch("nectar_tools.utils.get_project_users")
    def test_get_project_recipients_none(self, mock_get):
        def get_users_side_effect(client, project, role):
            return []

        mock_get.side_effect = get_users_side_effect
        mock_client = mock.Mock()
        mock_project = mock.Mock()

        (to, cc) = utils.get_project_recipients(mock_client, mock_project)

        self.assertIsNone(to)
        self.assertEqual([], cc)

    @mock.patch("nectar_tools.utils.get_project_users")
    def test_get_project_recipients_too_many(self, mock_get):
        def get_users_side_effect(client, project, role):
            if role == CONF.keystone.manager_role_id:
                return [
                    fakes.FakeUser(id="tm1", email="tm1@fake.com"),
                    fakes.FakeUser(id="tm2", email="tm2@fake.com"),
                ]
            else:
                return [
                    fakes.FakeUser(id=f"m{i}", email=f"m{i}@fake.com")
                    for i in range(1, 100)
                ]

        mock_get.side_effect = get_users_side_effect
        mock_client = mock.Mock()
        mock_project = mock.Mock()

        (to, cc) = utils.get_project_recipients(mock_client, mock_project)

        self.assertEqual("tm1@fake.com", to)
        self.assertEqual(49, len(cc))
        self.assertEqual("m1@fake.com", cc[1])
        self.assertEqual("m48@fake.com", cc[-1])

    @mock.patch("nectar_tools.utils.get_project_users")
    def test_get_allocation_recipients(self, mock_get):
        def get_users_side_effect(client, project, role):
            if role == CONF.keystone.manager_role_id:
                return [
                    fakes.FakeUser(id="tm1", email="tm1@fake.com"),
                    fakes.FakeUser(id="tm2", email="tm2@fake.com"),
                ]
            else:
                return [
                    fakes.FakeUser(id="member1", email="member1@fake.com"),
                    fakes.FakeUser(id="member2", email="member2@fake.com"),
                ]

        mock_get.side_effect = get_users_side_effect
        mock_client = mock.Mock()
        mock_project = mock.Mock()
        mock_allocation = mock.Mock(
            project_id=mock_project,
            contact_email="contact@fake.com",
            approver_email="approver@fake.com",
        )

        (to, cc) = utils.get_allocation_recipients(
            mock_client, mock_allocation
        )

        self.assertEqual("contact@fake.com", to)
        self.assertEqual(
            [
                "tm1@fake.com",
                "tm2@fake.com",
                "approver@fake.com",
                "member1@fake.com",
                "member2@fake.com",
            ],
            cc,
        )
        mock_get.assert_has_calls(
            [
                mock.call(
                    mock_client,
                    mock_project,
                    role=CONF.keystone.manager_role_id,
                ),
                mock.call(
                    mock_client,
                    mock_project,
                    role=CONF.keystone.member_role_id,
                ),
            ]
        )


def _marker_of(item):
    return item.id if hasattr(item, 'id') else item['id']


def _paginating_list_method(items, page_size):
    """Fake list call that honours the `marker` kwarg (nova/designate)."""

    def _call(marker=None, **kwargs):
        if marker is None:
            start = 0
        else:
            ids = [_marker_of(i) for i in items]
            start = ids.index(marker) + 1
        return items[start : start + page_size]

    return mock.Mock(side_effect=_call)


def _marker_ignoring_list_method(items, max_calls=50):
    """Fake list call that ignores `marker` and always returns everything.

    Models keystone users/projects/roles with no list_limit configured.
    Raises rather than hanging the test suite if the helper fails to
    terminate.
    """

    def _call(marker=None, **kwargs):
        if _call_mock.call_count > max_calls:
            raise AssertionError("list_resources did not terminate")
        return list(items)

    _call_mock = mock.Mock(side_effect=_call)
    return _call_mock


class ListResourcesTests(test.TestCase):
    def test_empty(self):
        list_method = mock.Mock(return_value=[])
        self.assertEqual([], utils.list_resources(list_method))
        list_method.assert_called_once_with()

    def test_single_page_attribute_style(self):
        items = [mock.Mock(id='a'), mock.Mock(id='b')]
        list_method = _paginating_list_method(items, page_size=10)
        result = utils.list_resources(list_method)
        self.assertEqual(items, result)

    def test_marker_pagination_attribute_style(self):
        items = [mock.Mock(id=c) for c in 'abcde']
        list_method = _paginating_list_method(items, page_size=2)
        result = utils.list_resources(list_method)
        self.assertEqual(items, result)
        self.assertEqual(['a', 'b', 'c', 'd', 'e'], [r.id for r in result])

    def test_marker_pagination_dict_style(self):
        items = [{'id': c} for c in 'abcde']
        list_method = _paginating_list_method(items, page_size=2)
        result = utils.list_resources(list_method)
        self.assertEqual(items, result)

    def test_kwargs_passed_through(self):
        items = [mock.Mock(id='a')]
        list_method = _paginating_list_method(items, page_size=10)
        utils.list_resources(list_method, domain='default')
        for call in list_method.call_args_list:
            self.assertEqual('default', call.kwargs['domain'])

    def test_marker_ignored_terminates(self):
        # Regression: keystone without list_limit ignores `marker` and
        # returns the full list every call. Must terminate, not OOM.
        items = [mock.Mock(id=c) for c in 'abc']
        list_method = _marker_ignoring_list_method(items)
        result = utils.list_resources(list_method)
        self.assertEqual(items, result)
        # One initial call + one probe that yields no new items, then stop.
        self.assertEqual(2, list_method.call_count)
