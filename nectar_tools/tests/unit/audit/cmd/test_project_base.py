from unittest import mock

from nectar_tools.audit.cmd import base as cmd_base
from nectar_tools.audit.cmd import project
from nectar_tools import test
from nectar_tools.tests import fakes


CHECK = (
    'nectar_tools.audit.projects.allocation:'
    'ProjectAllocationAuditor.check_deleted_resources'
)


class AuditCmdBaseTests(test.TestCase):
    def _make_cmd(self):
        cmd = cmd_base.AuditCmdBase.__new__(cmd_base.AuditCmdBase)
        cmd.session = mock.Mock()
        cmd.dry_run = True
        cmd.limit = 0
        return cmd

    def test_run_check_single_instance(self):
        cmd = self._make_cmd()
        auditor = mock.Mock()
        auditor_class = mock.Mock(return_value=auditor)
        fake_module = mock.Mock(FakeAuditor=auditor_class)

        with mock.patch(
            'nectar_tools.audit.cmd.base.importlib.import_module',
            return_value=fake_module,
        ):
            cmd.run_check('some.module:FakeAuditor.my_check')

        auditor_class.assert_called_once_with(
            ks_session=cmd.session, dry_run=True, limit=0
        )
        auditor.my_check.assert_called_once_with()
        auditor.summary.assert_called_once_with()


class ProjectAuditorCmdTests(test.TestCase):
    def _make_cmd(self, dry_run=False, limit=0):
        cmd = project.ProjectAllocationAuditorCmd.__new__(
            project.ProjectAllocationAuditorCmd
        )
        cmd.session = mock.Mock()
        cmd.dry_run = dry_run
        cmd.limit = limit
        cmd.list_not_run = False
        return cmd

    def test_run_check_runs_named_check_per_valid_project(self):
        # pt-2 is a trial project, so it is not valid for the allocation
        # auditor and must be skipped.
        p1 = fakes.FakeProject(id='1', name='proj-1')
        p2 = fakes.FakeProject(id='2', name='pt-2')
        p3 = fakes.FakeProject(id='3', name='proj-3')

        cmd = self._make_cmd(limit=5)
        built = []

        def make_auditor(**kwargs):
            auditor = mock.Mock()
            built.append((kwargs, auditor))
            return auditor

        manager = mock.Mock(side_effect=make_auditor)

        with (
            mock.patch.object(cmd, '_get_projects', return_value=[p1, p2, p3]),
            mock.patch.object(cmd, 'get_manager', return_value=manager),
        ):
            cmd.run_check(CHECK)

        # Only the two valid allocation projects get an auditor.
        self.assertEqual([p1, p3], [kw['project'] for kw, _ in built])
        for kwargs, auditor in built:
            self.assertEqual(cmd.session, kwargs['ks_session'])
            self.assertEqual(5, kwargs['limit'])
            auditor.check_deleted_resources.assert_called_once_with()
        # Summary is emitted once, on the last auditor built.
        built[-1][1].summary.assert_called_once_with()

    def test_run_check_no_valid_projects(self):
        cmd = self._make_cmd()
        manager = mock.Mock()

        with (
            mock.patch.object(cmd, '_get_projects', return_value=[]),
            mock.patch.object(cmd, 'get_manager', return_value=manager),
        ):
            # Should be a no-op and not raise (no auditor to summarise).
            cmd.run_check(CHECK)

        manager.assert_not_called()
