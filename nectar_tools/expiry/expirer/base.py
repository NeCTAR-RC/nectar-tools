import datetime
import logging

from nectar_tools import auth
from nectar_tools.expiry import archiver
from nectar_tools.expiry import expiry_states


LOG = logging.getLogger(__name__)

DATE_FORMAT = '%Y-%m-%d'


class Expirer(object):
    def __init__(self, project, ks_session=None, now=datetime.datetime.now(),
                 dry_run=False):
        self.k_client = auth.get_keystone_client(ks_session)
        self.now = now
        self.project = project
        self.dry_run = dry_run
        self.ks_session = ks_session
        self.nova_archiver = archiver.NovaArchiver(project=project,
                                                   ks_session=ks_session,
                                                   dry_run=dry_run)
        self.cinder_archiver = archiver.CinderArchiver(project=project,
                                                       ks_session=ks_session,
                                                       dry_run=dry_run)

    def _update_project(self, **kwargs):
        if not self.dry_run:
            self.k_client.projects.update(self.project.id, **kwargs)
        msg = '%s: Updating %s' % (self.project.id, kwargs)
        LOG.debug(msg)

    def check_archiving_status(self):
        LOG.debug("%s: Checking archive status", self.project.id)
        if self.nova_archiver.is_archive_successful():
            LOG.info("%s: Archive successful", self.project.id)
            self._update_project(expiry_status=expiry_states.ARCHIVED)
        else:
            LOG.debug("%s: Retrying archiving", self.project.id)
            self.archive_project()

    def archive_project(self):
        LOG.info("%s: Archiving project", self.project.id)
        # Archive all resources
        self.nova_archiver.archive_resources()

    def delete_resources(self):
        LOG.info("%s: Deleting resources", self.project.id)
        self.nova_archiver.delete_resources()
