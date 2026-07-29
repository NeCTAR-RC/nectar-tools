import datetime
from enum import Enum

import logging
from oslo_utils import uuidutils

from nectar_tools.audit import base
from nectar_tools import auth
from nectar_tools import eol
from nectar_tools.expiry import expiry_states

LOG = logging.getLogger(__name__)

# How long before its EOL date a kubernetes version starts being
# reported as a security risk.
EOL_WARNING_DAYS = 60

# Risks are re-reported every run (varroa refreshes the existing risk),
# so a risk only outlives the cluster's exposure by this window once the
# cluster is upgraded or deleted.
EOL_RISK_EXPIRY_DAYS = 7

NEARING_EOL_RISK_TYPE = {
    'name': 'kubernetes-nearing-eol',
    'display_name': 'Kubernetes version nearing end of life',
    'description': 'The Kubernetes version of this cluster is nearing '
    'its end of life. Upgrade the cluster to a supported version.',
}

EOL_RISK_TYPE = {
    'name': 'kubernetes-eol',
    'display_name': 'Kubernetes version end of life',
    'description': 'The Kubernetes version of this cluster has reached '
    'its end of life and no longer receives security updates. Upgrade '
    'the cluster to a supported version.',
}


class Driver(Enum):
    HEAT = 'k8s_fedora_coreos_v1'
    CAPI = 'k8s_capi_helm_v1'


class ClusterAuditor(base.Auditor):
    def setup_clients(self):
        super().setup_clients()
        self.openstack = auth.get_openstacksdk(sess=self.ks_session)
        self.client = auth.get_magnum_client(sess=self.ks_session)
        self.k_client = auth.get_keystone_client(sess=self.ks_session)
        self.varroa_client = auth.get_varroa_client(sess=self.ks_session)
        self._risk_types = None

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

    def check_kubernetes_eol(self):
        kubernetes = eol.Product('kubernetes')
        today = datetime.date.today()

        clusters = self.client.clusters.list(detail=True)
        for cluster in clusters:
            if (
                'DELETE' in cluster.status
                or 'CREATE_IN_PROGRESS' in cluster.status
                or 'CREATE_FAILED' in cluster.status
            ):
                continue
            if not getattr(cluster, 'coe_version', None):
                LOG.info("%s - no coe_version, skipping", cluster.uuid)
                continue
            eol_date = kubernetes.get_eol_date(cluster.coe_version)
            if eol_date is None:
                LOG.warning(
                    "%s - unknown kubernetes release for version %s",
                    cluster.uuid,
                    cluster.coe_version,
                )
                continue
            days_left = (eol_date - today).days
            if days_left < 0:
                risk_type = EOL_RISK_TYPE
            elif days_left <= EOL_WARNING_DAYS:
                risk_type = NEARING_EOL_RISK_TYPE
            else:
                continue
            LOG.info(
                "%s - kubernetes %s EOL on %s",
                cluster.uuid,
                cluster.coe_version,
                eol_date,
            )
            self.repair(
                f"{cluster.uuid}: Creating {risk_type['name']} security risk",
                self._create_security_risk,
                risk_type=risk_type,
                cluster=cluster,
            )

    def _get_or_create_risk_type(self, risk_type):
        if self._risk_types is None:
            self._risk_types = {
                t.name: t
                for t in self.varroa_client.security_risk_types.list()
            }
        existing = self._risk_types.get(risk_type['name'])
        if existing is None:
            existing = self.varroa_client.security_risk_types.create(
                **risk_type
            )
            self._risk_types[existing.name] = existing
        return existing

    def _create_security_risk(self, risk_type, cluster):
        sr_type = self._get_or_create_risk_type(risk_type)
        now = datetime.datetime.now(datetime.timezone.utc)
        expires = now + datetime.timedelta(days=EOL_RISK_EXPIRY_DAYS)
        time_format = '%Y-%m-%dT%H:%M:%S%z'
        self.varroa_client.security_risks.create(
            time=now.strftime(time_format),
            expires=expires.strftime(time_format),
            type_id=sr_type.id,
            project_id=cluster.project_id,
            resource_id=cluster.uuid,
            resource_type='cluster',
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
                # stack_id is derived from cluster name but truncated to 31 chars
                elif cluster.stack_id.startswith(cluster.name[:30]):
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
