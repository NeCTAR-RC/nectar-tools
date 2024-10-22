#!/usr/bin/env python

import logging
import prettytable

from nectar_tools import auth
from nectar_tools import cmd_base
from nectar_tools import config

from nectar_tools.expiry import expiry_states
from nectar_tools.expiry.manager import jupyterhub as expirer


CONF = config.CONFIG
LOG = logging.getLogger(__name__)

# TODO(andy) Copied from expirer, but should be imported consts
STATUS_KEY = 'nectar.org.au/expiry_status'
NEXT_STEP_KEY = 'nectar.org.au/expiry_next_step'
TICKET_ID_KEY = 'nectar.org.au/expiry_ticket_id'
UPDATED_AT_KEY = 'nectar.org.au/expiry_updated_at'


class JupyterHubVolumeExpiryCmd(cmd_base.CmdBase):
    def __init__(self):
        super().__init__(log_filename='jupyterhub-volume-expiry.log')

        self.kube_client = auth.get_kube_client()
        self.kube_ns = CONF.kubernetes_client.namespace

        pvcs = []
        if self.args.pvc_id:
            pvc = self.kube_client.read_namespaced_persistent_volume_claim(
                self.args.pvc_id, self.kube_ns
            )
            pvcs.append(pvc)
        elif self.args.all:
            pvcs = self.kube_client.list_namespaced_persistent_volume_claim(
                self.kube_ns, label_selector='hub.jupyter.org/username'
            ).items
        else:
            LOG.error("Need to provide PVC name(s) or use option --all")
        self.pvcs = pvcs

    @staticmethod
    def valid_pvc(pvc):
        # TODO(andy) Check if mounted?
        return True

    def print_status(self):
        pt = prettytable.PrettyTable(
            [
                'Name',
                'Last Active',
                'Expiry Status',
                'Expiry Next Step',
                'Ticket ID',
            ]
        )
        pt.align = 'l'
        for pvc in self.pvcs:
            if self.valid_pvc(pvc):
                ex = self.get_expirer(pvc)
                last_active_date = ex.get_last_active_date()
                pt.add_row(
                    [
                        pvc.metadata.name,
                        last_active_date.strftime("%Y-%m-%d"),
                        self._get_metadata(pvc, STATUS_KEY),
                        self._get_metadata(pvc, NEXT_STEP_KEY),
                        self._get_metadata(pvc, TICKET_ID_KEY),
                    ]
                )
        print(pt)

    def get_expirer(self, pvc):
        return expirer.JupyterHubVolumeExpirer(
            pvc=pvc, dry_run=self.dry_run, force_delete=self.args.force_delete
        )

    @staticmethod
    def _get_metadata(pvc, key, default=None):
        # return None if value is an empty string or 0
        return pvc.metadata.annotations.get(key, default) or default

    def _set_metadata(self, pvc, key, value):
        body = {'metadata': {'annotations': {key: value}}}
        self.kube_client.patch_namespaced_persistent_volume_claim(
            pvc.metadata.name, self.kube_ns, body=body
        )

    def add_args(self):
        super().add_args()
        self.parser.description = 'Manage JupyterHub PVCs (Volumes)'
        pvc_group = self.parser.add_mutually_exclusive_group()
        pvc_group.add_argument(
            '-p', '--pvc-id', help='PVC to process (Kubernetes name)'
        )
        pvc_group.add_argument(
            '--all', action='store_true', help='Run over all PVCs'
        )
        self.parser.add_argument(
            '-l',
            '--limit',
            type=int,
            default=0,
            help='Only process this many \
                                 eligible PVCs',
        )
        self.parser.add_argument(
            '-o',
            '--offset',
            type=int,
            default=None,
            help='Skip this many PVCs \
                                 before processing',
        )
        self.parser.add_argument(
            '-s',
            '--status',
            action='store_true',
            help='Report current status of each PVC',
        )
        self.parser.add_argument(
            '-a',
            '--set-admin',
            action='store_true',
            help='Mark a list of PVCs as admins',
        )
        self.parser.add_argument(
            '--force-delete',
            action='store_true',
            help="Delete an pvc no matter what state \
                                 it's in",
        )

    def set_admin(self):
        """Set status to admin for specified list of PVCs."""
        for pvc in self.pvcs:
            status = self._get_metadata(pvc, STATUS_KEY)
            if status == expiry_states.ADMIN:
                LOG.error("PVC %s is already admin", pvc.metadata.name)
            else:
                if self.dry_run:
                    LOG.info(
                        "Would set status admin for PVC %s (dry run)",
                        pvc.metadata.name,
                    )
                else:
                    LOG.debug("Setting status admin for %s", pvc.metadata.name)
                    self._set_metadata(pvc, STATUS_KEY, expiry_states.ADMIN)

    def process_pvcs(self):
        LOG.info("Processing JupyterHub PVCs")

        limit = self.args.limit
        offset = self.args.offset
        offset_count = 0
        processed = 0

        for pvc in self.pvcs:
            if self.valid_pvc(pvc):
                offset_count += 1
                if offset is None or offset_count > offset:
                    try:
                        LOG.debug("------------------")
                        ex = self.get_expirer(pvc)
                        if ex.process():
                            processed += 1
                    except Exception:
                        LOG.exception(
                            'Exception processing JupyterHub PVC %s',
                            pvc.metadata.name,
                        )
                if limit > 0 and processed >= limit:
                    break
        LOG.info("Processed %s PVCs", processed)
        return processed


def main():
    cmd = JupyterHubVolumeExpiryCmd()
    if cmd.args.status:
        cmd.print_status()
        return
    if cmd.args.set_admin:
        cmd.set_admin()
        return
    cmd.process_pvcs()


if __name__ == '__main__':
    main()
