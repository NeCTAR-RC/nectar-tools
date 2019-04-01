import sys

from nectar_tools import cmd_base


class ProjectAuditor(cmd_base.CmdBase):

    def add_args(self):
        super(ProjectAuditor, self).add_args()
        self.parser.description = 'Project auditor'
        project_group = self.parser.add_mutually_exclusive_group(required=True)
        project_group.add_argument('--all', action='store_true',
                            help='Run over all projects')
        project_group.add_argument('-p', '--project-id',
                            help='Project ID to process')

    def run_audits(self):
        manager = self.get_manager()
        projects = []
        if self.args.project_id:
            project = self.k_client.projects.get(self.args.project_id)
            projects.append(project)
        elif self.args.all:
            projects = self.k_client.projects.list(enabled=True)
            projects.sort(key=lambda p: p.name.split('-')[-1].zfill(5))
        else:
            print("Must specify either project_id or all argument")
            return sys.exit(1)

        for project in projects:
            if self.is_valid_project(project):
                auditor = manager(ks_session=self.session, project=project)
                auditor.run_all()
