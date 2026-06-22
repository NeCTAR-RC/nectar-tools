from nectar_tools.audit.cmd import base
from nectar_tools import utils


class ProjectAuditorCmd(base.AuditCmdBase):
    def add_args(self):
        super().add_args()
        self.parser.description = 'Project auditor'
        project_group = self.parser.add_mutually_exclusive_group(required=True)
        project_group.add_argument(
            '--all', action='store_true', help='Run over all projects'
        )
        project_group.add_argument(
            '-p', '--project-id', help='Project ID to process'
        )
        self.parser.add_argument(
            '--include-disabled',
            action='store_true',
            help='Include disabled projects with --all',
        )
        self.parser.add_argument(
            '--domain', default='default', help='Project domain.'
        )

    def _get_projects(self):
        projects = []
        if self.args.project_id:
            project = self.k_client.projects.get(self.args.project_id)
            projects.append(project)
        elif self.args.all and self.args.include_disabled:
            projects = utils.list_resources(
                self.k_client.projects.list, domain=self.args.domain
            )
        elif self.args.all:
            projects = utils.list_resources(
                self.k_client.projects.list,
                enabled=True,
                domain=self.args.domain,
            )

        projects.sort(key=lambda p: p.name.split('-')[-1].zfill(5))
        return projects

    def run_audits(self):
        manager = self.get_manager()
        for project in self._get_projects():
            if self.is_valid_project(project):
                auditor = manager(
                    ks_session=self.session,
                    project=project,
                    dry_run=self.dry_run,
                )
                auditor.run_all(list_not_run=self.list_not_run)

    def run_check(self, check):
        # Project auditors need a project, so the base single-instance
        # mechanism can't be used.  Run the named check over every valid
        # project instead.
        method_str = check.split(':')[1].split('.')[1]
        manager = self.get_manager()
        auditor = None
        with base.slack_context(self):
            for project in self._get_projects():
                if not self.is_valid_project(project):
                    continue
                auditor = manager(
                    ks_session=self.session,
                    project=project,
                    dry_run=self.dry_run,
                    limit=self.limit,
                )
                getattr(auditor, method_str)()
            if auditor is not None:
                auditor.summary()
