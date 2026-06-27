import logging
import re

from nectar_tools.audit.aggregate import report
from nectar_tools.audit import base
from nectar_tools import auth


LOG = logging.getLogger(__name__)

# Aggregate metadata keys that Nova owns and that are not routing properties.
RESERVED_KEYS = {'availability_zone'}

# require_tenant_aggregate ("Tenant Isolation with Placement") uses numbered
# keys holding a single project id each: filter_tenant_id0, filter_tenant_id1...
TENANT_NUMBERED_RE = re.compile(r'^filter_tenant_id(\d+)$')
TENANT_BARE_KEY = 'filter_tenant_id'

# NectarAggregateMultiTenancyIsolation uses one key holding a comma-separated
# list of up to NECTAR_MAX_TENANTS project ids.
NECTAR_TENANT_KEY = 'nectar:filter_tenant_id'
NECTAR_TENANT_NUMBERED_RE = re.compile(r'^nectar:filter_tenant_id(\d+)$')
NECTAR_MAX_TENANTS = 7

TRAIT_PREFIX = 'trait:'
INSTANCE_TYPE_KEY = 'instance_type'
# AggregateInstanceExtraSpecsFilter accepts either the bare key or this prefix
# on the flavor side; aggregate metadata always uses the bare key.
EXTRA_SPEC_NAMESPACE = 'aggregate_instance_extra_specs:'


class AggregateAuditor(base.Auditor):
    """Audit host-aggregate routing configuration for one availability zone.

    Strictly read-only: this auditor only lists/gets from the OpenStack APIs
    and never mutates the cloud. Findings are reported via LOG.warning; the
    only thing written is the optional local report file.
    """

    # Keep the report builder public but out of the auto-run check set.
    BASE_METHODS = base.Auditor.BASE_METHODS + ['generate_report']

    def setup_clients(self):
        super().setup_clients()
        self.n_client = auth.get_nova_client(sess=self.ks_session)
        self.p_client = auth.get_placement_client(sess=self.ks_session)
        self.g_client = auth.get_glance_client(sess=self.ks_session)
        self.k_client = auth.get_keystone_client(sess=self.ks_session)
        self._graph = None
        self._project_cache = {}

    # -- data gathering -----------------------------------------------------

    def _get_project(self, project_id):
        """Resolve a project id, caching results. Returns None if not found."""
        if project_id not in self._project_cache:
            try:
                self._project_cache[project_id] = self.k_client.projects.get(
                    project_id
                )
            except Exception:
                self._project_cache[project_id] = None
        return self._project_cache[project_id]

    def _build_graph(self):
        """Gather aggregates/hosts/RPs/flavors/images for the AZ.

        Cached on the instance so the three checks and the report share one
        pass over the APIs.
        """
        if self._graph is not None:
            return self._graph

        az = self.extra_args.get('availability_zone')
        if not az:
            raise ValueError("availability_zone is required")
        all_aggregates = self.n_client.aggregates.list()

        # Hosts belonging to the AZ come from the AZ-defining aggregates.
        az_hosts = set()
        for aggr in all_aggregates:
            if aggr.availability_zone == az:
                az_hosts.update(aggr.hosts or [])

        # In-scope aggregates: the AZ-defining ones plus any plain metadata
        # aggregate that shares a host with them.
        aggregates = []
        for aggr in all_aggregates:
            hosts = set(aggr.hosts or [])
            if aggr.availability_zone == az or (hosts & az_hosts):
                aggregates.append(aggr)
                az_hosts.update(hosts)

        # Every host that is a member of any aggregate (not just in-scope).
        # A host in no aggregate has no availability zone, so the
        # host-without-aggregate check is necessarily AZ-independent.
        all_aggregate_hosts = set()
        for aggr in all_aggregates:
            all_aggregate_hosts.update(aggr.hosts or [])

        # All compute resource providers (hypervisors) in Placement.
        compute_rps = set()
        for rp in self.p_client.resource_providers.list():
            if hasattr(rp.inventories(), 'VCPU'):
                compute_rps.add(rp.name)

        flavors = []
        for flavor in self.n_client.flavors.list(is_public=None):
            flavors.append(
                {'name': flavor.name, 'specs': dict(flavor.get_keys() or {})}
            )

        images = []
        for image in self.g_client.images.list():
            # glance v2 images behave like dicts of their properties.
            images.append(dict(image))

        self._graph = {
            'az': az,
            'aggregates': aggregates,
            'az_hosts': az_hosts,
            'all_aggregate_hosts': all_aggregate_hosts,
            'compute_rps': compute_rps,
            'flavors': flavors,
            'images': images,
        }
        return self._graph

    # -- matching helpers ---------------------------------------------------

    @staticmethod
    def _flavor_matches_spec(flavor, key, value):
        specs = flavor['specs']
        if specs.get(key) == value:
            return True
        return specs.get(EXTRA_SPEC_NAMESPACE + key) == value

    @staticmethod
    def _image_matches_prop(image, key, value):
        return str(image.get(key)) == str(value)

    def _matching_flavors(self, key, value):
        return [
            f['name']
            for f in self._graph['flavors']
            if self._flavor_matches_spec(f, key, value)
        ]

    def _matching_images(self, key, value):
        return [
            img.get('name') or img.get('id')
            for img in self._graph['images']
            if self._image_matches_prop(img, key, value)
        ]

    def _matching_flavor_names(self, names):
        wanted = {n.strip() for n in names if n.strip()}
        return [
            f['name'] for f in self._graph['flavors'] if f['name'] in wanted
        ]

    # -- checks (auto-run) --------------------------------------------------

    def hosts_without_aggregate(self):
        """Conflict 2.1: compute host in Placement but in no aggregate."""
        graph = self._build_graph()
        orphans = graph['compute_rps'] - graph['all_aggregate_hosts']
        for host in sorted(orphans):
            LOG.warning(
                "Host %s has a resource provider but is not a member of any "
                "aggregate (so it has no availability zone)",
                host,
            )

    def orphaned_aggregate_properties(self):
        """Conflict 2.2: aggregate property no flavor/image/project uses."""
        graph = self._build_graph()
        for aggr in graph['aggregates']:
            for key, value in (aggr.metadata or {}).items():
                if key in RESERVED_KEYS:
                    continue
                if self._is_tenant_key(key):
                    # Tenant routing is validated in metadata_syntax().
                    continue
                if key.startswith(TRAIT_PREFIX):
                    used = self._matching_flavors(
                        key, value
                    ) or self._matching_images(key, value)
                elif key == INSTANCE_TYPE_KEY:
                    used = self._matching_flavor_names(value.split(','))
                else:
                    used = self._matching_flavors(
                        key, value
                    ) or self._matching_images(key, value)
                if not used:
                    LOG.warning(
                        "Aggregate %s property %s=%s is orphaned: no flavor "
                        "or image references it",
                        aggr.name,
                        key,
                        value,
                    )

    def metadata_syntax(self):
        """Conflict 2.3: metadata that violates a filter's required syntax."""
        graph = self._build_graph()
        for aggr in graph['aggregates']:
            for key, value in (aggr.metadata or {}).items():
                self._check_key_syntax(aggr, key, value)

    # -- syntax helpers -----------------------------------------------------

    @staticmethod
    def _is_tenant_key(key):
        return (
            key == NECTAR_TENANT_KEY
            or key == TENANT_BARE_KEY
            or TENANT_NUMBERED_RE.match(key)
            or NECTAR_TENANT_NUMBERED_RE.match(key)
        )

    def _check_key_syntax(self, aggr, key, value):
        if key in RESERVED_KEYS:
            return

        if key == NECTAR_TENANT_KEY:
            ids = [v for v in value.split(',') if v.strip()]
            if len(ids) > NECTAR_MAX_TENANTS:
                LOG.warning(
                    "Aggregate %s %s lists %d projects but the limit is %d",
                    aggr.name,
                    key,
                    len(ids),
                    NECTAR_MAX_TENANTS,
                )
            self._check_projects_exist(aggr, key, ids)
            return

        if NECTAR_TENANT_NUMBERED_RE.match(key):
            LOG.warning(
                "Aggregate %s key %s is invalid: NectarAggregateMultiTenancy"
                "Isolation uses a single '%s' key with a comma-separated "
                "list, not numbered keys",
                aggr.name,
                key,
                NECTAR_TENANT_KEY,
            )
            self._check_projects_exist(aggr, key, [value])
            return

        if TENANT_NUMBERED_RE.match(key):
            if ',' in value:
                LOG.warning(
                    "Aggregate %s key %s has a comma-separated value '%s'; "
                    "require_tenant_aggregate uses one project id per "
                    "numbered key. Use '%s' for multiple projects",
                    aggr.name,
                    key,
                    value,
                    NECTAR_TENANT_KEY,
                )
            self._check_projects_exist(aggr, key, value.split(','))
            return

        if key == TENANT_BARE_KEY:
            LOG.warning(
                "Aggregate %s key %s has no numeric suffix; "
                "require_tenant_aggregate expects filter_tenant_id0, "
                "filter_tenant_id1, ...",
                aggr.name,
                key,
            )
            self._check_projects_exist(aggr, key, value.split(','))
            return

        if key.startswith(TRAIT_PREFIX) and value != 'required':
            LOG.warning(
                "Aggregate %s trait %s has value '%s'; traits must be set to "
                "'required'",
                aggr.name,
                key,
                value,
            )

    def _check_projects_exist(self, aggr, key, ids):
        for project_id in ids:
            project_id = project_id.strip()
            if not project_id:
                continue
            if self._get_project(project_id) is None:
                LOG.warning(
                    "Aggregate %s %s references project %s which does not "
                    "exist",
                    aggr.name,
                    key,
                    project_id,
                )

    # -- report (not auto-run) ----------------------------------------------

    def _build_edges(self):
        """Build subject -> aggregate routing edges for the report."""
        graph = self._build_graph()
        edges = []
        for aggr in graph['aggregates']:
            for key, value in (aggr.metadata or {}).items():
                if key in RESERVED_KEYS:
                    continue
                if key == NECTAR_TENANT_KEY or TENANT_NUMBERED_RE.match(key):
                    # Nectar key holds a comma list; numbered keys hold one id.
                    if key == NECTAR_TENANT_KEY:
                        pids = [v.strip() for v in value.split(',')]
                    else:
                        pids = [value.strip()]
                    for pid in pids:
                        if not pid:
                            continue
                        project = self._get_project(pid)
                        name = project.name if project else pid
                        edges.append(
                            {
                                'kind': 'project',
                                'subject': name,
                                'aggregate': aggr.name,
                                'via': key,
                            }
                        )
                elif key == INSTANCE_TYPE_KEY:
                    for fname in self._matching_flavor_names(value.split(',')):
                        edges.append(
                            {
                                'kind': 'flavor',
                                'subject': fname,
                                'aggregate': aggr.name,
                                'via': 'instance_type',
                            }
                        )
                else:
                    for fname in self._matching_flavors(key, value):
                        edges.append(
                            {
                                'kind': 'flavor',
                                'subject': fname,
                                'aggregate': aggr.name,
                                'via': key,
                            }
                        )
                    for iname in self._matching_images(key, value):
                        edges.append(
                            {
                                'kind': 'image',
                                'subject': iname,
                                'aggregate': aggr.name,
                                'via': key,
                            }
                        )

        # De-duplicate identical edges (same subject/aggregate/via).
        seen = set()
        unique = []
        for e in edges:
            ident = (e['kind'], e['subject'], e['aggregate'], e['via'])
            if ident not in seen:
                seen.add(ident)
                unique.append(e)
        return unique

    def _collect_conflicts(self):
        """Re-run the checks capturing their warnings for the report."""
        records = []

        class _Collector(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())

        handler = _Collector()
        logger = logging.getLogger(__name__)
        logger.addHandler(handler)
        try:
            self.hosts_without_aggregate()
            orphans_start = len(records)
            self.orphaned_aggregate_properties()
            orphans_end = len(records)
            self.metadata_syntax()
            syntax_end = len(records)
        finally:
            logger.removeHandler(handler)

        return {
            'hosts_without_aggregate': records[:orphans_start],
            'orphaned_properties': records[orphans_start:orphans_end],
            'metadata_syntax': records[orphans_end:syntax_end],
        }

    def generate_report(self, output_path, fmt='html'):
        """Render the routing relation chart and conflict tables.

        fmt is one of 'html', 'md', or 'both'. Returns the list of files
        written.
        """
        graph = self._build_graph()
        edges = self._build_edges()
        conflicts = self._collect_conflicts()
        return report.render(graph, edges, conflicts, output_path, fmt)
