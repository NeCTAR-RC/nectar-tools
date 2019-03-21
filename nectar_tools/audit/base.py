import logging


LOG = logging.getLogger(__name__)


class Auditor(object):

    def run_all(self):
        public_method_names = [method for method in dir(self)
                               if callable(getattr(self, method))
                               if not method.startswith('_')]
        for method in public_method_names:
            if method != 'run_all':
                LOG.debug("Starting %s", method)
                try:
                    getattr(self, method)()
                except Exception as e:
                    LOG.exception(e)
                LOG.debug("Finished %s", method)
