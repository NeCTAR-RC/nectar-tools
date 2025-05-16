from enum import Enum

import logging
from oslo_utils import uuidutils

from nectar_tools.audit import base
from nectar_tools import auth
from nectar_tools.expiry import expiry_states

LOG = logging.getLogger(__name__)


class Driver(Enum):
    HEAT = 'k8s_fedora_coreos_v1'
    CAPI = 'k8s_capi_helm_v1'


class ClusterAuditor(base.Auditor):
    def setup_clients(self):
        super().setup_clients()
        self.openstack = auth.get_openstacksdk(sess=self.ks_session)
        self.client = auth.get_magnum_client(sess=self.ks_session)
        self.k_client = auth.get_keystone_client(sess=self.ks_session)

    def _delete_cluster(self, cluster):
        self.repair(
            f"{cluster.uuid}: - Deleting cluster",
            lambda: self.client.clusters.delete(cluster.uuid),
        )

    # Case: CAPI clusters with a stuck loadbalancer
    def _fix_cluster_loadbalancer(self, cluster):
        stack_name = cluster.stack_id

        # look for loadbalancers belonging to the cluster
        loadbalancers = list(
            self.openstack.load_balancer.load_balancers(
                project_id=cluster.project_id
            )
        )
        loadbalancers = [
            lb for lb in loadbalancers if stack_name in lb['name']
        ]

        for lb in loadbalancers:
            LOG.debug(
                "%s - LoadBalancer %s (%s) exists",
                cluster.uuid,
                lb['id'],
                lb['name'],
            )
            try:
                self.repair(
                    f"{cluster.uuid}: - Deleting loadbalancer",
                    lambda: self.openstack.load_balancer.delete_load_balancer(
                        lb['id'], cascade=True
                    ),
                )
            except Exception as e:
                LOG.error(
                    "%s - Failed to delete loadbalancer %s: %s",
                    cluster.uuid,
                    lb['id'],
                    str(e),
                )

    # Case: CAPI clusters with a stuck network due to orphaned healthmonitor
    def _fix_cluster_network_orphaned_healthmonitor(self, cluster):
        stack_name = cluster.stack_id

        # look for network belonging to the cluster
        networks = list(
            self.openstack.network.networks(project_id=cluster.project_id)
        )
        networks = [n for n in networks if stack_name in n['name']]

        for network in networks:
            LOG.debug(
                "%s - Network %s (%s) exists",
                cluster.uuid,
                network['id'],
                network['name'],
            )
            ports = list(
                self.openstack.network.ports(network_id=network['id'])
            )

            # safety check to make sure network is almost empty
            # ports left should be metadata and healthmonitor
            if len(ports) > 2:
                LOG.debug(
                    "%s - Network %s has too many ports, skipping",
                    cluster.uuid,
                    network['id'],
                )
                continue

            # look for healthmonitor ports
            for port in ports:
                if port['device_owner'] == 'ovn-lb-hm:distributed':
                    self.repair(
                        f"{cluster.uuid}: - Deleting healthmonitor port {port['id']}",
                        lambda: self.openstack.network.delete_port(port['id']),
                    )

    def check_status(self):
        clusters = self.client.clusters.list(detail=True)
        for cluster in clusters:
            project = self.k_client.projects.get(cluster.project_id)

            if getattr(project, 'expiry_status', '') == expiry_states.DELETED:
                LOG.error(
                    "%s - Running cluster of deleted project", cluster.uuid
                )
                self._delete_cluster(cluster)

            elif cluster.status == 'CREATE_FAILED':
                if (
                    "Quota exceeded for resources" in cluster.status_reason
                    or "VolumeSizeExceedsAvailableQuota"
                    in cluster.status_reason
                    or "Quota has been met for resources"
                    in cluster.status_reason
                ):
                    LOG.warning(
                        "%s - CREATE_FAILED due to quota issue", cluster.uuid
                    )
                    self._delete_cluster(cluster)
                else:
                    LOG.info(
                        "%s - CREATE_FAILED %s",
                        cluster.uuid,
                        cluster.status_reason,
                    )
            elif cluster.status == 'DELETE_FAILED':
                LOG.warning("%s - in DELETE_FAILED state", cluster.uuid)
                self._delete_cluster(cluster)

            elif cluster.status == 'DELETE_IN_PROGRESS':
                LOG.warning("%s - in DELETE_IN_PROGRESS state", cluster.uuid)

                # Find the driver of cluster
                # HEAT clusters have uuid for stack_id
                driver = None
                if uuidutils.is_uuid_like(cluster.stack_id):
                    LOG.debug(
                        "%s - Driver is HEAT cluster with stack_id %s",
                        cluster.uuid,
                        cluster.stack_id,
                    )
                    driver = Driver.HEAT
                # CAPI clusters have stack_id like <cluster_name>-XXXXXXXXXXXX
                elif cluster.stack_id.startswith(cluster.name):
                    LOG.debug(
                        "%s - Driver is CAPI cluster with stack_id %s",
                        cluster.uuid,
                        cluster.stack_id,
                    )
                    driver = Driver.CAPI

                if driver == Driver.CAPI:
                    self._fix_cluster_network_orphaned_healthmonitor(cluster)
                    self._fix_cluster_loadbalancer(cluster)

                self._delete_cluster(cluster)
