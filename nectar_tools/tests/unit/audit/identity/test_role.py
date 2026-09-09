from unittest import mock

from nectar_tools.audit.identity import role
from nectar_tools import test
from nectar_tools.tests.unit.audit.identity import test_user


class FakeRole:
    def __init__(self, id, name):
        self.id = id
        self.name = name


class TestRoleAuditor(test.TestCase):
    def _get_auditor(self):
        with test.nested(
            mock.patch('nectar_tools.auth.get_openstacksdk'),
            mock.patch('nectar_tools.auth.get_keystone_client'),
        ):
            auditor = role.RoleAuditor(ks_session=None)
        return auditor

    def test_check_unused_roles(self):
        r1 = FakeRole(id='r1', name='member')
        r2 = FakeRole(id='r2', name='unused')
        auditor = self._get_auditor()
        auditor.k_client.roles.list.return_value = [r1, r2]
        auditor.k_client.role_assignments.list.return_value = [
            test_user.FakeAssignment(role_id='r1', user_id='u1'),
            test_user.FakeAssignment(role_id='r1', group_id='g1'),
        ]

        with mock.patch.object(role, 'LOG') as mock_log:
            auditor.check_unused_roles()

        # One bulk listing, no per-role calls
        auditor.k_client.role_assignments.list.assert_called_once_with()
        mock_log.info.assert_called_once_with("Role %s is unused", r2.name)
