from nectar_tools.audit.cmd import base


class ProjectAuditorCmd(base.AuditCmdBase):

    def add_args(self):
        super(ProjectAuditorCmd, self).add_args()
        self.parser.description = 'Project auditor'
        project_group = self.parser.add_mutually_exclusive_group(required=True)
        project_group.add_argument('--all', action='store_true',
                            help='Run over all projects')
        project_group.add_argument('--include-disabled', action='store_true',
                            help='Include disabled projects with --all')
        project_group.add_argument('-p', '--project-id',
                            help='Project ID to process')
        self.parser.add_argument('--domain', default='default',
                            help='Project domain.')

    def run_audits(self):
        manager = self.get_manager()
        projects = []
        if self.args.project_id:
            project = self.k_client.projects.get(self.args.project_id)
            projects.append(project)
        elif self.args.all and self.args.include_disabled:
            projects = self.k_client.projects.list(domain=self.args.domain)
        elif self.args.all:
            projects = self.k_client.projects.list(enabled=True,
                                                   domain=self.args.domain)

        projects.sort(key=lambda p: p.name.split('-')[-1].zfill(5))

        for project in projects:
            if self.is_valid_project(project):
                auditor = manager(ks_session=self.session, project=project)
                auditor.run_all(list_not_run=self.list_not_run)
