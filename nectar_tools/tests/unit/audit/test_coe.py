import datetime
from unittest import mock

from freezegun import freeze_time

from nectar_tools.audit.coe import cluster
from nectar_tools import test


EOL_DATES = {
    'v1.31.0': datetime.date(2026, 7, 1),  # past EOL
    'v1.32.4': datetime.date(2026, 8, 15),  # within 60 days
    'v1.34.0': datetime.date(2027, 1, 1),  # far from EOL
}


def fake_cluster(**kwargs):
    values = {
        'uuid': 'cluster-uuid',
        'project_id': 'project-id',
        'status': 'CREATE_COMPLETE',
        'coe_version': 'v1.32.4',
    }
    values.update(kwargs)
    c = mock.Mock(spec=list(values))
    for key, value in values.items():
        setattr(c, key, value)
    return c


@freeze_time('2026-07-29')
class TestClusterAuditorK8sEOL(test.TestCase):
    def _get_auditor(self, dry_run=True):
        with test.nested(
            mock.patch('nectar_tools.auth.get_openstacksdk'),
            mock.patch('nectar_tools.auth.get_magnum_client'),
            mock.patch('nectar_tools.auth.get_keystone_client'),
            mock.patch('nectar_tools.auth.get_varroa_client'),
        ):
            auditor = cluster.ClusterAuditor(ks_session=None, dry_run=dry_run)
        mock_product = mock.Mock()
        mock_product.get_eol_date.side_effect = EOL_DATES.get
        patcher = mock.patch(
            'nectar_tools.audit.coe.cluster.eol.Product',
            return_value=mock_product,
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        return auditor

    def test_past_eol_creates_risk(self):
        auditor = self._get_auditor(dry_run=False)
        auditor.client.clusters.list.return_value = [
            fake_cluster(coe_version='v1.31.0')
        ]
        auditor.varroa_client.security_risk_types.list.return_value = []
        new_type = mock.Mock(id='type-id')
        new_type.name = 'kubernetes-eol'
        auditor.varroa_client.security_risk_types.create.return_value = (
            new_type
        )

        auditor.check_kubernetes_eol()

        mock_type_create = auditor.varroa_client.security_risk_types.create
        mock_type_create.assert_called_once_with(**cluster.EOL_RISK_TYPE)
        auditor.varroa_client.security_risks.create.assert_called_once_with(
            time='2026-07-29T00:00:00+0000',
            expires='2026-08-05T00:00:00+0000',
            type_id='type-id',
            project_id='project-id',
            resource_id='cluster-uuid',
            resource_type='cluster',
        )

    def test_nearing_eol_creates_risk(self):
        auditor = self._get_auditor(dry_run=False)
        auditor.client.clusters.list.return_value = [
            fake_cluster(coe_version='v1.32.4')
        ]
        existing_type = mock.Mock(id='nearing-type-id')
        existing_type.name = 'kubernetes-nearing-eol'
        auditor.varroa_client.security_risk_types.list.return_value = [
            existing_type
        ]

        auditor.check_kubernetes_eol()

        # The existing risk type is reused, not recreated.
        auditor.varroa_client.security_risk_types.create.assert_not_called()
        auditor.varroa_client.security_risks.create.assert_called_once_with(
            time='2026-07-29T00:00:00+0000',
            expires='2026-08-05T00:00:00+0000',
            type_id='nearing-type-id',
            project_id='project-id',
            resource_id='cluster-uuid',
            resource_type='cluster',
        )

    def test_dry_run_creates_nothing(self):
        auditor = self._get_auditor(dry_run=True)
        auditor.client.clusters.list.return_value = [
            fake_cluster(coe_version='v1.31.0')
        ]

        auditor.check_kubernetes_eol()

        auditor.varroa_client.security_risk_types.list.assert_not_called()
        auditor.varroa_client.security_risks.create.assert_not_called()

    def test_supported_version_no_risk(self):
        auditor = self._get_auditor(dry_run=False)
        auditor.client.clusters.list.return_value = [
            fake_cluster(coe_version='v1.34.0')
        ]

        auditor.check_kubernetes_eol()

        auditor.varroa_client.security_risks.create.assert_not_called()

    def test_skips_transient_and_broken_clusters(self):
        auditor = self._get_auditor(dry_run=False)
        auditor.client.clusters.list.return_value = [
            fake_cluster(status='DELETE_IN_PROGRESS'),
            fake_cluster(status='CREATE_IN_PROGRESS'),
            fake_cluster(status='CREATE_FAILED'),
            fake_cluster(coe_version=None),
        ]

        auditor.check_kubernetes_eol()

        auditor.varroa_client.security_risks.create.assert_not_called()

    def test_unknown_version_skipped(self):
        auditor = self._get_auditor(dry_run=False)
        auditor.client.clusters.list.return_value = [
            fake_cluster(coe_version='v9.9.9')
        ]

        auditor.check_kubernetes_eol()

        auditor.varroa_client.security_risks.create.assert_not_called()
