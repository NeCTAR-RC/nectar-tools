import datetime
import testtools
from unittest.mock import patch

from nectar_tools.allocation_expiry import expirer
from nectar_tools import auth

from nectar_tools.tests import fakes

NOW = datetime.datetime(2017, 1, 1)



@patch('nectar_tools.allocation_expiry.archiver.NovaArchiver')
@patch('nectar_tools.allocation_expiry.expirer.NectarAllocationSession',
       return_value=fakes.FakeAllocationSession(fakes.PROJECTS))
@patch('nectar_tools.auth.get_session')
class AllocationExpiryTests(testtools.TestCase):
    
    def test_handle_project_active(self, mock_session,
                                   mock_allocation_session,
                                   mock_archiver):
        ex = expirer.NectarExpirer(now=NOW)
        project = fakes.FakeProject('active')
        ex.handle_project(project)
 
    def test_handle_project_warning(self, mock_session,
                                    mock_allocation_session,
                                    mock_archiver):
        ex = expirer.NectarExpirer(now=NOW)
        with patch.object(ex.k_client.projects, 'update') as mock_project_update:
            # Warning with long project, one month out
            project = fakes.FakeProject('warning1')
            ex.handle_project(project)
            mock_project_update.assert_called_with('warning1',
                                                   expiry_status='warning',
                                                   next_step=project.end_date)
            mock_project_update.reset_mock()
            
            # Warning with short project < 1 month out
            project = fakes.FakeProject('warning2')
            ex.handle_project(project)
            mock_project_update.assert_called_with('warning2',
                                                   expiry_status='warning',
                                                   next_step=project.end_date)
            mock_project_update.reset_mock()
            
            # Warning ready but  project extension in
            project = fakes.FakeProject('warning3')
            ex.handle_project(project)
            mock_project_update.assert_not_called()

    def test_handle_project_restricted(self, mock_session,
                                       mock_allocation_session,
                                       mock_archiver):
        ex = expirer.NectarExpirer(now=NOW)
        with patch.object(ex.k_client.projects, 'update') as mock_project_update:
            # Not ready for next step
            project = fakes.FakeProject('restricted1')
            ex.handle_project(project)
            mock_project_update.assert_not_called()
            mock_project_update.reset_mock()

            # Ready for next step
            project = fakes.FakeProject('restricted2')
            ex.handle_project(project)
            one_month = (NOW + datetime.timedelta(days=30)).strftime(
                expirer.DATE_FORMAT)
            mock_project_update.assert_called_with('restricted2',
                                                   expiry_status='restricted',
                                                   next_step=one_month)
            
            mock_project_update.reset_mock()

    def test_handle_project_archiving(self, mock_session,
                                      mock_allocation_session,
                                      mock_archiver):
        ex = expirer.NectarExpirer(now=NOW)
        