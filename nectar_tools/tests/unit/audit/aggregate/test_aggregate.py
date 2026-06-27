import os
import tempfile

from unittest import mock

from nectar_tools.audit.aggregate import aggregate
from nectar_tools import test


class FakeAggregate:
    def __init__(
        self, name, hosts, availability_zone=None, metadata=None, id=1
    ):
        self.name = name
        self.hosts = hosts
        self.availability_zone = availability_zone
        self.metadata = metadata or {}
        self.id = id


class FakeRP:
    def __init__(self, name, vcpu=True):
        self.name = name
        self._vcpu = vcpu

    def inventories(self):
        return mock.Mock(spec=['VCPU'] if self._vcpu else [])


class FakeFlavor:
    def __init__(self, name, keys=None):
        self.name = name
        self._keys = keys or {}

    def get_keys(self):
        return self._keys


class _Auditor(aggregate.AggregateAuditor):
    """AggregateAuditor with mocked clients for unit testing."""

    def setup_clients(self):
        self.n_client = mock.Mock()
        self.p_client = mock.Mock()
        self.g_client = mock.Mock()
        self.k_client = mock.Mock()
        self._graph = None
        self._project_cache = {}


class AggregateAuditorTests(test.TestCase):
    def _build(
        self, aggregates=None, rps=None, flavors=None, images=None, az='az1'
    ):
        auditor = _Auditor(None, dry_run=True, availability_zone=az)
        auditor.n_client.aggregates.list.return_value = aggregates or []
        auditor.p_client.resource_providers.list.return_value = rps or []
        auditor.n_client.flavors.list.return_value = flavors or []
        auditor.g_client.images.list.return_value = images or []
        return auditor

    def _messages(self, mock_log):
        return [c.args[0] for c in mock_log.warning.call_args_list]

    # -- AZ scoping ---------------------------------------------------------

    def test_az_scope_includes_shared_metadata_aggregate(self):
        az_agg = FakeAggregate(
            'zone-agg', ['h1', 'h2'], availability_zone='az1'
        )
        meta_agg = FakeAggregate('gpu', ['h1'], metadata={'special': 'true'})
        other = FakeAggregate('other-zone', ['h9'], availability_zone='az2')
        auditor = self._build(aggregates=[az_agg, meta_agg, other])
        graph = auditor._build_graph()
        names = {a.name for a in graph['aggregates']}
        self.assertEqual({'zone-agg', 'gpu'}, names)

    # -- hosts_without_aggregate -------------------------------------------

    def test_hosts_without_aggregate_flags_orphan(self):
        # h1 is a member of an aggregate; h2 has an RP but no aggregate;
        # h3 is not a compute node (no VCPU) so it is ignored.
        zone = FakeAggregate('zone', ['h1'], availability_zone='az1')
        auditor = self._build(
            aggregates=[zone],
            rps=[FakeRP('h1'), FakeRP('h2'), FakeRP('h3', vcpu=False)],
        )
        with mock.patch.object(aggregate, 'LOG') as mock_log:
            auditor.hosts_without_aggregate()
            messages = self._messages(mock_log)
            self.assertEqual(1, len(messages))
            self.assertIn('Host %s has a resource provider', messages[0])
            warned_host = mock_log.warning.call_args_list[0].args[1]
            self.assertEqual('h2', warned_host)

    def test_hosts_without_aggregate_silent_when_all_members(self):
        zone = FakeAggregate('zone', ['h1', 'h2'], availability_zone='az1')
        auditor = self._build(
            aggregates=[zone],
            rps=[FakeRP('h1'), FakeRP('h2')],
        )
        with mock.patch.object(aggregate, 'LOG') as mock_log:
            auditor.hosts_without_aggregate()
            self.assertEqual(0, mock_log.warning.call_count)

    # -- orphaned_aggregate_properties -------------------------------------

    def test_orphan_property_warns_when_unused(self):
        agg = FakeAggregate(
            'gpu',
            ['h1'],
            availability_zone='az1',
            metadata={'special-hw': 'true'},
        )
        auditor = self._build(aggregates=[agg], flavors=[FakeFlavor('m3')])
        with mock.patch.object(aggregate, 'LOG') as mock_log:
            auditor.orphaned_aggregate_properties()
            self.assertEqual(1, mock_log.warning.call_count)

    def test_orphan_property_silent_when_flavor_matches(self):
        agg = FakeAggregate(
            'gpu',
            ['h1'],
            availability_zone='az1',
            metadata={'special-hw': 'true'},
        )
        flavor = FakeFlavor('gpu-flavor', {'special-hw': 'true'})
        auditor = self._build(aggregates=[agg], flavors=[flavor])
        with mock.patch.object(aggregate, 'LOG') as mock_log:
            auditor.orphaned_aggregate_properties()
            self.assertEqual(0, mock_log.warning.call_count)

    def test_orphan_property_matches_namespaced_extra_spec(self):
        agg = FakeAggregate(
            'gpu',
            ['h1'],
            availability_zone='az1',
            metadata={'special-hw': 'true'},
        )
        flavor = FakeFlavor(
            'gpu', {'aggregate_instance_extra_specs:special-hw': 'true'}
        )
        auditor = self._build(aggregates=[agg], flavors=[flavor])
        with mock.patch.object(aggregate, 'LOG') as mock_log:
            auditor.orphaned_aggregate_properties()
            self.assertEqual(0, mock_log.warning.call_count)

    def test_orphan_trait_silent_when_image_matches(self):
        agg = FakeAggregate(
            'gpu',
            ['h1'],
            availability_zone='az1',
            metadata={'trait:CUSTOM_GPU': 'required'},
        )
        image = {'name': 'gpu-image', 'trait:CUSTOM_GPU': 'required'}
        auditor = self._build(aggregates=[agg], images=[image])
        with mock.patch.object(aggregate, 'LOG') as mock_log:
            auditor.orphaned_aggregate_properties()
            self.assertEqual(0, mock_log.warning.call_count)

    def test_orphan_instance_type_silent_when_flavor_name_matches(self):
        agg = FakeAggregate(
            'aff',
            ['h1'],
            availability_zone='az1',
            metadata={'instance_type': 'm3.large,m3.xlarge'},
        )
        auditor = self._build(
            aggregates=[agg], flavors=[FakeFlavor('m3.large')]
        )
        with mock.patch.object(aggregate, 'LOG') as mock_log:
            auditor.orphaned_aggregate_properties()
            self.assertEqual(0, mock_log.warning.call_count)

    def test_orphan_skips_tenant_keys(self):
        agg = FakeAggregate(
            't',
            ['h1'],
            availability_zone='az1',
            metadata={'filter_tenant_id0': 'abc'},
        )
        auditor = self._build(aggregates=[agg])
        with mock.patch.object(aggregate, 'LOG') as mock_log:
            auditor.orphaned_aggregate_properties()
            self.assertEqual(0, mock_log.warning.call_count)

    # -- metadata_syntax ----------------------------------------------------

    def test_syntax_comma_in_numbered_tenant_key(self):
        agg = FakeAggregate(
            't',
            ['h1'],
            availability_zone='az1',
            metadata={'filter_tenant_id0': 'abc,def'},
        )
        auditor = self._build(aggregates=[agg])
        with mock.patch.object(aggregate, 'LOG') as mock_log:
            auditor.metadata_syntax()
            messages = self._messages(mock_log)
            self.assertTrue(
                any('comma-separated value' in m for m in messages)
            )

    def test_syntax_numbered_nectar_key(self):
        agg = FakeAggregate(
            't',
            ['h1'],
            availability_zone='az1',
            metadata={'nectar:filter_tenant_id1': 'abc'},
        )
        auditor = self._build(aggregates=[agg])
        with mock.patch.object(aggregate, 'LOG') as mock_log:
            auditor.metadata_syntax()
            messages = self._messages(mock_log)
            self.assertTrue(any('uses a single' in m for m in messages))

    def test_syntax_bare_tenant_key(self):
        agg = FakeAggregate(
            't',
            ['h1'],
            availability_zone='az1',
            metadata={'filter_tenant_id': 'abc'},
        )
        auditor = self._build(aggregates=[agg])
        with mock.patch.object(aggregate, 'LOG') as mock_log:
            auditor.metadata_syntax()
            messages = self._messages(mock_log)
            self.assertTrue(any('no numeric suffix' in m for m in messages))

    def test_syntax_too_many_nectar_tenants(self):
        ids = ','.join(f'p{i}' for i in range(8))
        agg = FakeAggregate(
            't',
            ['h1'],
            availability_zone='az1',
            metadata={'nectar:filter_tenant_id': ids},
        )
        auditor = self._build(aggregates=[agg])
        with mock.patch.object(aggregate, 'LOG') as mock_log:
            auditor.metadata_syntax()
            messages = self._messages(mock_log)
            self.assertTrue(any('limit is' in m for m in messages))

    def test_syntax_trait_not_required(self):
        agg = FakeAggregate(
            'gpu',
            ['h1'],
            availability_zone='az1',
            metadata={'trait:CUSTOM_GPU': 'yes'},
        )
        auditor = self._build(aggregates=[agg])
        with mock.patch.object(aggregate, 'LOG') as mock_log:
            auditor.metadata_syntax()
            messages = self._messages(mock_log)
            self.assertTrue(
                any("must be set to 'required'" in m for m in messages)
            )

    def test_syntax_valid_tenant_keys_silent(self):
        agg = FakeAggregate(
            't',
            ['h1'],
            availability_zone='az1',
            metadata={
                'filter_tenant_id0': 'abc',
                'nectar:filter_tenant_id': 'abc,def',
            },
        )
        auditor = self._build(aggregates=[agg])
        # projects.get returns a truthy mock -> projects "exist"
        with mock.patch.object(aggregate, 'LOG') as mock_log:
            auditor.metadata_syntax()
            self.assertEqual(0, mock_log.warning.call_count)

    def test_syntax_unknown_project_warns(self):
        agg = FakeAggregate(
            't',
            ['h1'],
            availability_zone='az1',
            metadata={'filter_tenant_id0': 'missing'},
        )
        auditor = self._build(aggregates=[agg])
        auditor.k_client.projects.get.side_effect = Exception('not found')
        with mock.patch.object(aggregate, 'LOG') as mock_log:
            auditor.metadata_syntax()
            messages = self._messages(mock_log)
            self.assertTrue(any('does not' in m for m in messages))

    # -- report -------------------------------------------------------------

    def test_generate_report_both_formats(self):
        agg = FakeAggregate(
            'gpu',
            ['h1'],
            availability_zone='az1',
            metadata={'special-hw': 'true'},
        )
        flavor = FakeFlavor('gpu', {'special-hw': 'true'})
        auditor = self._build(aggregates=[agg], flavors=[flavor])
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, 'agg')
            written = auditor.generate_report(out, fmt='both')
            self.assertEqual(2, len(written))
            for path in written:
                self.assertTrue(os.path.exists(path))
                self.assertTrue(os.path.getsize(path) > 0)

    def test_generate_report_markdown(self):
        agg = FakeAggregate(
            'gpu',
            ['h1'],
            availability_zone='az1',
            metadata={'special-hw': 'true'},
        )
        flavor = FakeFlavor('gpu', {'special-hw': 'true'})
        auditor = self._build(aggregates=[agg], flavors=[flavor])
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, 'agg.md')
            written = auditor.generate_report(out, fmt='md')
            self.assertEqual([out], written)
            with open(out, encoding='utf-8') as fh:
                content = fh.read()
            self.assertIn('mermaid', content)
            self.assertIn('gpu', content)
