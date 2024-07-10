import datetime
import logging

import requests

from nectar_tools import auth
from nectar_tools import config

from nectar_tools.expiry import archiver
from nectar_tools.expiry import expirer as base
from nectar_tools.expiry import expiry_states
from nectar_tools.expiry import notifier as expiry_notifier


CONF = config.CONFIG
LOG = logging.getLogger(__name__)

ONE_MONTH_IN_DAYS = 31
SIX_MONTHS_IN_DAYS = 180


class JupyterHubVolumeExpirer(base.Expirer):

    STATUS_KEY = 'nectar.org.au/expiry_status'
    NEXT_STEP_KEY = 'nectar.org.au/expiry_next_step'
    TICKET_ID_KEY = 'nectar.org.au/expiry_ticket_id'
    UPDATED_AT_KEY = 'nectar.org.au/expiry_updated_at'

    EVENT_PREFIX = 'expiry.jupyterhub.volume'

    def __init__(self, pvc, ks_session=None, dry_run=False,
                 force_delete=False):

        patched_pvc = pvc
        patched_pvc.id = pvc.metadata.name

        notifier = expiry_notifier.ExpiryNotifier(
            resource_type='jupyterhub_volume',
            resource=patched_pvc,
            template_dir='jupyterhub_volume',
            group_id=CONF.freshdesk.jupyterhub_group,
            subject='ARDC Nectar Jupyter Notebook Service volume expiry',
            ks_session=None, dry_run=dry_run,
            ticket_id_key=self.TICKET_ID_KEY)

        self.archiver = archiver.JupyterHubVolumeArchiver(
            patched_pvc, ks_session=ks_session, dry_run=dry_run)

        self.pvc = patched_pvc
        self.id = self.pvc.metadata.name
        self.username = self.pvc.metadata.annotations.get(
            'hub.jupyter.org/username')
        self.force_delete = force_delete
        self.kube_client = auth.get_kube_client()
        self.kube_ns = CONF.kubernetes_client.namespace

        super().__init__('jupyterhub_volume', self.pvc, notifier,
                         ks_session, dry_run)

    def has_metadata(self, key):
        if key in self.pvc.metadata.annotations:
            return True
        return False

    def get_metadata(self, key, default=None):
        # return None if value is an empty string or 0
        return self.pvc.metadata.annotations.get(key, default) or default

    def set_metadata(self, key, value):
        self.pvc.metadata.annotations[key] = value

    def _update_object(self, **kwargs):
        # Update the PVC via the k8s API
        body = {'metadata': {'annotations': kwargs}}
        self.kube_client.patch_namespaced_persistent_volume_claim(
            self.id, self.kube_ns, body=body)

    def _get_recipients(self):
        return self.username, []

    def _get_notification_context(self):
        context = {
            'name': self.username,
            'expiry_date': self.make_next_step_date(self.now),
        }
        return context

    def get_status(self):
        status = self.get_metadata(self.STATUS_KEY)
        if not status:
            status = expiry_states.ACTIVE
            self.set_metadata(self.STATUS_KEY, status)
        return status

    def get_next_step_date(self):
        expiry_next_step = self.get_metadata(self.NEXT_STEP_KEY)
        if expiry_next_step:
            try:
                return datetime.datetime.strptime(
                    expiry_next_step, base.DATE_FORMAT)
            except ValueError:
                LOG.error('%s: Invalid %s date: %s',
                          self.pvc.id, self.NEXT_STEP_KEY, expiry_next_step)
        return None

    @staticmethod
    def _jupyterhub_api(path):
        url = CONF.jupyterhub.api_url + '/' + path
        token = CONF.jupyterhub.token
        r = requests.get(url, headers={'Authorization': 'token ' + token})
        r.raise_for_status()
        return r.json()

    def get_last_active_date(self):
        hubuser = self._jupyterhub_api('/users/' + self.username)
        # The timestamp given from JHub can vary, so we just strip away
        # everything except the date part
        ts = hubuser.get('last_activity').split('T')[0]
        last_activity = datetime.datetime.strptime(ts, '%Y-%m-%d')
        return last_activity

    def get_warning_date(self):
        last_activity = self.get_last_active_date()
        return last_activity + datetime.timedelta(days=SIX_MONTHS_IN_DAYS)

    def stop_resource(self):
        # Just one day is enough
        expiry_date = self.make_next_step_date(self.now, days=1)
        update_kwargs = {self.STATUS_KEY: expiry_states.STOPPED,
                         self.NEXT_STEP_KEY: expiry_date}
        with base.ResourceRollback(self):
            self._update_resource(**update_kwargs)
            self._send_notification('stop')
        self.send_event('stop')

    def revert_expiry(self):
        status = self.get_status()
        if status == expiry_states.ACTIVE:
            return
        LOG.info("Reverting PVC expiry: %s", self.id)
        self.finish_expiry(message='JupyterHub PVC expiry process was reset.')

    def should_process(self):
        expiry_status = self.get_status()
        last_active = self.get_last_active_date()

        # Warning date for this is always last active date + 6 months
        if self.ready_for_warning():
            LOG.debug("User is ready for warning. Last active %s", last_active)
            return True

        # If the expiry process has started, but the user has since logged
        # in again within the last month, reset the expiry status
        if expiry_status != expiry_states.ACTIVE:
            one_month_ago = self.now - datetime.timedelta(
                days=ONE_MONTH_IN_DAYS)
            is_recently_active = last_active > one_month_ago
            if is_recently_active:
                LOG.debug("User has recently been active: %s", last_active)
                self.revert_expiry()

        return False

    def process(self):
        expiry_status = self.get_status()

        if self.force_delete:
            LOG.info("Force deleting PVC: %s", self.id)
            self.delete_resources(force=True)
            return True

        if not self.should_process():
            return False

        LOG.debug("Processing PVC: %s, Status: %s, Next Step: %s",
                  self.id, expiry_status, self.get_next_step_date())

        if expiry_status == expiry_states.ACTIVE:
            self.send_warning()
            return True
        elif expiry_status == expiry_states.WARNING:
            if self.at_next_step():
                self.stop_resource()
                return True
            return False
        elif expiry_status == expiry_states.STOPPED:
            if self.at_next_step():
                self.finish_expiry()
                self.delete_resources(force=True)
                return True
            return False
        else:
            LOG.warning("JupyterHub PVC %s: Unspecified status %s",
                        self.id, expiry_status)
            return False
