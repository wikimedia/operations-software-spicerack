"""ElasticsearchCluster module test."""
from datetime import datetime, timedelta
from unittest import mock

import pytest

from cumin import NodeSet
from elasticsearch import Elasticsearch, ConflictError, RequestError, TransportError

from spicerack import elasticsearch_cluster as ec
from spicerack.administrative import Reason
from spicerack.remote import Remote, RemoteHosts
from spicerack.tests import elasticsearch_too_old


pytestmark = pytest.mark.skipif(  # pylint: disable=invalid-name
    elasticsearch_too_old(), reason='Requires more recent elasticsearch module'
)


def test_create_elasticsearch_clusters():
    """It should return an instance of ElasticsearchCluster."""
    target = ec.create_elasticsearch_clusters('search_eqiad', None)
    assert isinstance(target, ec.ElasticsearchClusters)


def test_create_elasticsearch_clusters_fail():
    """It should throw an ElasticsearchCluster Exception."""
    with pytest.raises(ec.ElasticsearchClusterError, match='No cluster group named search_test'):
        ec.create_elasticsearch_clusters('search_test', None)


def test_get_remote_hosts():
    """Test that RemoteHosts instance is returned."""
    mocked_remote_hosts = mock.Mock(spec_set=RemoteHosts)
    mocked_remote_hosts.hosts = NodeSet('el[1-2]')
    elastic_hosts = ec.ElasticsearchHosts(mocked_remote_hosts, None)
    result = elastic_hosts.get_remote_hosts()
    assert isinstance(result, RemoteHosts)


def test_start_elasticsearch():
    """Test that start elasticsearch service is called correctly."""
    mocked_remote_hosts = mock.Mock(spec_set=RemoteHosts)
    mocked_remote_hosts.run_sync = mock.Mock(return_value=iter(()))
    elastic_hosts = ec.ElasticsearchHosts(mocked_remote_hosts, None)
    elastic_hosts.start_elasticsearch()
    mocked_remote_hosts.run_sync.assert_called_with('cat /etc/elasticsearch/instances | xarg systemctl start')


def test_stop_elasticsearch():
    """Test that stop elasticsearch service is called correctly."""
    mocked_remote_hosts = mock.Mock(spec_set=RemoteHosts)
    mocked_remote_hosts.run_sync = mock.Mock(return_value=iter(()))
    elastic_hosts = ec.ElasticsearchHosts(mocked_remote_hosts, None)
    elastic_hosts.stop_elasticsearch()
    mocked_remote_hosts.run_sync.assert_called_with('cat /etc/elasticsearch/instances | xarg systemctl stop')


def test_restart_elasticsearch():
    """Test that restart elasticsearch service is called correctly."""
    mocked_remote_hosts = mock.Mock(spec_set=RemoteHosts)
    mocked_remote_hosts.run_sync = mock.Mock(return_value=iter(()))
    elastic_hosts = ec.ElasticsearchHosts(mocked_remote_hosts, None)
    elastic_hosts.restart_elasticsearch()
    mocked_remote_hosts.run_sync.assert_called_with('cat /etc/elasticsearch/instances | xarg systemctl restart')


def test_depool_nodes():
    """Test that depool command is called correctly."""
    mocked_remote_hosts = mock.Mock(spec_set=RemoteHosts)
    mocked_remote_hosts.run_sync = mock.Mock(return_value=iter(()))
    elastic_hosts = ec.ElasticsearchHosts(mocked_remote_hosts, None)
    elastic_hosts.depool_nodes()
    mocked_remote_hosts.run_sync.assert_called_with('depool')


def test_pool_nodes():
    """Test that pool command is called correctly."""
    mocked_remote_hosts = mock.Mock(spec_set=RemoteHosts)
    mocked_remote_hosts.run_sync = mock.Mock(return_value=iter(()))
    elastic_hosts = ec.ElasticsearchHosts(mocked_remote_hosts, None)
    elastic_hosts.pool_nodes()
    mocked_remote_hosts.run_sync.assert_called_with('pool')


def test_elasticsearch_call_when_wait_for_elasticsearch_up():
    """Test that elasticsearch instance is called when wait for instance to come up."""
    remote = mock.Mock(spec_set=Remote)
    elastic_alpha = Elasticsearch('localhost:9200')
    elastic_alpha.nodes.info = mock.Mock(return_value={
        'nodes': {
            'ELASTIC4': {'name': 'el5-alpha'}, 'ELASTIC5': {'name': 'el6-alpha'}
        }
    })
    elastic_alpha_cluster = ec.ElasticsearchCluster(elastic_alpha, None, dry_run=False)

    elastic_beta = Elasticsearch('localhost:9201')
    elastic_beta.nodes.info = mock.Mock(return_value={
        'nodes': {
            'ELASTIC4': {'name': 'el5-beta'}, 'ELASTIC5': {'name': 'el6-beta'}
        }
    })
    elastic_beta_cluster = ec.ElasticsearchCluster(elastic_beta, None, dry_run=False)

    next_nodes = [
        {'name': 'el5',
            'clusters_instances': [
                elastic_alpha_cluster,
                elastic_beta_cluster,
            ]
         },
        {'name': 'el6',
            'clusters_instances': [
                elastic_alpha_cluster,
                elastic_beta_cluster,
            ]
         }
    ]

    elastic_hosts = ec.ElasticsearchHosts(remote, next_nodes, dry_run=False)
    elastic_hosts.wait_for_elasticsearch_up()
    assert elastic_alpha.nodes.info.called
    assert elastic_beta.nodes.info.called


def test_elasticsearch_call_not_made_when_wait_for_elasticsearch_up_in_dry_run():
    """Test that elasticsearch instance is not called in dry run mode."""
    remote = mock.Mock(spec_set=Remote)
    elastic_alpha = Elasticsearch('localhost:9200')
    elastic_alpha.nodes.info = mock.Mock(return_value={
        'nodes': {
            'ELASTIC4': {'name': 'el5-alpha'}, 'ELASTIC5': {'name': 'el6-alpha'}
        }
    })
    elastic_alpha_cluster = ec.ElasticsearchCluster(elastic_alpha, None, dry_run=False)

    elastic_beta = Elasticsearch('localhost:9201')
    elastic_beta.nodes.info = mock.Mock(return_value={
        'nodes': {
            'ELASTIC4': {'name': 'el5-beta'}, 'ELASTIC5': {'name': 'el6-beta'}
        }
    })
    elastic_beta_cluster = ec.ElasticsearchCluster(elastic_beta, None, dry_run=False)

    next_nodes = [
        {'name': 'el5',
         'clusters_instances': [
             elastic_alpha_cluster,
             elastic_beta_cluster,
         ]
         },
        {'name': 'el6',
         'clusters_instances': [
             elastic_alpha_cluster,
             elastic_beta_cluster,
         ]
         }
    ]

    elastic_hosts = ec.ElasticsearchHosts(remote, next_nodes, dry_run=True)
    elastic_hosts.wait_for_elasticsearch_up()
    assert not elastic_alpha.nodes.info.called
    assert not elastic_beta.nodes.info.called


@mock.patch('spicerack.decorators.time.sleep', return_value=None)
def test_elasticsearch_call_is_retried_when_wait_for_elasticsearch_up_is_not_up(mocked_sleep):
    """Test that elasticsearch instance is called more than once when node is not found in cluster."""
    remote = mock.Mock(spec_set=Remote)
    elastic_alpha = Elasticsearch('localhost:9200')
    elastic_alpha.nodes.info = mock.Mock(return_value={
        'nodes': {
            'ELASTIC4': {'name': 'el7-alpha'}, 'ELASTIC5': {'name': 'el8-alpha'}
        }
    })
    elastic_alpha_cluster = ec.ElasticsearchCluster(elastic_alpha, None, dry_run=False)

    elastic_beta = Elasticsearch('localhost:9201')
    elastic_beta.nodes.info = mock.Mock(return_value={
        'nodes': {
            'ELASTIC4': {'name': 'el5-beta'}, 'ELASTIC5': {'name': 'el6-beta'}
        }
    })
    elastic_beta_cluster = ec.ElasticsearchCluster(elastic_beta, None, dry_run=False)

    next_nodes = [
        {'name': 'el5',
         'clusters_instances': [
             elastic_alpha_cluster,
             elastic_beta_cluster,
         ]
         },
        {'name': 'el6',
         'clusters_instances': [
             elastic_alpha_cluster,
             elastic_beta_cluster,
         ]
         }
    ]

    elastic_hosts = ec.ElasticsearchHosts(remote, next_nodes, dry_run=False)
    with pytest.raises(ec.ElasticsearchClusterCheckError):
        elastic_hosts.wait_for_elasticsearch_up(timedelta(seconds=20))
        assert mocked_sleep.called
    assert elastic_alpha.nodes.info.call_count == 4


@mock.patch('spicerack.decorators.time.sleep', return_value=None)
def test_elasticsearch_call_is_retried_when_wait_for_elasticsearch_up_cannot_be_reached(mocked_sleep):
    """Test that elasticsearch instance is called more than once when the cluster cannot be reached."""
    remote = mock.Mock(spec_set=Remote)
    elastic_alpha = Elasticsearch('localhost:9200')
    elastic_alpha.nodes.info = mock.Mock(side_effect=TransportError)
    elastic_alpha_cluster = ec.ElasticsearchCluster(elastic_alpha, None, dry_run=False)

    next_nodes = [{
        'name': 'el5',
        'clusters_instances': [elastic_alpha_cluster]
    }]

    elastic_hosts = ec.ElasticsearchHosts(remote, next_nodes, dry_run=False)
    with pytest.raises(ec.ElasticsearchClusterError):
        elastic_hosts.wait_for_elasticsearch_up(timedelta(seconds=20))
        assert mocked_sleep.called
    assert elastic_alpha.nodes.info.call_count == 4


def test_cluster_settings_are_unchanged_when_stopped_replication_is_dry_run():
    """Check that cluster routing in dry run mode is truly safe"""
    elasticsearch = Elasticsearch('endpoint:9200')
    elasticsearch.cluster.put_settings = mock.Mock(return_value=True)
    elasticsearchcluster = ec.ElasticsearchCluster(elasticsearch, None, dry_run=True)
    with elasticsearchcluster.stopped_replication():
        assert not elasticsearch.cluster.put_settings.called


def test_split_node_names():
    """split_node_name() support cluster names containing '-'"""
    node_name, cluster_name = ec.ElasticsearchCluster.split_node_name('node1-cluster-name')
    assert node_name == 'node1'
    assert cluster_name == 'cluster-name'


class TestElasticsearchClusters:
    """Test class for Elasticsearch Clusters"""

    def setup_method(self):
        """Setup the test environment."""
        # pylint: disable=attribute-defined-outside-init
        self.elasticsearch1 = Elasticsearch('endpoint:9201')
        self.elasticsearch2 = Elasticsearch('endpoint:9202')
        self.cluster1 = ec.ElasticsearchCluster(self.elasticsearch1, None, dry_run=False)
        self.cluster2 = ec.ElasticsearchCluster(self.elasticsearch2, None, dry_run=False)
        self.clusters = [self.cluster1, self.cluster2]

    def test_flush_markers_on_clusters(self):
        """Test that elasticsearch call to flush markers was properly made."""
        self.elasticsearch1.indices.flush = mock.Mock(return_value=True)
        self.elasticsearch1.indices.flush_synced = mock.Mock(return_value=True)
        self.elasticsearch2.indices.flush = mock.Mock(return_value=True)
        self.elasticsearch2.indices.flush_synced = mock.Mock(return_value=True)
        elasticsearchclusters = ec.ElasticsearchClusters(self.clusters, None)
        elasticsearchclusters.flush_markers(timedelta(seconds=30))
        self.elasticsearch1.indices.flush.assert_called_with(force=True, request_timeout=30)
        self.elasticsearch1.indices.flush_synced.assert_called_with(request_timeout=30)
        self.elasticsearch2.indices.flush.assert_called_with(force=True, request_timeout=30)
        self.elasticsearch2.indices.flush_synced.assert_called_with(request_timeout=30)

    def test_flush_markers_on_clusters_fail(self):
        """Test that when conflict error is raised, execution continues."""
        self.elasticsearch1.indices.flush = mock.Mock(side_effect=ConflictError('test'))
        self.elasticsearch1.indices.flush_synced = mock.Mock(return_value=True)
        self.elasticsearch2.indices.flush = mock.Mock(return_value=True)
        self.elasticsearch2.indices.flush_synced = mock.Mock(return_value=True)
        elasticsearchclusters = ec.ElasticsearchClusters(self.clusters, None)
        elasticsearchclusters.flush_markers(timedelta(seconds=30))
        self.elasticsearch1.indices.flush_synced.assert_called_with(request_timeout=30)
        self.elasticsearch2.indices.flush.assert_called_with(force=True, request_timeout=30)
        self.elasticsearch2.indices.flush_synced.assert_called_with(request_timeout=30)

    def test_flush_markers_on_clusters_fail_synced(self):
        """Test that when conflict error is raised during synced flush, execution continues."""
        self.elasticsearch1.indices.flush = mock.Mock(return_value=True)
        self.elasticsearch1.indices.flush_synced = mock.Mock(side_effect=ConflictError('test'))
        self.elasticsearch2.indices.flush = mock.Mock(return_value=True)
        self.elasticsearch2.indices.flush_synced = mock.Mock(return_value=True)
        elasticsearchclusters = ec.ElasticsearchClusters(self.clusters, None)
        elasticsearchclusters.flush_markers(timedelta(seconds=30))
        self.elasticsearch1.indices.flush_synced.assert_called_with(request_timeout=30)
        self.elasticsearch2.indices.flush.assert_called_with(force=True, request_timeout=30)
        self.elasticsearch2.indices.flush_synced.assert_called_with(request_timeout=30)

    def test_when_all_shards_are_assigned_no_allocation_is_performed(self):
        """Test that shard allocation is not performed when all shards have been assigned on all clusters"""
        self.elasticsearch1.nodes.info = mock.Mock(return_value={'nodes': {'ELASTIC1': {'name': 'el1-alpha'}}})
        self.elasticsearch2.nodes.info = mock.Mock(return_value={'nodes': {'ELASTIC7': {'name': 'el1-beta'}}})
        self.elasticsearch1.cat.shards = mock.Mock(return_value=[
            {'index': 'index1', 'shard': 2, 'state': 'ASSIGNED'},
            {'index': 'index2', 'shard': 4, 'state': 'ASSIGNED'}
        ])
        self.elasticsearch2.cat.shards = mock.Mock(return_value=[
            {'index': 'index3', 'shard': 6, 'state': 'ASSIGNED'},
            {'index': 'index4', 'shard': 7, 'state': 'ASSIGNED'}
        ])
        self.elasticsearch1.cluster.reroute = mock.Mock(return_value=True)
        self.elasticsearch2.cluster.reroute = mock.Mock(return_value=True)
        elasticsearchclusters = ec.ElasticsearchClusters(self.clusters, None)
        elasticsearchclusters.force_allocation_of_all_unassigned_shards()
        assert not self.elasticsearch1.cluster.reroute.called
        assert not self.elasticsearch2.cluster.reroute.called

    def test_force_allocation_of_all_unassigned_shards(self):
        """Test that elasticsearch performs cluster reroute with with unassigned shards on all clusters."""
        self.elasticsearch1.nodes.info = mock.Mock(return_value={'nodes': {'ELASTIC1': {'name': 'el1-alpha'}}})
        self.elasticsearch2.nodes.info = mock.Mock(return_value={'nodes': {'ELASTIC7': {'name': 'el1-beta'}}})
        self.elasticsearch1.cat.shards = mock.Mock(return_value=[
            {'index': 'index1', 'shard': 2, 'state': 'UNASSIGNED'},
            {'index': 'index2', 'shard': 4, 'state': 'ASSIGNED'}
        ])
        self.elasticsearch2.cat.shards = mock.Mock(return_value=[
            {'index': 'index3', 'shard': 6, 'state': 'ASSIGNED'},
            {'index': 'index4', 'shard': 7, 'state': 'UNASSIGNED'}
        ])
        self.elasticsearch1.cluster.reroute = mock.Mock(return_value=True)
        self.elasticsearch2.cluster.reroute = mock.Mock(return_value=True)
        elasticsearchclusters = ec.ElasticsearchClusters(self.clusters, None)
        elasticsearchclusters.force_allocation_of_all_unassigned_shards()
        self.elasticsearch1.cluster.reroute.assert_called_with(retry_failed=True, body={
            'commands': [{
                'allocate_replica': {
                    'index': 'index1', 'shard': 2,
                    'node': 'el1-alpha'
                }
            }]
        })
        self.elasticsearch2.cluster.reroute.assert_called_with(retry_failed=True, body={
            'commands': [{
                'allocate_replica': {
                    'index': 'index4', 'shard': 7,
                    'node': 'el1-beta'
                }
            }]
        })

    def test_force_allocation_of_shards_with_failed_node(self):
        """Test that shard allocation command was called twice after it fails on the first node."""
        self.elasticsearch1.nodes.info = mock.Mock(return_value={'nodes': {
            'ELASTIC1': {'name': 'el1-alpha'}, 'ELASTIC3': {'name': 'el2-alpha'}
        }})
        self.elasticsearch2.nodes.info = mock.Mock(return_value={'nodes': {
            'ELASTIC7': {'name': 'el1-beta'}, 'ELASTIC4': {'name': 'el2-beta'},
        }})
        self.elasticsearch1.cat.shards = mock.Mock(return_value=[
            {'index': 'index1', 'shard': 2, 'state': 'UNASSIGNED'},
            {'index': 'index2', 'shard': 4, 'state': 'ASSIGNED'}
        ])
        self.elasticsearch2.cat.shards = mock.Mock(return_value=[
            {'index': 'index3', 'shard': 6, 'state': 'ASSIGNED'},
            {'index': 'index4', 'shard': 7, 'state': 'UNASSIGNED'}
        ])
        self.elasticsearch1.cluster.reroute = mock.Mock(side_effect=RequestError('test'))
        self.elasticsearch2.cluster.reroute = mock.Mock(side_effect=RequestError('test'))
        elasticsearchclusters = ec.ElasticsearchClusters(self.clusters, None)
        elasticsearchclusters.force_allocation_of_all_unassigned_shards()
        assert self.elasticsearch1.cluster.reroute.call_count == 2
        assert self.elasticsearch2.cluster.reroute.call_count == 2

    def test_stopped_replication(self):
        """Check that context manager stops replication and then starts replication on each cluster."""
        self.elasticsearch1.cluster.put_settings = mock.Mock(return_value=True)
        self.elasticsearch2.cluster.put_settings = mock.Mock(return_value=True)
        elasticsearchclusters = ec.ElasticsearchClusters(self.clusters, None)
        with elasticsearchclusters.stopped_replication():
            self.elasticsearch1.cluster.put_settings.assert_called_with(body={
                'transient': {
                    'cluster.routing.allocation.enable': 'primaries'
                }
            })
            self.elasticsearch2.cluster.put_settings.assert_called_with(body={
                'transient': {
                    'cluster.routing.allocation.enable': 'primaries'
                }
            })

        self.elasticsearch1.cluster.put_settings.assert_called_with(body={
            'transient': {
                'cluster.routing.allocation.enable': 'all'
            }
        })
        self.elasticsearch2.cluster.put_settings.assert_called_with(body={
            'transient': {
                'cluster.routing.allocation.enable': 'all'
            }
        })

    def test_frozen_writes_write_to_index(self):
        """Test that elasticsearch write to index is called to freeze writes"""
        self.elasticsearch1.index = mock.Mock(return_value=True)
        self.elasticsearch2.index = mock.Mock(return_value=True)
        self.elasticsearch1.delete = mock.Mock(return_value=True)
        self.elasticsearch2.delete = mock.Mock(return_value=True)
        reason = Reason('test', 'test_user', 'test_host', task_id='T111222')
        cluster1 = ec.ElasticsearchCluster(self.elasticsearch1, None, dry_run=False)
        cluster2 = ec.ElasticsearchCluster(self.elasticsearch2, None, dry_run=False)
        elasticsearchclusters = ec.ElasticsearchClusters([cluster1, cluster2], None)
        with elasticsearchclusters.frozen_writes(reason):
            assert self.elasticsearch1.index.called
            assert self.elasticsearch2.index.called

        assert self.elasticsearch1.delete.called
        assert self.elasticsearch2.delete.called

    def test_when_frozen_writes_fails_exception_is_raised(self):
        """Test that when elasticsearch write to index fails, an exception is raised

        and a call to delete/unfreeze write is placed
        """
        self.elasticsearch1.index = mock.Mock(side_effect=TransportError('test'))
        self.elasticsearch2.index = mock.Mock(return_value=True)
        self.elasticsearch1.delete = mock.Mock(return_value=True)
        self.elasticsearch2.delete = mock.Mock(return_value=True)
        reason = Reason('test', 'test_user', 'test_host', task_id='T111222')
        elasticsearchclusters = ec.ElasticsearchClusters(self.clusters, None)
        with pytest.raises(ec.ElasticsearchClusterError):
            with elasticsearchclusters.frozen_writes(reason):
                assert self.elasticsearch1.index.called

            assert self.elasticsearch1.delete.called
            assert self.elasticsearch2.delete.called

    def test_when_unfreeze_writes_fails_exception_is_raised(self):
        """Test that when elasticsearch delete doc in index fails, an exception is raised

        and a call to delete/unfreeze write is placed
        """
        self.elasticsearch1.index = mock.Mock(return_value=True)
        self.elasticsearch2.index = mock.Mock(return_value=True)
        self.elasticsearch1.delete = mock.Mock(side_effect=TransportError('test'))
        self.elasticsearch2.delete = mock.Mock(return_value=True)
        reason = Reason('test', 'test_user', 'test_host', task_id='T111222')
        elasticsearchclusters = ec.ElasticsearchClusters(self.clusters, None)
        with pytest.raises(ec.ElasticsearchClusterError):
            with elasticsearchclusters.frozen_writes(reason):
                assert self.elasticsearch1.index.called

            assert self.elasticsearch1.delete.called
            assert self.elasticsearch2.delete.called

    def test_no_call_to_freeze_write_in_dry_run(self):
        """Test that when dry run is enabled, call to write to cluster index to freeze write is not placed"""
        self.elasticsearch1.index = mock.Mock(return_value=True)
        self.elasticsearch2.delete = mock.Mock(return_value=True)
        cluster1 = ec.ElasticsearchCluster(self.elasticsearch1, None, dry_run=True)
        cluster2 = ec.ElasticsearchCluster(self.elasticsearch2, None, dry_run=True)
        reason = Reason('test', 'test_user', 'test_host', task_id='T111222')
        elasticsearchclusters = ec.ElasticsearchClusters([cluster1, cluster2], None)
        with elasticsearchclusters.frozen_writes(reason):
            assert not self.elasticsearch1.index.called
            assert not self.elasticsearch2.delete.called

    def test_wait_for_green_on_all_clusters_elastisearch_call(self):
        """Makes sure the call to elasticsearch.cluster.health is placed for each cluster."""
        self.elasticsearch1.cluster.health = mock.Mock(return_value=True)
        self.elasticsearch2.cluster.health = mock.Mock(return_value=True)
        elasticsearchclusters = ec.ElasticsearchClusters(self.clusters, None)
        elasticsearchclusters.wait_for_green(timedelta(seconds=13))
        assert self.elasticsearch1.cluster.health.called
        assert self.elasticsearch2.cluster.health.called

    @mock.patch('spicerack.elasticsearch_cluster.retry')
    def test_wait_for_green_correct_tries_test(self, retry):
        """Check that the number of tries is correctly computed."""
        self.elasticsearch1.cluster.health = mock.Mock(return_value=True)
        self.elasticsearch2.cluster.health = mock.Mock(return_value=True)
        elasticsearchclusters = ec.ElasticsearchClusters(self.clusters, None)
        elasticsearchclusters.wait_for_green(timedelta(seconds=20))
        assert retry.call_args[1]['tries'] == 2

    @mock.patch('spicerack.elasticsearch_cluster.retry')
    def test_wait_for_green_default_tries_test(self, retry):
        """Checks that a default value of 1 is returned when timeout is less than 10"""
        self.elasticsearch1.cluster.health = mock.Mock(return_value=True)
        self.elasticsearch2.cluster.health = mock.Mock(return_value=True)
        elasticsearchclusters = ec.ElasticsearchClusters(self.clusters, None)
        elasticsearchclusters.wait_for_green(timedelta(seconds=4))
        assert retry.call_args[1]['tries'] == 1

    @mock.patch('spicerack.decorators.time.sleep', return_value=None)
    def test_wait_for_green_retry_test(self, mocked_sleep):
        """Test that the retry is called again when cluster health request throws an exception."""
        self.elasticsearch1.cluster.health = mock.Mock(side_effect=TransportError('test'))
        self.elasticsearch2.cluster.health = mock.Mock(side_effect=TransportError('test'))
        elasticsearchclusters = ec.ElasticsearchClusters(self.clusters, None)
        with pytest.raises(ec.ElasticsearchClusterCheckError):
            elasticsearchclusters.wait_for_green(timedelta(seconds=20))
            assert mocked_sleep.called
            assert self.elasticsearch1.cluster.health.call_count == 2
            assert self.elasticsearch2.cluster.health.call_count == 2

    def test_get_next_clusters_nodes(self):
        """Test that next nodes belong in the same row on each cluster."""
        remote = mock.Mock(spec_set=Remote)
        since = datetime.utcfromtimestamp(20 / 1000)
        cluster1_nodes = {
            'ELASTIC1':
                {'name': 'el1-alpha', 'attributes': {'row': 'row1'}, 'jvm': {'start_time_in_millis': 10}},
            'ELASTIC2':
                {'name': 'el2-alpha', 'attributes': {'row': 'row1'}, 'jvm': {'start_time_in_millis': 10}},
            'ELASTIC3':
                {'name': 'el3-alpha', 'attributes': {'row': 'row1'}, 'jvm': {'start_time_in_millis': 30}},
        }

        cluster2_nodes = {
            'ELASTIC4':
                {'name': 'el3-gamma', 'attributes': {'row': 'row1'}, 'jvm': {'start_time_in_millis': 10}},
            'ELASTIC5':
                {'name': 'el4-gamma', 'attributes': {'row': 'row1'}, 'jvm': {'start_time_in_millis': 10}},
        }
        self.elasticsearch1.nodes.info = mock.Mock(return_value={'nodes': cluster1_nodes})
        self.elasticsearch2.nodes.info = mock.Mock(return_value={'nodes': cluster2_nodes})
        elasticsearchclusters = ec.ElasticsearchClusters(self.clusters, remote, dry_run=False)
        elasticsearchclusters.get_next_clusters_nodes(since, 4)
        nodes_not_restarted = remote.query.call_args[0][0]
        nodes_not_restarted = nodes_not_restarted.split(',')
        nodes_not_restarted.sort()
        assert nodes_not_restarted == ['el1*', 'el2*', 'el3*', 'el4*']

    def test_get_next_clusters_nodes_raises_error_when_size_is_less_than_one(self):
        """Test that next nodes belong in the same row on each cluster."""
        since = datetime.utcfromtimestamp(20 / 1000)
        elasticsearchclusters = ec.ElasticsearchClusters(self.clusters, None, dry_run=False)
        with pytest.raises(ec.ElasticsearchClusterError):
            elasticsearchclusters.get_next_clusters_nodes(since, 0)

    def test_get_next_nodes_returns_less_nodes_than_specified(self):
        """Test that the nodes returned is less than specified based on if they have been restarted for each clusters"""
        remote = mock.Mock(spec_set=Remote)
        since = datetime.utcfromtimestamp(20 / 1000)
        cluster1_nodes = {
            'ELASTIC3':
                {'name': 'el3-alpha', 'attributes': {'row': 'row1'}, 'jvm': {'start_time_in_millis': 30}},
            'ELASTIC4':
                {'name': 'el5-alpha', 'attributes': {'row': 'row2'}, 'jvm': {'start_time_in_millis': 30}},
            'ELASTIC5':
                {'name': 'el6-alpha', 'attributes': {'row': 'row2'}, 'jvm': {'start_time_in_millis': 10}},
        }

        cluster2_nodes = {
            'ELASTIC6':
                {'name': 'el3-beta', 'attributes': {'row': 'row1'}, 'jvm': {'start_time_in_millis': 30}},
            'ELASTIC7':
                {'name': 'el5-beta', 'attributes': {'row': 'row2'}, 'jvm': {'start_time_in_millis': 30}},
            'ELASTIC8':
                {'name': 'el7-beta', 'attributes': {'row': 'row2'}, 'jvm': {'start_time_in_millis': 10}},
        }
        self.elasticsearch1.nodes.info = mock.Mock(return_value={'nodes': cluster1_nodes})
        self.elasticsearch2.nodes.info = mock.Mock(return_value={'nodes': cluster2_nodes})
        elasticsearchclusters = ec.ElasticsearchClusters(self.clusters, remote, dry_run=False)
        elasticsearchclusters.get_next_clusters_nodes(since, 4)
        nodes_not_restarted = remote.query.call_args[0][0]
        nodes_not_restarted = nodes_not_restarted.split(',')
        nodes_not_restarted.sort()
        assert nodes_not_restarted == ['el6*', 'el7*']

    def test_get_next_nodes_most_not_restarted(self):
        """Test to get rows that have the most not restarted nodes first on each cluster."""
        remote = mock.Mock(spec_set=Remote)
        since = datetime.utcfromtimestamp(20 / 1000)
        cluster1_nodes = {
            'ELASTIC4':
                {'name': 'el5-alpha', 'attributes': {'row': 'row2'}, 'jvm': {'start_time_in_millis': 10}},
            'ELASTIC5':
                {'name': 'el6-alpha', 'attributes': {'row': 'row2'}, 'jvm': {'start_time_in_millis': 10}},
            'ELASTIC6':
                {'name': 'el7-alpha', 'attributes': {'row': 'row2'}, 'jvm': {'start_time_in_millis': 30}},
        }

        cluster2_nodes = {
            'ELASTIC7':
                {'name': 'el9-beta', 'attributes': {'row': 'row3'}, 'jvm': {'start_time_in_millis': 10}},
            'ELASTIC8':
                {'name': 'el8-beta', 'attributes': {'row': 'row3'}, 'jvm': {'start_time_in_millis': 50}},
            'ELASTIC9':
                {'name': 'el10-beta', 'attributes': {'row': 'row3'}, 'jvm': {'start_time_in_millis': 30}},
        }
        self.elasticsearch1.nodes.info = mock.Mock(return_value={'nodes': cluster1_nodes})
        self.elasticsearch2.nodes.info = mock.Mock(return_value={'nodes': cluster2_nodes})
        elasticsearchclusters = ec.ElasticsearchClusters(self.clusters, remote, dry_run=False)
        elasticsearchclusters.get_next_clusters_nodes(since, 4)
        nodes_not_restarted = remote.query.call_args[0][0]
        nodes_not_restarted = nodes_not_restarted.split(',')
        nodes_not_restarted.sort()
        assert nodes_not_restarted == ['el5*', 'el6*']

    def test_get_next_nodes_no_rows(self):
        """Test that all nodes have been restarted on all clusters."""
        since = datetime.utcfromtimestamp(20 / 1000)
        cluster1_nodes = {
            'ELASTIC3':
                {'name': 'el3-gamma', 'attributes': {'row': 'row1'}, 'jvm': {'start_time_in_millis': 30}},
            'ELASTIC4':
                {'name': 'el5-gamma', 'attributes': {'row': 'row2'}, 'jvm': {'start_time_in_millis': 87}},
            'ELASTIC5':
                {'name': 'el6-gamma', 'attributes': {'row': 'row2'}, 'jvm': {'start_time_in_millis': 77}},
        }

        cluster2_nodes = {
            'ELASTIC3':
                {'name': 'el4-alpha', 'attributes': {'row': 'row1'}, 'jvm': {'start_time_in_millis': 40}},
            'ELASTIC4':
                {'name': 'el5-gamma', 'attributes': {'row': 'row2'}, 'jvm': {'start_time_in_millis': 89}},
            'ELASTIC5':
                {'name': 'el6-alpha', 'attributes': {'row': 'row2'}, 'jvm': {'start_time_in_millis': 79}},
        }
        self.elasticsearch1.nodes.info = mock.Mock(return_value={'nodes': cluster1_nodes})
        self.elasticsearch2.nodes.info = mock.Mock(return_value={'nodes': cluster2_nodes})
        elasticsearchclusters = ec.ElasticsearchClusters(self.clusters, None)
        result = elasticsearchclusters.get_next_clusters_nodes(since, 2)
        assert result is None

    def test_get_next_nodes_fails_when_rows_are_not_same(self):
        """Test that error is raised when clusters instances of the same node belong to different rows"""
        since = datetime.utcfromtimestamp(20 / 1000)
        cluster1_nodes = {
            'ELASTIC3':
                {'name': 'el3-gamma', 'attributes': {'row': 'row1'}, 'jvm': {'start_time_in_millis': 10}},
            'ELASTIC4':
                {'name': 'el5-gamma', 'attributes': {'row': 'row2'}, 'jvm': {'start_time_in_millis': 87}},
        }

        cluster2_nodes = {
            'ELASTIC3':
                {'name': 'el3-alpha', 'attributes': {'row': 'row6'}, 'jvm': {'start_time_in_millis': 10}},

        }
        self.elasticsearch1.nodes.info = mock.Mock(return_value={'nodes': cluster1_nodes})
        self.elasticsearch2.nodes.info = mock.Mock(return_value={'nodes': cluster2_nodes})
        elasticsearchclusters = ec.ElasticsearchClusters(self.clusters, None)
        with pytest.raises(ec.ElasticsearchClusterError):
            elasticsearchclusters.get_next_clusters_nodes(since, 2)
