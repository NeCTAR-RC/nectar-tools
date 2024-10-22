import logging

from unittest.mock import MagicMock
from unittest.mock import patch

from nectar_tools.audit import base
from nectar_tools import test


LOG = logging.getLogger(__name__)


class RepairAuditor(base.Auditor):
    def __init__(self, dry_run=False):
        super().__init__(None, dry_run=dry_run)

    def setup_clients(self):
        pass


class AuditorTests(test.TestCase):
    def test_correct_logger(self):
        auditor = RepairAuditor()
        self.assertEqual(LOG, auditor.repair_log)

    def test_repair_dry_run(self):
        auditor = RepairAuditor(dry_run=True)
        mock_action = MagicMock()
        with patch.object(auditor, 'repair_log') as mock_log:
            auditor.repair("repair 1", mock_action)
            mock_action.assert_not_called()
            mock_log.info.assert_called_once()

    def test_repair_no_dry_run(self):
        auditor = RepairAuditor(dry_run=False)
        mock_action = MagicMock()
        with patch.object(auditor, 'repair_log') as mock_log:
            auditor.repair("repair 1", mock_action)
            mock_action.assert_called()
            mock_log.info.assert_called_once()
