import logging


from nectar_tools.audit.identity import base
from nectar_tools.expiry import archiver


LOG = logging.getLogger(__name__)


class ProjectAuditor(base.IdentityAuditor):

    def check_deleted_no_instances(self):
        projects = self.k_client.projects.list()
        for project in projects:
            status = getattr(project, 'expiry_status', None)
            if status == 'deleted':
                nova_archiver = archiver.NovaArchiver(
                    project, ks_session=self.ks_session)
                instances = nova_archiver._all_instances()
                if instances:
                    LOG.error("Deleted project %s has %s running instances",
                              project.name, len(instances))
