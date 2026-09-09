from unittest import mock

from nectar_tools.audit.identity import user
from nectar_tools import test
from nectar_tools.tests import fakes


class FakeAssignment:
    def __init__(self, role_id='role1', user_id=None, group_id=None):
        self.role = {'id': role_id}
        if user_id:
            self.user = {'id': user_id}
        if group_id:
            self.group = {'id': group_id}


class TestUserAuditor(test.TestCase):
    def _get_auditor(self, users):
        with test.nested(
            mock.patch('nectar_tools.auth.get_openstacksdk'),
            mock.patch('nectar_tools.auth.get_keystone_client'),
        ):
            with mock.patch('nectar_tools.utils.list_resources') as mock_list:
                mock_list.return_value = users
                auditor = user.UserAuditor(ks_session=None)
        return auditor

    def test_check_users_no_projects(self):
        u1 = fakes.FakeUser(id='u1', email='u1@example.org')
        u2 = fakes.FakeUser(id='u2', email='u2@example.org')
        u3 = fakes.FakeUser(id='u3', enabled=False, email='u3@example.org')
        auditor = self._get_auditor([u1, u2, u3])
        # u1 has a direct assignment, u2 has none, u3 is disabled;
        # group assignments must not break the user id lookup.
        auditor.k_client.role_assignments.list.return_value = [
            FakeAssignment(user_id='u1'),
            FakeAssignment(group_id='g1'),
        ]

        with mock.patch.object(user, 'LOG') as mock_log:
            auditor.check_users_no_projects()

        # One bulk listing, no per-user calls
        auditor.k_client.role_assignments.list.assert_called_once_with()
        mock_log.info.assert_called_once_with(
            "User %s has no roles assigned", u2.name
        )

    def test_check_default_project_id(self):
        u_none = fakes.FakeUser(id='u1', email='u1@example.org')
        u_missing = fakes.FakeUser(id='u2', email='u2@example.org')
        u_missing.default_project_id = 'gone'
        u_admin = fakes.FakeUser(id='u3', email='u3@example.org')
        u_admin.default_project_id = 'p1'
        u_bot = fakes.FakeUser(id='u4', email='proj2_bot')
        u_bot.default_project_id = 'p2'
        u_pt = fakes.FakeUser(id='u5', email='u5@example.org')
        u_pt.default_project_id = 'p3'
        u_other = fakes.FakeUser(id='u6', email='u6@example.org')
        u_other.default_project_id = 'p4'

        projects = [
            fakes.FakeProject(id='p1', name='admin', expiry_status='admin'),
            fakes.FakeProject(id='p2', name='proj2'),
            fakes.FakeProject(id='p3', name='pt-abc123'),
            fakes.FakeProject(id='p4', name='research'),
        ]
        auditor = self._get_auditor(
            [u_none, u_missing, u_admin, u_bot, u_pt, u_other]
        )
        auditor.k_client.projects.list.return_value = projects

        with mock.patch.object(user, 'LOG') as mock_log:
            auditor.check_default_project_id()

        # One bulk listing, no per-user projects.get calls
        auditor.k_client.projects.get.assert_not_called()
        mock_log.info.assert_called_once_with(
            "User %s has no default_project_id", u_none.name
        )
        mock_log.warning.assert_has_calls(
            [
                mock.call(
                    "User %s default_project_id is a non-existent project",
                    u_missing.name,
                ),
                mock.call(
                    "User %s default_project_id is not a PT", u_other.name
                ),
            ]
        )
        self.assertEqual(2, mock_log.warning.call_count)
