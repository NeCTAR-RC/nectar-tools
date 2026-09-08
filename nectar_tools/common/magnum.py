from enum import Enum
import re

from oslo_utils import uuidutils

from nectar_tools import config

CONF = config.CONF

# magnum-capi-helm truncates the sanitised cluster name to this many
# characters when it builds stack_id (see _generate_release_name in
# magnum_capi_helm/driver.py).
CAPI_RELEASE_NAME_LEN = 30


class Driver(Enum):
    HEAT = 'k8s_fedora_coreos_v1'
    CAPI = 'k8s_capi_helm_v1'


def _sanitized_name(name):
    """Mirror magnum_capi_helm.driver_utils.sanitized_name"""
    return re.sub('[^a-z0-9]+', '-', name.lower()).strip('-')


def get_cluster_driver(cluster):
    """Best-effort magnum driver detection for a cluster.

    Magnum doesn't expose the driver directly, but it can be inferred from
    the shape of stack_id: HEAT stack_ids are a plain UUID, while the CAPI
    helm driver builds stack_id as ``<sanitised name[:30]>-<12 char id>``,
    where the name is lowercased and runs of non-alphanumeric characters
    are collapsed to ``-``.
    Returns None if stack_id isn't set yet or doesn't match either shape.
    """
    stack_id = getattr(cluster, 'stack_id', None)
    if not stack_id:
        return None
    if uuidutils.is_uuid_like(stack_id):
        return Driver.HEAT
    name = getattr(cluster, 'name', None)
    if name is not None:
        prefix = _sanitized_name(name)[:CAPI_RELEASE_NAME_LEN]
        if stack_id.startswith(f'{prefix}-'):
            return Driver.CAPI
    return None


def capi_cluster_namespace(cluster):
    """Namespace holding the cluster's CAPI resources.

    Mirrors magnum_capi_helm.driver_utils.cluster_namespace; the prefix
    must match magnum's [capi_helm]/namespace_prefix.
    """
    project_id = re.sub('[^a-z0-9]', '', cluster.project_id.lower())
    return f'{CONF.capi_client.namespace_prefix}-{project_id}'
