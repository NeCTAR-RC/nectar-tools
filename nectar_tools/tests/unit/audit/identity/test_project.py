from unittest import mock

from nectar_tools.audit.identity import project
from nectar_tools import test


class FakeProject:
    def __init__(self, id, name, expiry_status=None):
        self.id = id
        self.name = name
        if expiry_status is not None:
            self.expiry_status = expiry_status


class FakeServer:
    def __init__(self, id, tenant_id):
        self.id = id
        self.tenant_id = tenant_id


class TestProjectAuditor(test.TestCase):
    def _get_auditor(self):
        with test.nested(
            mock.patch('nectar_tools.auth.get_openstacksdk'),
            mock.patch('nectar_tools.auth.get_keystone_client'),
            mock.patch('nectar_tools.auth.get_nova_client'),
        ):
            auditor = project.ProjectAuditor(ks_session=None)
        return auditor

    def test_check_deleted_no_instances(self):
        deleted = FakeProject('p1', 'gone', expiry_status='deleted')
        deleted_empty = FakeProject('p2', 'empty', expiry_status='deleted')
        active = FakeProject('p3', 'live', expiry_status='active')
        plain = FakeProject('p4', 'plain')
        auditor = self._get_auditor()
        auditor.k_client.projects.list.return_value = [
            deleted,
            deleted_empty,
            active,
            plain,
        ]
        servers = [
            FakeServer('s1', 'p1'),
            FakeServer('s2', 'p3'),
            FakeServer('s3', 'p1'),
            FakeServer('s4', 'p4'),
        ]
        auditor.n_client.servers.list.side_effect = [servers, []]

        with mock.patch.object(project, 'LOG') as mock_log:
            auditor.check_deleted_no_instances()

        # One paged all-tenants listing, no per-project calls
        auditor.n_client.servers.list.assert_has_calls(
            [
                mock.call(search_opts={'all_tenants': True}),
                mock.call(search_opts={'all_tenants': True}, marker='s4'),
            ]
        )
        self.assertEqual(2, auditor.n_client.servers.list.call_count)
        mock_log.error.assert_called_once_with(
            "Deleted project %s has %s running instances", deleted.name, 2
        )

    def test_check_deleted_no_instances_none_deleted(self):
        auditor = self._get_auditor()
        auditor.k_client.projects.list.return_value = [
            FakeProject('p1', 'live', expiry_status='active'),
            FakeProject('p2', 'plain'),
        ]

        with mock.patch.object(project, 'LOG') as mock_log:
            auditor.check_deleted_no_instances()

        auditor.n_client.servers.list.assert_not_called()
        mock_log.error.assert_not_called()
