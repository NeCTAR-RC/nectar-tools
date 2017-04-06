import logging


LOG = logging.getLogger(__name__)


class LogMixin(object):

    def log(self, message, *args, level=logging.INFO):
        extra = {'project_id': self.project.id,
                 'project_name': self.project.name}
        LOG.log(level, message, *args, extra=extra)
