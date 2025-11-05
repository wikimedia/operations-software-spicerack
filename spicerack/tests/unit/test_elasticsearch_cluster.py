"""ElasticsearchCluster module test."""

import itertools
import logging
from datetime import datetime, timedelta
from unittest import mock

import pytest
from wmflib.config import load_yaml_config
from wmflib.prometheus import Prometheus

from spicerack.administrative import Reason
from spicerack.apiclient import APIClient, APIClientError
from spicerack.remote import Remote, RemoteHosts
from spicerack.tests import get_fixture_path

try:
    from spicerack import elasticsearch_cluster as ec  # pylint: disable=ungrouped-imports
    from spicerack.elasticsearch_cluster import NodesGroup
except ImportError:
    pass


ELASTICSEARCH_CONFIG = load_yaml_config(get_fixture_path("elasticsearch", "config.yaml"))


def test_create_elasticsearch_clusters():
    """It should return an instance of ElasticsearchCluster."""
    target = ec.create_elasticsearch_clusters(ELASTICSEARCH_CONFIG, "search_eqiad", ["some_core_dc"], None, None)
    assert isinstance(target, ec.ElasticsearchClusters)


def test_create_elasticsearch_clusters_fail():
    """It should throw an ElasticsearchCluster Exception."""
    with pytest.raises(ec.ElasticsearchClusterError, match="No cluster group named search_test"):
        ec.create_elasticsearch_clusters(ELASTICSEARCH_CONFIG, "search_test", ["some_core_dc"], None, None)


def test_start_elasticsearch():
    """Test that start elasticsearch service is called correctly."""
    mocked_remote_hosts = mock.Mock(spec_set=RemoteHosts)
    mocked_remote_hosts.run_sync = mock.Mock(return_value=iter(()))
    elastic_hosts = ec.ElasticsearchHosts(mocked_remote_hosts, None)
    elastic_hosts.start_elasticsearch()
    mocked_remote_hosts.run_sync.assert_called_with("cat /etc/elasticsearch/instances | xargs systemctl start")


def test_stop_elasticsearch():
    """Test that stop elasticsearch service is called correctly."""
    mocked_remote_hosts = mock.Mock(spec_set=RemoteHosts)
    mocked_remote_hosts.run_sync = mock.Mock(return_value=iter(()))
    elastic_hosts = ec.ElasticsearchHosts(mocked_remote_hosts, None)
    elastic_hosts.stop_elasticsearch()
    mocked_remote_hosts.run_sync.assert_called_with("cat /etc/elasticsearch/instances | xargs systemctl stop")


def test_restart_elasticsearch():
    """Test that restart elasticsearch service is called correctly."""
    mocked_remote_hosts = mock.Mock(spec_set=RemoteHosts)
    mocked_remote_hosts.run_sync = mock.Mock(return_value=iter(()))
    elastic_hosts = ec.ElasticsearchHosts(mocked_remote_hosts, None)
    elastic_hosts.restart_elasticsearch()
    mocked_remote_hosts.run_sync.assert_called_with("cat /etc/elasticsearch/instances | xargs systemctl restart")


def test_depool_nodes():
    """Test that depool command is called correctly."""
    mocked_remote_hosts = mock.Mock(spec_set=RemoteHosts)
    mocked_remote_hosts.run_sync = mock.Mock(return_value=iter(()))
    elastic_hosts = ec.ElasticsearchHosts(mocked_remote_hosts, None)
    elastic_hosts.depool_nodes()
    mocked_remote_hosts.run_sync.assert_called_with("depool")


def test_pool_nodes():
    """Test that pool command is called correctly."""
    mocked_remote_hosts = mock.Mock(spec_set=RemoteHosts)
    mocked_remote_hosts.run_sync = mock.Mock(return_value=iter(()))
    elastic_hosts = ec.ElasticsearchHosts(mocked_remote_hosts, None)
    elastic_hosts.pool_nodes()
    mocked_remote_hosts.run_sync.assert_called_with("pool")


def test_wait_for_elasticsearch_up_delegates_to_all_nodes_groups():
    """Test that elasticsearch instance is called when wait for instance to come up."""
    node_group1 = mock.Mock(spec_set=NodesGroup)
    node_group1.check_all_nodes_up = mock.Mock()
    node_group2 = mock.Mock(spec_set=NodesGroup)
    node_group2.check_all_nodes_up = mock.Mock()
    remote_hosts = mock.Mock(spec_set=RemoteHosts)

    hosts = ec.ElasticsearchHosts(remote_hosts, [node_group1, node_group2], dry_run=False)
    hosts.wait_for_elasticsearch_up()

    assert node_group1.check_all_nodes_up.called
    assert node_group2.check_all_nodes_up.called


def test_wait_for_elasticsearch_does_no_check_when_in_dry_run():
    """In dry run we expect to always return that all nodes are up."""
    node_group = mock.Mock(spec_set=NodesGroup)
    node_group.check_all_nodes_up = mock.Mock()
    remote_hosts = mock.Mock(spec_set=RemoteHosts)

    hosts = ec.ElasticsearchHosts(remote_hosts, [node_group], dry_run=True)
    hosts.wait_for_elasticsearch_up()

    assert not node_group.check_all_nodes_up.called


@mock.patch("wmflib.decorators.time.sleep", return_value=None)
def test_wait_for_elasticsearch_up_fails_if_one_node_is_down(mocked_sleep):
    """Test that elasticsearch instance is called when wait for instance to come up."""
    node_group1 = mock.Mock(spec_set=NodesGroup)
    node_group1.check_all_nodes_up = mock.Mock()
    node_group2 = mock.Mock(spec_set=NodesGroup)
    node_group2.check_all_nodes_up = mock.Mock(side_effect=ec.ElasticsearchClusterCheckError())
    remote_hosts = mock.Mock(spec_set=RemoteHosts)

    hosts = ec.ElasticsearchHosts(remote_hosts, [node_group1, node_group2], dry_run=False)

    with pytest.raises(ec.ElasticsearchClusterCheckError):
        hosts.wait_for_elasticsearch_up(timedelta(minutes=1))
    assert mocked_sleep.called


@mock.patch("wmflib.decorators.time.sleep", return_value=None)
def test_wait_for_elasticsearch_up_retries_on_failures(mocked_sleep):
    """Test that elasticsearch instance is called when wait for instance to come up."""
    node_group = mock.Mock(spec_set=NodesGroup)
    node_group.check_all_nodes_up = mock.Mock(side_effect=ec.ElasticsearchClusterCheckError())
    remote_hosts = mock.Mock(spec_set=RemoteHosts)

    hosts = ec.ElasticsearchHosts(remote_hosts, [node_group], dry_run=False)

    with pytest.raises(ec.ElasticsearchClusterCheckError):
        hosts.wait_for_elasticsearch_up(timedelta(minutes=1))
    assert node_group.check_all_nodes_up.call_count == 12
    assert mocked_sleep.called


def test_cluster_settings_are_unchanged_when_stopped_replication_is_dry_run():
    """Check that cluster routing in dry run mode is truly safe."""
    elasticsearch_cluster = ec.ElasticsearchCluster("endpoint:9200", None, dry_run=True)
    with mock.patch.object(elasticsearch_cluster, "make_api_call"):
        with elasticsearch_cluster.stopped_replication():
            assert not elasticsearch_cluster.make_api_call.called


class TestElasticsearchClusters:
    """Test class for Elasticsearch Clusters."""

    def setup_method(self):
        """Setup the test environment."""
        # pylint: disable=attribute-defined-outside-init
        endpoint1 = "endpoint:9201"
        endpoint2 = "endpoint:9202"
        self.cluster1 = ec.ElasticsearchCluster(endpoint1, None, dry_run=False)
        self.cluster2 = ec.ElasticsearchCluster(endpoint2, None, dry_run=False)
        self.clusters = [self.cluster1, self.cluster2]
        self.cluster1.make_api_call = mock.Mock()
        self.cluster2.make_api_call = mock.Mock()

    def default_elasticsearch_clusters(self):
        """Return simple default Elasticsearch clusters to DRY up test code."""
        return ec.ElasticsearchClusters(self.clusters, None, None, ["eqiad", "codfw"])

    def test_flush_markers_on_clusters(self):
        """Test that elasticsearch call to flush markers was properly made."""
        elasticsearch_clusters = self.default_elasticsearch_clusters()
        elasticsearch_clusters.flush_markers(timedelta(seconds=30))
        self.cluster1.make_api_call.assert_has_calls(
            [
                mock.call(
                    route="/_flush",
                    params={"force": "true"},
                    http_method="POST",
                    body={},
                    timeout=30.0,
                ),
                mock.call(
                    route="/_flush/synced",
                    params={},
                    http_method="POST",
                    body={},
                    timeout=30.0,
                ),
            ]
        )
        self.cluster2.make_api_call.assert_has_calls(
            [
                mock.call(
                    route="/_flush",
                    params={"force": "true"},
                    http_method="POST",
                    body={},
                    timeout=30.0,
                ),
                mock.call(route="/_flush/synced", params={}, http_method="POST", body={}, timeout=30.0),
            ]
        )

    def test_flush_markers_on_clusters_fail(self):
        """Test that when conflict error is raised, execution continues."""
        self.cluster1.make_api_call = mock.Mock(side_effect=APIClientError("test"))

        elasticsearch_clusters = self.default_elasticsearch_clusters()
        elasticsearch_clusters.flush_markers(timedelta(seconds=30))
        self.cluster2.make_api_call.assert_has_calls(
            [
                mock.call(
                    route="/_flush",
                    params={"force": "true"},
                    http_method="POST",
                    body={},
                    timeout=30.0,
                ),
                mock.call(route="/_flush/synced", params={}, http_method="POST", body={}, timeout=30.0),
            ]
        )

    def test_flush_markers_on_clusters_fail_synced(self, caplog):
        """Test that when conflict error is raised during synced flush, execution continues."""
        caplog.set_level(logging.WARNING)
        self.cluster1.make_api_call = mock.Mock(side_effect=[None, APIClientError("test")])
        elasticsearch_clusters = self.default_elasticsearch_clusters()
        elasticsearch_clusters.flush_markers(timedelta(seconds=30))
        self.cluster1.make_api_call.assert_has_calls(
            [
                mock.call(
                    route="/_flush",
                    params={"force": "true"},
                    http_method="POST",
                    body={},
                    timeout=30.0,
                ),
                mock.call(route="/_flush/synced", params={}, http_method="POST", body={}, timeout=30.0),
            ]
        )
        self.cluster2.make_api_call.assert_has_calls(
            [
                mock.call(
                    route="/_flush",
                    params={"force": "true"},
                    http_method="POST",
                    body={},
                    timeout=30.0,
                ),
                mock.call(route="/_flush/synced", params={}, http_method="POST", body={}, timeout=30.0),
            ]
        )
        assert caplog.record_tuples == [
            (
                "spicerack.elasticsearch_cluster",
                logging.WARNING,
                "Not all shards were synced flushed on endpoint:9201.",
            ),
        ]

    def test_when_all_shards_are_assigned_no_allocation_is_performed(self):
        """Test that shard allocation is not performed when all shards have been assigned on all clusters."""
        self.cluster1.get_nodes = mock.Mock(return_value={"ELASTIC1": {"name": "el1-alpha"}})
        self.cluster2.get_nodes = mock.Mock(return_value={"ELASTIC7": {"name": "el1-beta"}})
        self.cluster1._get_unassigned_shards = mock.Mock(return_value=[])  # pylint: disable=protected-access
        self.cluster2._get_unassigned_shards = mock.Mock(return_value=[])  # pylint: disable=protected-access
        elasticsearch_clusters = self.default_elasticsearch_clusters()
        elasticsearch_clusters.force_allocation_of_all_unassigned_shards()
        self.cluster1.make_api_call.assert_not_called()
        self.cluster2.make_api_call.assert_not_called()

    def test_force_allocation_of_all_unassigned_shards(self):
        """Test that elasticsearch performs cluster reroute with with unassigned shards on all clusters."""
        self.cluster1.get_nodes = mock.Mock(return_value={"ELASTIC1": {"name": "el1-alpha"}})
        self.cluster2.get_nodes = mock.Mock(return_value={"ELASTIC7": {"name": "el1-beta"}})
        self.cluster1._get_unassigned_shards = mock.Mock(  # pylint: disable=protected-access
            return_value=[
                {"index": "index1", "shard": 2, "state": "UNASSIGNED"},
            ]
        )
        self.cluster2._get_unassigned_shards = mock.Mock(  # pylint: disable=protected-access
            return_value=[
                {"index": "index4", "shard": 7, "state": "UNASSIGNED"},
            ]
        )
        elasticsearch_clusters = self.default_elasticsearch_clusters()
        elasticsearch_clusters.force_allocation_of_all_unassigned_shards()
        self.cluster1.make_api_call.assert_called_once_with(
            route="/_cluster/reroute",
            params={"retry_failed": True},
            http_method="POST",
            body={"commands": {"allocate_replica": {"index": "index1", "shard": 2, "node": "el1-alpha"}}},
            timeout=30,
        )
        self.cluster2.make_api_call.assert_called_once_with(
            route="/_cluster/reroute",
            params={"retry_failed": True},
            http_method="POST",
            body={"commands": {"allocate_replica": {"index": "index4", "shard": 7, "node": "el1-beta"}}},
            timeout=30,
        )

    def test_force_allocation_of_shards_with_failed_node(self, caplog):
        """Test that shard allocation command was called twice after it fails on the first node."""
        caplog.set_level(logging.WARNING)
        self.cluster1.get_nodes = mock.Mock(
            return_value={
                "ELASTIC1": {"name": "el1-alpha"},
                "ELASTIC3": {"name": "el2-alpha"},
            }
        )
        self.cluster2.get_nodes = mock.Mock(
            return_value={
                "ELASTIC7": {"name": "el1-beta"},
                "ELASTIC4": {"name": "el2-beta"},
            }
        )
        self.cluster1._get_unassigned_shards = mock.Mock(  # pylint: disable=protected-access
            return_value=[
                {"index": "index1", "shard": 2, "state": "UNASSIGNED"},
            ]
        )
        self.cluster2._get_unassigned_shards = mock.Mock(  # pylint: disable=protected-access
            return_value=[
                {"index": "index4", "shard": 7, "state": "UNASSIGNED"},
            ]
        )
        self.cluster1.make_api_call = mock.Mock(side_effect=APIClientError("test"))
        self.cluster2.make_api_call = mock.Mock(side_effect=APIClientError("test"))
        elasticsearch_clusters = self.default_elasticsearch_clusters()
        elasticsearch_clusters.force_allocation_of_all_unassigned_shards()
        self.cluster1.make_api_call.assert_has_calls(
            calls=[
                mock.call(
                    route="/_cluster/reroute",
                    params={"retry_failed": True},
                    http_method="POST",
                    body={"commands": {"allocate_replica": {"index": "index1", "shard": 2, "node": "el1-alpha"}}},
                    timeout=30,
                ),
                mock.call(
                    route="/_cluster/reroute",
                    params={"retry_failed": True},
                    http_method="POST",
                    body={"commands": {"allocate_replica": {"index": "index1", "shard": 2, "node": "el2-alpha"}}},
                    timeout=30,
                ),
            ],
            any_order=True,  # we shuffle the nodes
        )
        self.cluster2.make_api_call.assert_has_calls(
            calls=[
                mock.call(
                    route="/_cluster/reroute",
                    params={"retry_failed": True},
                    http_method="POST",
                    body={"commands": {"allocate_replica": {"index": "index4", "shard": 7, "node": "el1-beta"}}},
                    timeout=30,
                ),
                mock.call(
                    route="/_cluster/reroute",
                    params={"retry_failed": True},
                    http_method="POST",
                    body={"commands": {"allocate_replica": {"index": "index4", "shard": 7, "node": "el2-beta"}}},
                    timeout=30,
                ),
            ],
            any_order=True,  # we shuffle the nodes
        )
        assert caplog.record_tuples == [
            ("spicerack.elasticsearch_cluster", logging.WARNING, "Could not reallocate shard [index1:2] on any node"),
            ("spicerack.elasticsearch_cluster", logging.WARNING, "Could not reallocate shard [index4:7] on any node"),
        ]

    def test_stopped_replication(self):
        """Check that context manager stops replication and then starts replication on each cluster."""
        self.cluster1.make_api_call = mock.Mock()
        self.cluster2.make_api_call = mock.Mock()
        elasticsearch_clusters = self.default_elasticsearch_clusters()
        with elasticsearch_clusters.stopped_replication():
            self.cluster1.make_api_call.assert_called_with(
                route="/_cluster/settings",
                params={},
                http_method="PUT",
                body={"persistent": {"cluster.routing.allocation.enable": "primaries"}},
                timeout=30,
            )
            self.cluster2.make_api_call.assert_called_with(
                route="/_cluster/settings",
                params={},
                http_method="PUT",
                body={"persistent": {"cluster.routing.allocation.enable": "primaries"}},
                timeout=30,
            )

        self.cluster1.make_api_call.assert_called_with(
            route="/_cluster/settings",
            params={},
            http_method="PUT",
            body={"persistent": {"cluster.routing.allocation.enable": "all"}},
            timeout=30,
        )
        self.cluster2.make_api_call.assert_called_with(
            route="/_cluster/settings",
            params={},
            http_method="PUT",
            body={"persistent": {"cluster.routing.allocation.enable": "all"}},
            timeout=30,
        )

    def test_frozen_writes_write_to_index(self):
        """Test that elasticsearch write to index is called to freeze writes."""
        reason = Reason("test", "test_user", "test_host", task_id="T111222")
        elasticsearch_clusters = self.default_elasticsearch_clusters()
        with elasticsearch_clusters.frozen_writes(reason):
            self.cluster1.make_api_call.assert_called_with(
                route="/mw_cirrus_metastore/_doc/freeze-everything",
                params={},
                http_method="PUT",
                body={"host": "test_host", "timestamp": mock.ANY, "reason": "test - test_user@test_host - T111222"},
                timeout=30,
            )
            self.cluster2.make_api_call.assert_called_with(
                route="/mw_cirrus_metastore/_doc/freeze-everything",
                params={},
                http_method="PUT",
                body={"host": "test_host", "timestamp": mock.ANY, "reason": "test - test_user@test_host - T111222"},
                timeout=30,
            )

        self.cluster1.make_api_call.assert_called_with(
            route="mw_cirrus_metastore/_doc/freeze-everything", params={}, http_method="DELETE", body={}, timeout=30
        )
        self.cluster2.make_api_call.assert_called_with(
            route="mw_cirrus_metastore/_doc/freeze-everything", params={}, http_method="DELETE", body={}, timeout=30
        )

    def test_when_frozen_writes_fails_exception_is_raised(self):
        """Test that when elasticsearch write to index fails, an exception is raised.

        and a call to delete/unfreeze write is placed
        """
        self.cluster1.make_api_call.side_effect = APIClientError("test")
        reason = Reason("test", "test_user", "test_host", task_id="T111222")
        elasticsearch_clusters = self.default_elasticsearch_clusters()
        with pytest.raises(ec.ElasticsearchClusterError):
            with elasticsearch_clusters.frozen_writes(reason):
                self.cluster1.make_api_call.assert_called_with(
                    route="/mw_cirrus_metastore/_doc/freeze-everything",
                    params={},
                    http_method="PUT",
                    body={"host": "test_host", "timestamp": mock.ANY, "reason": "test - test_user@test_host - T111222"},
                    timeout=30,
                )
                self.cluster2.make_api_call.assert_not_called()
        assert self.cluster1.make_api_call.call_count == 1
        assert self.cluster2.make_api_call.call_count == 0

    def test_when_unfreeze_writes_fails_exception_is_raised(self, caplog):
        """Test that when elasticsearch delete doc in index fails, an exception is raised.

        and a call to delete/unfreeze write is placed

        """
        caplog.set_level(logging.WARNING)
        # the freeze works, unfreeze fails
        self.cluster1.make_api_call = mock.Mock(side_effect=[None, APIClientError("test"), None, None])

        reason = Reason("test", "test_user", "test_host", task_id="T111222")
        elasticsearch_clusters = self.default_elasticsearch_clusters()
        with elasticsearch_clusters.frozen_writes(reason):
            self.cluster1.make_api_call.assert_called_with(
                route="/mw_cirrus_metastore/_doc/freeze-everything",
                params={},
                http_method="PUT",
                body={"host": "test_host", "timestamp": mock.ANY, "reason": "test - test_user@test_host - T111222"},
                timeout=30,
            )
            self.cluster2.make_api_call.assert_called_with(
                route="/mw_cirrus_metastore/_doc/freeze-everything",
                params={},
                http_method="PUT",
                body={"host": "test_host", "timestamp": mock.ANY, "reason": "test - test_user@test_host - T111222"},
                timeout=30,
            )

        # the second api call (unfreeze) failed, so we tried to freeze and unfreeze again
        assert self.cluster1.make_api_call.call_count == 4  # freeze(ok), unfreeze(fail), freeze(ok), unfreeze(ok)
        assert self.cluster2.make_api_call.call_count == 2  # freeze(ok), unfreeze(fail)
        assert caplog.record_tuples == [
            (
                "spicerack.elasticsearch_cluster",
                logging.WARNING,
                (
                    "Could not unfreeze writes, trying to freeze and unfreeze again: Encountered error while deleting "
                    "'freeze-everything' document to unfreeze cluster writes"
                ),
            )
        ]

    def test_no_call_to_freeze_write_in_dry_run(self):
        """Test that when dry run is enabled, call to write to cluster index to freeze write is not placed."""
        cluster1 = ec.ElasticsearchCluster(self.cluster1, None, dry_run=True)
        cluster2 = ec.ElasticsearchCluster(self.cluster2, None, dry_run=True)
        reason = Reason("test", "test_user", "test_host", task_id="T111222")
        elasticsearch_clusters = ec.ElasticsearchClusters([cluster1, cluster2], None, None, ["eqiad", "codfw"])
        with elasticsearch_clusters.frozen_writes(reason):
            self.cluster1.make_api_call.assert_not_called()
            self.cluster2.make_api_call.assert_not_called()

    def test_wait_for_all_write_queues_with_queues_empty(self):
        """Ensure that we return None in the "happy path", when all queues are empty, meaning we didn't raise."""
        prometheus = mock.MagicMock(spec_set=Prometheus)
        prometheus.query = mock.MagicMock(
            return_value=[
                {
                    "metric": {"topic": "the_topic", "partition": "the_partition"},
                    "value": [1597958424.599, "0"],
                },
                {
                    "metric": {"topic": "the_topic", "partition": "the_partition"},
                    "value": [1597958424.599, "0"],
                },
                {
                    "metric": {"topic": "the_topic", "partition": "the_partition"},
                    "value": [1597958424.599, "0"],
                },
            ]
        )
        elasticsearch_clusters = ec.ElasticsearchClusters(self.clusters, None, prometheus, ["eqiad", "codfw"])

        assert elasticsearch_clusters.wait_for_all_write_queues_empty() is None

    def test_wait_for_all_write_queues_with_queues_non_empty(self):
        """Ensure that we raise an ElasticsearchClusterCheckError if write queues aren't empty."""
        prometheus = mock.MagicMock(spec_set=Prometheus)
        prometheus.query = mock.MagicMock(
            return_value=[
                {
                    "metric": {"topic": "the_topic", "partition": "the_partition"},
                    "value": [1597958424.599, "9535"],
                },
                {
                    "metric": {"topic": "the_topic", "partition": "the_partition"},
                    "value": [1597958424.599, "9608"],
                },
                {
                    "metric": {"topic": "the_topic", "partition": "the_partition"},
                    "value": [1597958424.599, "9536"],
                },
            ]
        )
        elasticsearch_clusters = ec.ElasticsearchClusters(self.clusters, None, prometheus, ["eqiad", "codfw"])

        with pytest.raises(ec.ElasticsearchClusterCheckError):
            elasticsearch_clusters.wait_for_all_write_queues_empty()

    def test_wait_for_all_write_queues_with_empty_response(self):
        """Ensure that we raise ElasticsearchClusterError if prometheus query fails to return any results."""
        prometheus = mock.MagicMock(spec_set=Prometheus)
        prometheus.query = mock.MagicMock(return_value=[])
        elasticsearch_clusters = ec.ElasticsearchClusters(self.clusters, None, prometheus, ["eqiad", "codfw"])

        with pytest.raises(ec.ElasticsearchClusterError):
            elasticsearch_clusters.wait_for_all_write_queues_empty()

    def test_write_queue_datacenters_get_queried(self):
        """Ensure that there is a prometheus query for each dc of write_queue_datacenters."""
        prometheus = mock.MagicMock(spec_set=Prometheus)
        prometheus.query = mock.MagicMock(
            return_value=[
                {
                    "metric": {"topic": "the_topic", "partition": "the_partition"},
                    "value": [1597958424.599, "0"],
                },
                {
                    "metric": {"topic": "the_topic", "partition": "the_partition"},
                    "value": [1597958424.599, "0"],
                },
                {
                    "metric": {"topic": "the_topic", "partition": "the_partition"},
                    "value": [1597958424.599, "0"],
                },
            ]
        )
        elasticsearch_clusters = ec.ElasticsearchClusters(self.clusters, None, prometheus, ["eqiad", "codfw"])
        elasticsearch_clusters.wait_for_all_write_queues_empty()

        assert prometheus.query.mock_calls == [
            mock.call(mock.ANY, "eqiad"),
            mock.call(mock.ANY, "codfw"),
        ]

    def test_wait_for_green_on_all_clusters_elastisearch_call(self):
        """Makes sure the call to elasticsearch.cluster.health is placed for each cluster."""
        elasticsearch_clusters = self.default_elasticsearch_clusters()
        elasticsearch_clusters.wait_for_green(timedelta(seconds=13))
        self.cluster1.make_api_call.assert_called_once_with(
            route="/_cluster/health",
            params={"wait_for_status": "green", "timeout": "1s"},
            http_method="GET",
            body={},
            timeout=30,
        )
        self.cluster2.make_api_call.assert_called_once_with(
            route="/_cluster/health",
            params={"wait_for_status": "green", "timeout": "1s"},
            http_method="GET",
            body={},
            timeout=30,
        )

    @mock.patch("spicerack.elasticsearch_cluster.retry")
    def test_wait_for_green_correct_tries_test(self, retry):
        """Check that the number of tries is correctly computed."""
        elasticsearch_clusters = self.default_elasticsearch_clusters()
        elasticsearch_clusters.wait_for_green(timedelta(seconds=20))
        assert retry.call_args[1]["tries"] == 2

    @mock.patch("spicerack.elasticsearch_cluster.retry")
    def test_wait_for_green_default_tries_test(self, retry):
        """Checks that a default value of 1 is returned when timeout is less than 10."""
        elasticsearch_clusters = self.default_elasticsearch_clusters()
        elasticsearch_clusters.wait_for_green(timedelta(seconds=4))
        assert retry.call_args[1]["tries"] == 1

    @mock.patch("wmflib.decorators.time.sleep", return_value=None)
    def test_wait_for_green_retry_test(self, mocked_sleep):
        """Test that the retry is called again when cluster health request throws an exception."""
        self.cluster1.make_api_call = mock.Mock(side_effect=[APIClientError("test"), None])
        self.cluster2.make_api_call = mock.Mock(side_effect=[APIClientError("test"), None])
        elasticsearch_clusters = self.default_elasticsearch_clusters()
        with pytest.raises(ec.ElasticsearchClusterCheckError):
            elasticsearch_clusters.wait_for_green(timedelta(seconds=20))

        mocked_sleep.assert_called_once_with(10.0)
        assert self.cluster1.make_api_call.call_count == 2  # fail, ok
        assert self.cluster2.make_api_call.call_count == 1  # not called, ok

    def test_wait_for_yellow_w_no_moving_shards_on_all_clusters_elastisearch_call(self):
        """Makes sure the call to elasticsearch.cluster.health is placed for each cluster."""
        elasticsearch_clusters = self.default_elasticsearch_clusters()
        elasticsearch_clusters.wait_for_yellow_w_no_moving_shards(timedelta(seconds=13))
        self.cluster1.make_api_call.assert_called_once_with(
            route="/_cluster/health",
            params={
                "wait_for_status": "yellow",
                "wait_for_no_initializing_shards": True,
                "wait_for_no_relocating_shards": True,
                "timeout": "1s",
            },
            http_method="GET",
            body={},
            timeout=30,
        )
        self.cluster2.make_api_call.assert_called_once_with(
            route="/_cluster/health",
            params={
                "wait_for_status": "yellow",
                "wait_for_no_initializing_shards": True,
                "wait_for_no_relocating_shards": True,
                "timeout": "1s",
            },
            http_method="GET",
            body={},
            timeout=30,
        )

    @mock.patch("wmflib.decorators.time.sleep", return_value=None)
    def test_wait_for_yellow_w_no_moving_shards_retry_test(self, mocked_sleep):
        """Test that the retry is called again when cluster health request throws an exception."""
        self.cluster1.make_api_call = mock.Mock(side_effect=[APIClientError("test"), None])
        self.cluster2.make_api_call = mock.Mock(side_effect=[APIClientError("test"), None])
        elasticsearch_clusters = self.default_elasticsearch_clusters()
        with pytest.raises(ec.ElasticsearchClusterCheckError):
            elasticsearch_clusters.wait_for_yellow_w_no_moving_shards(timedelta(seconds=20))
            assert mocked_sleep.called

        assert self.cluster1.make_api_call.call_count == 2  # fail, ok
        assert self.cluster2.make_api_call.call_count == 1  # not called, ok

    def test_reset_read_only_is_sent_to_all_clusters(self):
        """Reset read only status should be sent to all clusters."""
        # This should really be an integration test but too much work to set up.
        elasticsearch_clusters = self.default_elasticsearch_clusters()
        elasticsearch_clusters.reset_indices_to_read_write()

        self.cluster1.make_api_call.assert_called_once_with(
            route="/_all/_settings",
            params={},
            http_method="PUT",
            body={"index.blocks.read_only_allow_delete": None},
            timeout=30,
        )
        self.cluster2.make_api_call.assert_called_once_with(
            route="/_all/_settings",
            params={},
            http_method="PUT",
            body={"index.blocks.read_only_allow_delete": None},
            timeout=30,
        )

    def test_reset_read_only_wraps_exceptions(self):
        """Exceptions from underlying elasticsearch client should be wrapped."""
        self.cluster1.make_api_call = mock.Mock(side_effect=APIClientError("test"))
        self.cluster2.make_api_call = mock.Mock(side_effect=APIClientError("test"))

        elasticsearch_clusters = self.default_elasticsearch_clusters()
        with pytest.raises(ec.ElasticsearchClusterError):
            elasticsearch_clusters.reset_indices_to_read_write()

        self.cluster1.make_api_call.assert_called_once()
        self.cluster2.make_api_call.assert_not_called()


def test_get_next_clusters_nodes():
    """Test that next nodes belong in the same row on each cluster."""
    remote = mock.Mock(spec_set=Remote)
    since = datetime.utcfromtimestamp(20 / 1000)
    elasticsearch_clusters = ec.ElasticsearchClusters(
        mock_node_info(
            [
                {
                    "x1": json_node("elastic1001.example.com", "alpha", "row1", 10),
                    "x2": json_node("elastic1002.example.com", "alpha", "row1", 10),
                    "x3": json_node("elastic1003.example.com", "alpha", "row1", 30),
                },
                {
                    "y3": json_node("elastic1003.example.com", "gamma", "row1", 10),
                    "y4": json_node("elastic1004.example.com", "gamma", "row1", 10),
                },
            ]
        ),
        remote,
        None,
        ["eqiad", "codfw"],
    )
    elasticsearch_clusters.get_next_clusters_nodes(since, 4)
    nodes_not_restarted = remote.query.call_args[0][0]
    nodes_not_restarted = nodes_not_restarted.split(",")
    nodes_not_restarted.sort()
    assert nodes_not_restarted == [
        "elastic1001.example.com",
        "elastic1002.example.com",
        "elastic1003.example.com",
        "elastic1004.example.com",
    ]


def test_get_next_clusters_nodes_raises_error_when_size_is_less_than_one():
    """Test that next nodes belong in the same row on each cluster."""
    since = datetime.utcfromtimestamp(20 / 1000)
    elasticsearch_clusters = ec.ElasticsearchClusters(None, None, ["eqiad", "codfw"], None)
    with pytest.raises(ec.ElasticsearchClusterError):
        elasticsearch_clusters.get_next_clusters_nodes(since, 0)


def test_get_next_nodes_returns_less_nodes_than_specified():
    """Test that the nodes returned is less than specified based on if they have been restarted for each clusters."""
    remote = mock.Mock(spec_set=Remote)
    since = datetime.utcfromtimestamp(20 / 1000)
    elasticsearch_clusters = ec.ElasticsearchClusters(
        mock_node_info(
            [
                {
                    "x1": json_node("elastic1001.example.com", start_time=10),
                    "x2": json_node("elastic1002.example.com", start_time=10),
                    "x3": json_node("elastic1003.example.com", start_time=30),
                }
            ]
        ),
        remote,
        None,
        ["eqiad", "codfw"],
    )
    elasticsearch_clusters.get_next_clusters_nodes(since, 4)
    nodes_not_restarted = remote.query.call_args[0][0]
    nodes_not_restarted = nodes_not_restarted.split(",")
    nodes_not_restarted.sort()
    assert nodes_not_restarted == ["elastic1001.example.com", "elastic1002.example.com"]


def _eval_get_next_nodes(node_info, batch_size=4):
    def update_start(start_time, accept):
        for cluster in node_info:
            for node in cluster.values():
                if accept(node):
                    node["jvm"] = {"start_time_in_millis": start_time}

    update_start(0, lambda x: True)
    since = datetime.utcfromtimestamp(10 / 1000)
    for i in itertools.count(start=20, step=10):
        remote = mock.Mock(spec_set=Remote)
        elasticsearch_clusters = ec.ElasticsearchClusters(mock_node_info(node_info), remote, None, ["eqiad", "codfw"])
        res = elasticsearch_clusters.get_next_clusters_nodes(since, batch_size)
        if res is None:
            return
        # FIXME: We assert on the nodes that were queried via cumin and not on the return value of
        #  get_next_clusters_nodes(). This is a simplification to avoid mocking yet another return value.
        #  It is also a code smell. There is a refactoring waiting to happen to reduce / isolate the complexity
        #  of get_next_clusters_nodes().
        nodes_queried = remote.query.call_args[0][0]
        nodes_queried = nodes_queried.split(",")
        nodes_queried.sort()
        update_start(i, lambda x, nodes=nodes_queried: x["attributes"]["fqdn"] in nodes)
        yield nodes_queried


def test_get_next_nodes_returns_masters_from_separate_rows_one_at_a_time():
    """Test to verify masters ignore batching and start one at a time.

    Makes the bold assumption the cluster is properly deployed with only a single
    master capable node per row.
    """
    node_info = [
        {
            "m1": json_node("elastic1005.example.com", "alpha", "row2", 10, master_capable=True),
            "m2": json_node("elastic1006.example.com", "alpha", "row3", 10, master_capable=True),
        },
    ]

    seen = set()
    for batch in _eval_get_next_nodes(node_info):
        assert len(batch) == 1
        for node in batch:
            assert node not in seen
            seen.add(node)
    assert len(seen) == 2


def test_get_next_nodes_returns_masters_after_other_nodes():
    """Test to verify master nodes are restarted last.

    In this setup, mimicing prod, where some nodes are masters in two clusters,
    and some nodes are masters in one cluster, a3 and a4 must still be rebooted
    prior to a1 and a2, to ensure the alpha cluster masters are not restarted
    prior to their worker nodes.
    """
    node_info = [
        {
            "a1": json_node("elastic1001.example.com", "alpha", "row2", 10, master_capable=True),
            "a2": json_node("elastic1002.example.com", "alpha", "row3", 10, master_capable=True),
            "a3": json_node("elastic1003.example.com", "alpha", "row3", 10),
            "a4": json_node("elastic1004.example.com", "alpha", "row4", 10),
            "a5": json_node("elastic1005.example.com", "alpha", "row2", 10),
            "a6": json_node("elastic1006.example.com", "alpha", "row2", 10),
        },
        {
            "a1": json_node("elastic1001.example.com", "beta", "row2", 10, master_capable=True),
            "a3": json_node("elastic1003.example.com", "beta", "row3", 10, master_capable=True),
            "a5": json_node("elastic1005.example.com", "beta", "row2", 10),
        },
        {
            "a2": json_node("elastic1002.example.com", "delta", "row3", 10, master_capable=True),
            "a4": json_node("elastic1004.example.com", "delta", "row4", 10, master_capable=True),
            "a6": json_node("elastic1006.example.com", "delta", "row2", 10),
        },
    ]

    expect_batches = [
        {"elastic1005.example.com", "elastic1006.example.com"},
        {"elastic1001.example.com", "elastic1002.example.com", "elastic1003.example.com", "elastic1004.example.com"},
    ]
    expect_batch = None
    for batch in _eval_get_next_nodes(node_info):
        if not expect_batch:
            assert expect_batches, "unexpected batch of hosts returned"
            expect_batch = expect_batches.pop(0)
        unexpected = [node for node in batch if node not in expect_batch]
        assert not unexpected, "node not expected in current batch"
        expect_batch = expect_batch.difference(batch)
    assert not expect_batches, "expected batches of hosts remain"


def test_get_next_nodes_least_not_restarted():
    """Test to get rows that have the least not restarted nodes first on each cluster."""
    remote = mock.Mock(spec_set=Remote)
    since = datetime.utcfromtimestamp(20 / 1000)
    elasticsearch_clusters = ec.ElasticsearchClusters(
        mock_node_info(
            [
                {
                    "x4": json_node("elastic1005.example.com", "alpha", "row2", 10),
                    "x5": json_node("elastic1006.example.com", "alpha", "row2", 10),
                    "x6": json_node("elastic1007.example.com", "alpha", "row2", 30),
                },
                {
                    "x7": json_node("elastic1009.example.com", "beta", "row3", 10),
                    "x8": json_node("elastic1008.example.com", "beta", "row3", 50),
                    "x9": json_node("elastic1010.example.com", "beta", "row3", 30),
                },
            ]
        ),
        remote,
        None,
        ["eqiad", "codfw"],
    )
    elasticsearch_clusters.get_next_clusters_nodes(since, 4)
    # FIXME: We assert on the nodes that were queried via cumin and not on the return value of
    #  get_next_clusters_nodes(). This is a simplification to avoid mocking yet another return value.
    #  It is also a code smell. There is a refactoring waiting to happen to reduce / isolate the complexity
    #  of get_next_clusters_nodes().
    nodes_queried = remote.query.call_args[0][0]
    nodes_queried = nodes_queried.split(",")
    nodes_queried.sort()
    assert nodes_queried == ["elastic1009.example.com"]


def test_get_next_nodes_no_rows():
    """Test that all nodes have been restarted on all clusters."""
    since = datetime.utcfromtimestamp(20 / 1000)
    elasticsearch_clusters = ec.ElasticsearchClusters(
        mock_node_info(
            [
                {
                    "x3": json_node("elastic1003.example.com", "gamma", "row1", 30),
                    "x4": json_node("elastic1005.example.com", "gamma", "row2", 87),
                    "x5": json_node("elastic1006.example.com", "gamma", "row2", 77),
                },
                {
                    "x3": json_node("elastic1004.example.com", "alpha", "row1", 40),
                    "x4": json_node("elastic1005.example.com", "gamma", "row2", 89),
                    "x5": json_node("elastic1016.example.com", "alpha", "row2", 79),
                },
            ]
        ),
        None,
        None,
        ["eqiad", "codfw"],
    )
    result = elasticsearch_clusters.get_next_clusters_nodes(since, 2)
    assert result is None


def test_get_next_nodes_fails_when_rows_are_not_same():
    """Test that error is raised when clusters instances of the same node belong to different rows."""
    since = datetime.utcfromtimestamp(20 / 1000)
    elasticsearch_clusters = ec.ElasticsearchClusters(
        mock_node_info(
            [
                {
                    "x3": json_node("elastic1003.example.com", "gamma", "row1", 10),
                    "x4": json_node("elastic1005.example.com", "gamma", "row2", 87),
                },
                {
                    "x3": json_node("elastic1003.example.com", "alpha", "row6", 10),
                },
            ]
        ),
        None,
        None,
        ["eqiad", "codfw"],
    )
    with pytest.raises(AssertionError):
        elasticsearch_clusters.get_next_clusters_nodes(since, 2)


def test_nodes_group_aggregates_same_clusters():
    """Same cluster aggregated multiple times is ignored."""
    node1 = json_node("elastic1001.example.com", "alpha", row="row1")
    node2 = json_node("elastic1001.example.com", "alpha", row="row1")
    cluster = mock.Mock()
    group = NodesGroup(node1, cluster)
    group.accumulate(node2, cluster)

    assert len(group.clusters_instances) == 1


def test_nodes_group_fail_to_accumulate_with_different_fqdn():
    """Aggregation should only works if used on the same node."""
    node1 = json_node("elastic1001.example.com")
    node2 = json_node("elastic1002.example.com")
    cluster = mock.Mock()
    group = NodesGroup(node1, cluster)

    with pytest.raises(AssertionError):
        group.accumulate(node2, cluster)


def test_all_nodes_are_restarted():
    """All nodes are deemed restarted if they are all listed as cluster nodes."""
    node1 = json_node("elastic1001.example.com", cluster_name="alpha")
    node2 = json_node("elastic1001.example.com", cluster_name="beta")
    alpha, beta = mock_node_info([{"x1": node1}, {"y1": node2}])  # pylint: disable=unbalanced-tuple-unpacking

    group = NodesGroup(node1, alpha)
    group.accumulate(node2, beta)

    group.check_all_nodes_up()

    # whitebox testing for convenience
    # TODO: refactor mock_node_info() to expose the mock Elasticsearch instances
    alpha._api_client.request.assert_called_once_with(  # pylint: disable=protected-access
        "GET", "/_nodes", json={}, params={}, timeout=30
    )
    beta._api_client.request.assert_called_once_with(  # pylint: disable=protected-access
        "GET", "/_nodes", json={}, params={}, timeout=30
    )


def test_node_not_restarted():
    """Error is raised if a node is not listed as a member of the cluster."""
    node1 = json_node("elastic1001.example.com", cluster_name="alpha")
    node2 = json_node("elastic1001.example.com", cluster_name="beta")
    alpha, beta = mock_node_info([{"x1": node1}, {"y1": node2}])  # pylint: disable=unbalanced-tuple-unpacking

    group = NodesGroup(node1, alpha)
    group.accumulate(node2, beta)

    # remove elastic1001 from alpha cluster
    alpha.make_api_call = mock.Mock(return_value={"nodes": {}})  # pylint: disable=protected-access
    with pytest.raises(ec.ElasticsearchClusterCheckError):
        group.check_all_nodes_up()


def json_node(
    fqdn: str,
    cluster_name: str = "alpha-cluster",
    row: str = "row1",
    start_time: int = 10,
    master_capable: bool = False,
) -> dict:
    """Used to mock the elasticsearch node API."""
    hostname = fqdn.split(".", 1)[0]
    node_name = f"{hostname}-{cluster_name}"
    return {
        "name": node_name,
        "attributes": {
            "row": row,
            "hostname": hostname,
            "fqdn": fqdn,
        },
        "roles": ["master"] if master_capable else [],
        "settings": {
            "cluster": {
                "name": cluster_name,
            }
        },
        "jvm": {"start_time_in_millis": start_time},
    }


def mock_node_info(values):
    """Creates a list of ElasticsearchCluster which will return the given node info."""
    clusters = []
    port = 9200
    for nodes in values:
        endpoint = f"localhost:{port}"
        api_client = mock.Mock(spec_set=APIClient)
        mock_response = mock.Mock()
        mock_response.json.return_value = {"nodes": nodes}
        api_client.request.return_value = mock_response
        cluster = ec.ElasticsearchCluster(endpoint, None, dry_run=False)
        cluster._api_client = api_client  # pylint: disable=protected-access
        clusters.append(cluster)

        port += 1
    return clusters
