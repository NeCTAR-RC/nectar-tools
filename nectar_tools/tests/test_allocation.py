from unittest import mock

from nectar_tools import allocations
from nectar_tools.allocations import states
from nectar_tools import test

from nectar_tools.tests import fakes


@mock.patch('nectar_tools.allocations.AllocationManager')
@mock.patch('nectar_tools.auth.get_session', new=mock.Mock())
class AllocationTests(test.TestCase):

    def test_init(self, mock_manager):
        allocation = allocations.Allocation(
            mock_manager, fakes.ALLOCATION_RESPONSE, None)

        self.assertEqual(1, allocation.id)
        self.assertEqual(15, len(allocation.quotas))
        self.assertEqual(mock_manager, allocation.manager)
        self.assertEqual(None, allocation.service_quotas)
        self.assertFalse(allocation.noop)

    def test_update(self, mock_manager):
        allocation = allocations.Allocation(
            mock_manager, fakes.ALLOCATION_RESPONSE, None)

        project_id = 'something-different'
        allocation.update(project_id=project_id)
        mock_manager.update_allocation.assert_called_once_with(
            allocation.id, project_id=project_id)
        self.assertEqual(project_id, allocation.project_id)

    def test_update_delete(self, mock_manager):
        allocation = allocations.Allocation(
            mock_manager, fakes.ALLOCATION_RESPONSE, None)

        with mock.patch.object(allocation, 'delete') as mock_delete:
            allocation.update(status=states.DELETED)
            mock_delete.assert_called_once_with()

    def test_delete(self, mock_manager):
        allocation = allocations.Allocation(
            mock_manager, fakes.ALLOCATION_RESPONSE, None)

        allocation.delete()

        mock_manager.update_allocation.assert_called_once_with(
            allocation.id, status=states.DELETED)

        self.assertEqual(states.DELETED, allocation.status)

    def test_delete_with_parent(self, mock_manager):
        data = fakes.ALLOCATION_RESPONSE
        parent_id = 22
        data['parent_request'] = parent_id
        allocation = allocations.Allocation(
            mock_manager, data, None)

        allocation.delete()
        calls = [mock.call(allocation.id, status=states.DELETED),
                 mock.call(allocation.parent_request, status=states.DELETED)]
        mock_manager.update_allocation.has_calls(calls)
