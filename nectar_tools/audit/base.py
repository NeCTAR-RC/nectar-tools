import logging

from nectar_tools import auth


LOG = logging.getLogger(__name__)

REPAIR_COUNT = 0


class Auditor(object):

    # public methods that are not "checks"
    BASE_METHODS = ['setup_clients', 'run_all', 'repair', 'summary']

    def __init__(self, ks_session, dry_run=True):
        self.ks_session = ks_session
        self.dry_run = dry_run

        # This should correspond to the LOG that the actual auditor
        # uses for its diagnostics.
        self.repair_log = logging.getLogger(self.__class__.__module__)

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

        if not list_not_run:
            self.summary()

    def summary(self):
        if self.dry_run:
            LOG.info(
                f"Found {REPAIR_COUNT} items to repair, run with -y to action")
        else:
            LOG.info(f"Repaired {REPAIR_COUNT} items")

    def repair(self, message, action):
        global REPAIR_COUNT
        REPAIR_COUNT += 1

        if self.dry_run:
            self.repair_log.info("Repair (noop): " + message)
        else:
            action()
            self.repair_log.info("Repair: " + message)
