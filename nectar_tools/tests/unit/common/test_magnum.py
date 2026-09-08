from unittest import mock

from nectar_tools.common import magnum
from nectar_tools import test

CONF = test.CONF


def fake_cluster(name='cluster1', stack_id=None, project_id='dummy'):
    cluster = mock.Mock()
    cluster.name = name
    cluster.stack_id = stack_id
    cluster.project_id = project_id
    return cluster


class GetClusterDriverTests(test.TestCase):
    def test_heat_cluster(self):
        cluster = fake_cluster(stack_id='e6fc5721-d20f-4a08-9d4f-8f5e6c9e4f1b')
        self.assertEqual(
            magnum.Driver.HEAT, magnum.get_cluster_driver(cluster)
        )

    def test_capi_cluster(self):
        cluster = fake_cluster(stack_id='cluster1-abc123456789')
        self.assertEqual(
            magnum.Driver.CAPI, magnum.get_cluster_driver(cluster)
        )

    def test_capi_cluster_sanitised_name(self):
        # The CAPI driver lowercases the name and collapses runs of
        # non-alphanumeric characters to '-' before building stack_id
        cluster = fake_cluster(
            name='My_Test  Cluster!', stack_id='my-test-cluster-abc123456789'
        )
        self.assertEqual(
            magnum.Driver.CAPI, magnum.get_cluster_driver(cluster)
        )

    def test_capi_cluster_long_name(self):
        # The sanitised name is truncated to 30 characters
        cluster = fake_cluster(
            name='a' * 40, stack_id='a' * 30 + '-abc123456789'
        )
        self.assertEqual(
            magnum.Driver.CAPI, magnum.get_cluster_driver(cluster)
        )

    def test_no_stack_id(self):
        cluster = fake_cluster(stack_id=None)
        self.assertIsNone(magnum.get_cluster_driver(cluster))

    def test_no_name(self):
        cluster = fake_cluster(name=None, stack_id='cluster1-abc123456789')
        self.assertIsNone(magnum.get_cluster_driver(cluster))

    def test_unrecognised_stack_id(self):
        cluster = fake_cluster(stack_id='not-a-match')
        self.assertIsNone(magnum.get_cluster_driver(cluster))

    def test_stack_id_shares_name_prefix_only(self):
        # A stack_id that merely starts with the cluster name isn't a match
        cluster = fake_cluster(
            name='cluster1', stack_id='cluster10-abc123456789'
        )
        self.assertIsNone(magnum.get_cluster_driver(cluster))


class CapiClusterNamespaceTests(test.TestCase):
    def test_namespace(self):
        cluster = fake_cluster(project_id='0123456789abcdef0123456789abcdef')
        self.assertEqual(
            'magnum-0123456789abcdef0123456789abcdef',
            magnum.capi_cluster_namespace(cluster),
        )

    def test_namespace_prefix(self):
        CONF.set_override('namespace_prefix', 'other', group='capi_client')
        cluster = fake_cluster(project_id='abc123')
        self.assertEqual(
            'other-abc123', magnum.capi_cluster_namespace(cluster)
        )

    def test_namespace_sanitises_project_id(self):
        cluster = fake_cluster(project_id='ABC-123')
        self.assertEqual(
            'magnum-abc123', magnum.capi_cluster_namespace(cluster)
        )
