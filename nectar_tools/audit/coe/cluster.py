import logging

from nectar_tools.audit import base
from nectar_tools import auth


LOG = logging.getLogger(__name__)


class ClusterAuditor(base.Auditor):

    def __init__(self, *args, **kwargs):
        kwargs['log'] = LOG
        super().__init__(*args, **kwargs)

    def setup_clients(self):
        super().setup_clients()
        self.client = auth.get_magnum_client(sess=self.ks_session)
        self.k_client = auth.get_keystone_client(sess=self.ks_session)

    def _delete_cluster(self, cluster):
        self.repair(lambda: self.client.clusters.delete(cluster.uuid),
                    "%s: - Deleting cluster", cluster.uuid)

    def check_status(self):
        clusters = self.client.clusters.list(detail=True)
        for cluster in clusters:
            project = self.k_client.projects.get(cluster.project_id)

            if not project.enabled:
                LOG.error("%s - Running cluster of disabled project",
                          cluster.uuid)
                self._delete_cluster(cluster)
            elif cluster.status == 'CREATE_FAILED':
                if ("Quota exceeded for resources" in cluster.status_reason
                        or "VolumeSizeExceedsAvailableQuota"
                        in cluster.status_reason
                        or "Quota has been met for resources"
                        in cluster.status_reason):

                    LOG.warning("%s - CREATE_FAILED due to quota issue",
                                cluster.uuid)
                    self._delete_cluster(cluster)
                else:
                    LOG.warning("%s - CREATE_FAILED %s", cluster.uuid,
                                cluster.status_reason)
            elif cluster.status == 'DELETE_FAILED':
                LOG.warning("%s - in DELETE_FAILED state",
                            cluster.uuid)
                self._delete_cluster(cluster)
