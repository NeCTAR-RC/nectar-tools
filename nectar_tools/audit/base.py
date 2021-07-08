import logging

from nectar_tools import auth


LOG = logging.getLogger(__name__)


class Auditor(object):

    # public methods that are not "checks"
    BASE_METHODS = ['setup_clients', 'run_all', 'repair']

    def __init__(self, ks_session, dry_run=True):
        self.ks_session = ks_session
        self.repair_log = logging.getLogger(self.__class__.__name__)
        self.dry_run = dry_run
        self.setup_clients()

    def setup_clients(self):
        self.sdk_client = auth.get_openstacksdk(sess=self.ks_session)

    def run_all(self, list_not_run=False, **kwargs):
        public_method_names = [method for method in dir(self)
                               if callable(getattr(self, method))
                               if not method.startswith('_')
                               and method not in self.BASE_METHODS]
        for method in public_method_names:
            if list_not_run:
                path = "%s:%s.%s" % (type(self).__module__,
                                     type(self).__name__,
                                     method)
                print(path)
                continue
            LOG.debug("Starting %s", method)
            try:
                getattr(self, method)(**kwargs)
            except Exception as e:
                LOG.exception(e)
            LOG.debug("Finished %s", method)

    def repair(self, action, message, *args, **kwargs):
        if self.dry_run:
            self.repair_log.info("Repair (skipped): " + message,
                                 *args, **kwargs)
        else:
            action()
            self.repair_log.info("Repair: " + message, *args, **kwargs)
