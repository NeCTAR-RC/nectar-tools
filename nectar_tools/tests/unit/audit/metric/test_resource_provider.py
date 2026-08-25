from unittest import mock

from nectar_tools.audit.metric import resource_provider
from nectar_tools import test


class TestEnsureSite(test.TestCase):
    def _get_auditor(self, dry_run=False):
        with test.nested(
            mock.patch('nectar_tools.auth.get_openstacksdk'),
            mock.patch('nectar_tools.auth.get_gnocchi_client'),
            mock.patch('nectar_tools.auth.get_placement_client'),
        ):
            auditor = resource_provider.ResourceProviderAuditor(
                ks_session=None, dry_run=dry_run
            )
        return auditor

    def test_recreated_rp_with_scope(self):
        auditor = self._get_auditor()
        new_rp = {'id': 'new-id', 'name': 'cc1.example.com'}
        old_rps = [
            {
                'id': 'old-id-1',
                'name': 'cc1.example.com',
                'site': 'monash',
                'scope': 'national',
            },
            {
                'id': 'old-id-2',
                'name': 'cc1.example.com',
                'site': 'monash',
                'scope': 'national',
            },
        ]
        auditor.g_client.resource.search.side_effect = [[new_rp], old_rps]

        auditor.ensure_site()

        auditor.g_client.resource.delete.assert_has_calls(
            [mock.call('old-id-1'), mock.call('old-id-2')]
        )
        auditor.g_client.resource.update.assert_called_once_with(
            resource_type='resource_provider',
            resource_id='new-id',
            resource={'site': 'monash', 'scope': 'national'},
        )

    def test_recreated_rp_without_scope(self):
        # Regression test: the repair must still run when the old
        # resource provider has no scope set
        auditor = self._get_auditor()
        new_rp = {'id': 'new-id', 'name': 'cc1.example.com'}
        old_rp = {'id': 'old-id', 'name': 'cc1.example.com', 'site': 'monash'}
        auditor.g_client.resource.search.side_effect = [[new_rp], [old_rp]]

        auditor.ensure_site()

        auditor.g_client.resource.delete.assert_called_once_with('old-id')
        auditor.g_client.resource.update.assert_called_once_with(
            resource_type='resource_provider',
            resource_id='new-id',
            resource={'site': 'monash'},
        )

    def test_new_rp_domain_mapping(self):
        auditor = self._get_auditor()
        new_rp = {'id': 'new-id', 'name': 'cc1.melbourne.nectar.org.au'}
        auditor.g_client.resource.search.side_effect = [[new_rp], []]

        auditor.ensure_site()

        auditor.g_client.resource.delete.assert_not_called()
        auditor.g_client.resource.update.assert_called_once_with(
            resource_type='resource_provider',
            resource_id='new-id',
            resource={'site': 'melbourne'},
        )

    def test_new_rp_unknown_domain(self):
        auditor = self._get_auditor()
        new_rp = {'id': 'new-id', 'name': 'cc1.unknown.example.com'}
        auditor.g_client.resource.search.side_effect = [[new_rp], []]

        auditor.ensure_site()

        auditor.g_client.resource.delete.assert_not_called()
        auditor.g_client.resource.update.assert_not_called()

    def test_dry_run(self):
        auditor = self._get_auditor(dry_run=True)
        new_rp = {'id': 'new-id', 'name': 'cc1.example.com'}
        old_rp = {'id': 'old-id', 'name': 'cc1.example.com', 'site': 'monash'}
        auditor.g_client.resource.search.side_effect = [[new_rp], [old_rp]]

        auditor.ensure_site()

        auditor.g_client.resource.delete.assert_not_called()
        auditor.g_client.resource.update.assert_not_called()
