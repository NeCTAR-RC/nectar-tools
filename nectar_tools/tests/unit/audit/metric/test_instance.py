from unittest import mock

from gnocchiclient import exceptions as g_exceptions
import novaclient.exceptions

from nectar_tools.audit.metric import instance
from nectar_tools import test
from nectar_tools.tests import fakes


class TestEnsureInstanceConsistency(test.TestCase):
    def _get_auditor(self, dry_run=False):
        with test.nested(
            mock.patch('nectar_tools.auth.get_openstacksdk'),
            mock.patch('nectar_tools.auth.get_gnocchi_client'),
            mock.patch('nectar_tools.auth.get_nova_client'),
        ):
            auditor = instance.InstanceAuditor(
                ks_session=None, dry_run=dry_run, days_ago=90, az=None
            )
        return auditor

    @staticmethod
    def _server(id='fake-uuid', terminated_at=None):
        return fakes.FakeInstance(
            id=id,
            created='2025-01-01T00:00:00Z',
            tenant_id='project1',
            **{'OS-SRV-USG:terminated_at': terminated_at},
        )

    @staticmethod
    def _gnocchi_instance(ended_at='2025-03-01T00:00:00'):
        return {
            'started_at': '2025-01-01T00:00:00',
            'ended_at': ended_at,
        }

    def test_clear_ended_at_instance_not_in_nova(self):
        # An instance ended in gnocchi whose nova listing entry has no
        # terminated_at but which is gone from nova must be skipped, not
        # have its ended_at cleared (gnocchi 500s on a null ended_at).
        auditor = self._get_auditor()
        auditor.n_client.servers.list.side_effect = [[self._server()], []]
        auditor.g_client.resource.get.return_value = self._gnocchi_instance()
        auditor.n_client.servers.get.side_effect = (
            novaclient.exceptions.NotFound(404)
        )

        auditor.ensure_instance_consistency()

        auditor.g_client.resource.update.assert_not_called()

    def test_ended_at_from_stale_listing(self):
        # The listing said not deleted, but nova has a terminated_at
        # differing from gnocchi's: set the real end time.
        auditor = self._get_auditor()
        auditor.n_client.servers.list.side_effect = [[self._server()], []]
        auditor.g_client.resource.get.return_value = self._gnocchi_instance()
        auditor.n_client.servers.get.return_value = self._server(
            terminated_at='2025-03-05T12:00:00'
        )

        auditor.ensure_instance_consistency()

        auditor.g_client.resource.update.assert_called_once_with(
            'instance',
            'fake-uuid',
            {'ended_at': '2025-03-05 12:00:00+00:00'},
        )

    def test_ended_at_from_stale_listing_already_correct(self):
        # Nova's terminated_at matches gnocchi's ended_at: no repair.
        auditor = self._get_auditor()
        auditor.n_client.servers.list.side_effect = [[self._server()], []]
        auditor.g_client.resource.get.return_value = self._gnocchi_instance()
        auditor.n_client.servers.get.return_value = self._server(
            terminated_at='2025-03-01T00:10:00'
        )

        auditor.ensure_instance_consistency()

        auditor.g_client.resource.update.assert_not_called()

    def test_clear_ended_at_running_instance(self):
        # Confirmed still running in nova but ended in gnocchi: clear
        # the end time.
        auditor = self._get_auditor()
        auditor.n_client.servers.list.side_effect = [[self._server()], []]
        auditor.g_client.resource.get.return_value = self._gnocchi_instance()
        auditor.n_client.servers.get.return_value = self._server()

        auditor.ensure_instance_consistency()

        auditor.g_client.resource.update.assert_called_once_with(
            'instance', 'fake-uuid', {'ended_at': None}
        )

    def test_gnocchi_error_continues(self):
        # A gnocchi server error on one resource must not abort the
        # whole check.
        auditor = self._get_auditor()
        servers = [self._server(id='fake-1'), self._server(id='fake-2')]
        auditor.n_client.servers.list.side_effect = [servers, []]
        auditor.g_client.resource.get.side_effect = [
            self._gnocchi_instance(),
            self._gnocchi_instance(),
        ]
        auditor.n_client.servers.get.side_effect = servers
        auditor.g_client.resource.update.side_effect = [
            g_exceptions.ClientException(code=500, message='boom'),
            None,
        ]

        auditor.ensure_instance_consistency()

        self.assertEqual(2, auditor.g_client.resource.update.call_count)

    def test_dry_run(self):
        auditor = self._get_auditor(dry_run=True)
        auditor.n_client.servers.list.side_effect = [[self._server()], []]
        auditor.g_client.resource.get.return_value = self._gnocchi_instance()
        auditor.n_client.servers.get.return_value = self._server()

        auditor.ensure_instance_consistency()

        auditor.g_client.resource.update.assert_not_called()
