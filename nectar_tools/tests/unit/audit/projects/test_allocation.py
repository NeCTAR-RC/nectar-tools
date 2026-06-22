from unittest import mock

from nectarallocationclient import states as allocation_states

from nectar_tools.audit.projects import allocation
from nectar_tools.expiry import expiry_states
from nectar_tools import test
from nectar_tools.tests import fakes


class ProjectAllocationAuditorTests(test.TestCase):
    def setUp(self):
        super().setUp()
        patcher_sdk = mock.patch('nectar_tools.auth.get_openstacksdk')
        patcher_keystone = mock.patch('nectar_tools.auth.get_keystone_client')
        patcher_allocation = mock.patch(
            'nectar_tools.auth.get_allocation_client'
        )
        self.mock_sdk = patcher_sdk.start()
        self.mock_keystone = patcher_keystone.start()
        self.mock_allocation = patcher_allocation.start()
        self.addCleanup(patcher_sdk.stop)
        self.addCleanup(patcher_keystone.stop)
        self.addCleanup(patcher_allocation.stop)

    def _get_auditor(self, project, dry_run=False, allocation_status=None):
        auditor = allocation.ProjectAllocationAuditor(
            ks_session=mock.Mock(), project=project, dry_run=dry_run
        )
        # By default link a deleted allocation so the resource check runs.
        if allocation_status is False:
            alloc = None
        else:
            if allocation_status is None:
                allocation_status = allocation_states.DELETED
            alloc = mock.Mock(status=allocation_status)
        auditor._get_allocation_or_none = mock.Mock(return_value=alloc)
        return auditor

    @mock.patch.object(allocation.archiver, 'ResourceArchiver')
    def test_check_deleted_resources_not_deleted(self, mock_archiver):
        project = fakes.FakeProject(expiry_status=expiry_states.ACTIVE)
        auditor = self._get_auditor(project)

        auditor.check_deleted_resources()

        # No archiver should be built for a project that isn't deleted.
        mock_archiver.assert_not_called()
        auditor.k_client.projects.update.assert_not_called()

    @mock.patch.object(allocation.archiver, 'ResourceArchiver')
    def test_check_deleted_resources_no_status(self, mock_archiver):
        project = fakes.FakeProject()
        auditor = self._get_auditor(project)

        auditor.check_deleted_resources()

        mock_archiver.assert_not_called()
        auditor.k_client.projects.update.assert_not_called()

    @mock.patch.object(allocation.archiver, 'ResourceArchiver')
    def test_check_deleted_resources_no_allocation(self, mock_archiver):
        # Deleted project with no (or missing) allocation is out of sync;
        # leave it for check_deleted_allocation to report.
        project = fakes.FakeProject(expiry_status=expiry_states.DELETED)
        auditor = self._get_auditor(project, allocation_status=False)

        auditor.check_deleted_resources()

        mock_archiver.assert_not_called()
        auditor.k_client.projects.update.assert_not_called()

    @mock.patch.object(allocation.archiver, 'ResourceArchiver')
    def test_check_deleted_resources_live_allocation(self, mock_archiver):
        # Deleted project linked to a live allocation is out of sync; don't
        # revert, as that would fight the allocation state.
        project = fakes.FakeProject(expiry_status=expiry_states.DELETED)
        auditor = self._get_auditor(
            project, allocation_status=allocation_states.APPROVED
        )

        auditor.check_deleted_resources()

        mock_archiver.assert_not_called()
        auditor.k_client.projects.update.assert_not_called()

    @mock.patch.object(allocation.archiver, 'ResourceArchiver')
    def test_check_deleted_resources_no_resources(self, mock_archiver):
        mock_archiver.return_value.is_delete_successful.return_value = True
        project = fakes.FakeProject(expiry_status=expiry_states.DELETED)
        auditor = self._get_auditor(project)

        auditor.check_deleted_resources()

        mock_archiver.assert_called_once_with(
            project,
            archivers=allocation.DELETE_ARCHIVERS,
            ks_session=auditor.ks_session,
            dry_run=False,
        )
        mock_archiver.return_value.is_delete_successful.assert_called_once_with()
        auditor.k_client.projects.update.assert_not_called()

    @mock.patch.object(allocation.archiver, 'ResourceArchiver')
    def test_check_deleted_resources_with_resources(self, mock_archiver):
        mock_archiver.return_value.is_delete_successful.return_value = False
        project = fakes.FakeProject(expiry_status=expiry_states.DELETED)
        auditor = self._get_auditor(project)

        auditor.check_deleted_resources()

        auditor.k_client.projects.update.assert_called_once_with(
            project.id, expiry_status=expiry_states.DELETING
        )

    @mock.patch.object(allocation.archiver, 'ResourceArchiver')
    def test_check_deleted_resources_with_resources_dry_run(
        self, mock_archiver
    ):
        mock_archiver.return_value.is_delete_successful.return_value = False
        project = fakes.FakeProject(expiry_status=expiry_states.DELETED)
        auditor = self._get_auditor(project, dry_run=True)

        auditor.check_deleted_resources()

        # In dry run mode we detect but must not change the project.
        auditor.k_client.projects.update.assert_not_called()
