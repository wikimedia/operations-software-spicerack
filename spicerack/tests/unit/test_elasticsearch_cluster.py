"""ElasticsearchCluster module test."""
from datetime import datetime, timedelta
from unittest import mock

import pytest

from cumin import NodeSet
from elasticsearch import Elasticsearch, TransportError

from spicerack import elasticsearch_cluster as ec
from spicerack.remote import Remote
from spicerack.tests import elasticsearch_too_old


pytestmark = pytest.mark.skipif(  # pylint: disable=invalid-name
    elasticsearch_too_old(), reason='Requires more recent elasticsearch module'
)


def test_create_elasticsearch_cluster():
    """It should return an instance of ElasticsearchCluster."""
    target = ec.create_elasticsearch_cluster('eqiad', None)
    assert isinstance(target, ec.ElasticsearchCluster)


def test_create_elasticsearch_cluster_fail():
    """It should throw an ElasticsearchCluster Exception."""
    with pytest.raises(ec.ElasticsearchClusterError, match='No cluster named wmnet'):
        ec.create_elasticsearch_cluster('wmnet', None)


def test_elasticsearch_remote_host_factory():
    """It should return an instance of ElasticsearchHosts."""
    target = ec.elasticsearch_remote_hosts_factory({}, NodeSet('host[1-9]'))
    assert isinstance(target, ec.ElasticsearchHosts)


def test_start_elasticsearch():
    """Test that start elasticsearch service is called correctly."""
    elastic_hosts = ec.ElasticsearchHosts({}, hosts=NodeSet('host1'))
    elastic_hosts.run_sync = mock.Mock(return_value=iter(()))
    elastic_hosts.start_elasticsearch()
    elastic_hosts.run_sync.assert_called_with('systemctl start elasticsearch')


def test_stop_elasticsearch():
    """Test that stop elasticsearch service is called correctly."""
    elastic_hosts = ec.ElasticsearchHosts({}, hosts=NodeSet('host1'))
    elastic_hosts.run_sync = mock.Mock(return_value=iter(()))
    elastic_hosts.stop_elasticsearch()
    elastic_hosts.run_sync.assert_called_with('systemctl stop elasticsearch')


def test_stopped_replication():
    """Check that context manager stops replication and then starts replication."""
    elasticsearch = Elasticsearch('endpoint:9200')
    elasticsearch.cluster.put_settings = mock.Mock(return_value=True)
    elasticsearchcluster = ec.ElasticsearchCluster(elasticsearch, None, dry_run=False)
    with elasticsearchcluster.stopped_replication():
        elasticsearch.cluster.put_settings.assert_called_with(body={
            'transient': {
                'cluster.routing.allocation.enable': 'primaries'
            }
        })
    elasticsearch.cluster.put_settings.assert_called_with(body={
        'transient': {
            'cluster.routing.allocation.enable': 'all'
        }
    })


def test_cluster_settings_are_unchanged_when_stopped_replication_is_dry_run():
    """Check that cluster routing in dry run mode is truly safe"""
    elasticsearch = Elasticsearch('endpoint:9200')
    elasticsearch.cluster.put_settings = mock.Mock(return_value=True)
    elasticsearchcluster = ec.ElasticsearchCluster(elasticsearch, None, dry_run=True)
    with elasticsearchcluster.stopped_replication():
        elasticsearch.cluster.put_settings.assert_not_called()


def test_wait_for_green_elasticsearch_call():
    """Makes sure the call to elasticsearch.cluster.health is placed."""
    mocked_elastic = mock.Mock()
    mocked_elastic.cluster.health.return_value = True
    elasticsearchcluster = ec.ElasticsearchCluster(mocked_elastic, None, dry_run=False)
    elasticsearchcluster.wait_for_green(timedelta(seconds=13))
    mocked_elastic.cluster.health.assert_called()


@mock.patch('spicerack.elasticsearch_cluster.retry')
def test_wait_for_green_correct_tries_test(retry):
    """Check that the number of tries is correctly computed."""
    mocked_elastic = mock.Mock()
    mocked_elastic.cluster.health.return_value = True
    elasticsearchcluster = ec.ElasticsearchCluster(mocked_elastic, None, dry_run=False)
    elasticsearchcluster.wait_for_green(timedelta(seconds=20))
    assert retry.call_args[1]['tries'] == 2


@mock.patch('spicerack.decorators.time.sleep', return_value=None)
def test_wait_for_green_retry_test(mocked_sleep):
    """Test that the retry is called again when elasticsearch request throws an exception."""
    mocked_elastic = mock.Mock()
    mocked_elastic.cluster.health.side_effect = TransportError('test')
    elasticsearchcluster = ec.ElasticsearchCluster(mocked_elastic, None, dry_run=False)
    with pytest.raises(TransportError):
        elasticsearchcluster.wait_for_green(timedelta(seconds=20))
    print(mocked_sleep.mock_calls)
    assert mocked_elastic.cluster.health.call_count == 2


@mock.patch('spicerack.elasticsearch_cluster.retry')
def test_wait_for_green_default_tries_test(retry):
    """Checks that a default value of 1 is returned when timeout is less than 10"""
    mocked_elastic = mock.Mock()
    mocked_elastic.cluster.health.return_value = True
    elasticsearchcluster = ec.ElasticsearchCluster(mocked_elastic, None, dry_run=False)
    elasticsearchcluster.wait_for_green(timedelta(seconds=2))
    assert retry.call_args[1]['tries'] == 1


def test_get_next_nodes():
    """Test that next nodes belong in the same row."""
    remote = mock.MagicMock(spec_set=Remote)
    since = datetime.utcfromtimestamp(20 / 1000)
    nodes = {
        'ELASTIC1':
            {'name': 'el1', 'attributes': {'row': 'row1'}, 'jvm': {'start_time_in_millis': 10}},
        'ELASTIC2':
            {'name': 'el2', 'attributes': {'row': 'row1'}, 'jvm': {'start_time_in_millis': 10}},
        'ELASTIC3':
            {'name': 'el3', 'attributes': {'row': 'row2'}, 'jvm': {'start_time_in_millis': 30}},
    }
    elasticsearch = Elasticsearch('test-endpoint:9200')
    elasticsearch.nodes.info = mock.Mock(return_value={'nodes': nodes})
    elasticsearchcluster = ec.ElasticsearchCluster(elasticsearch, remote, dry_run=False)
    elasticsearchcluster.get_next_nodes(since, 2)
    nodes_not_restarted = remote.query.call_args[0][0]
    nodes_not_restarted = nodes_not_restarted.split(',')
    nodes_not_restarted.sort()
    assert nodes_not_restarted == ['el1*', 'el2*']


def test_get_next_nodes_returns_less_nodes_than_specified():
    """Test that the nodes returned is less than specified based on if they have been restarted."""
    remote = mock.MagicMock(spec_set=Remote)
    since = datetime.utcfromtimestamp(20 / 1000)
    nodes = {
        'ELASTIC3':
            {'name': 'el3', 'attributes': {'row': 'row1'}, 'jvm': {'start_time_in_millis': 30}},
        'ELASTIC4':
            {'name': 'el5', 'attributes': {'row': 'row2'}, 'jvm': {'start_time_in_millis': 30}},
        'ELASTIC5':
            {'name': 'el6', 'attributes': {'row': 'row2'}, 'jvm': {'start_time_in_millis': 10}},
    }
    elasticsearch = Elasticsearch('test-endpoint:9200')
    elasticsearch.nodes.info = mock.Mock(return_value={'nodes': nodes})
    elasticsearchcluster = ec.ElasticsearchCluster(elasticsearch, remote, dry_run=False)
    elasticsearchcluster.get_next_nodes(since, 2)
    node_not_restarted = remote.query.call_args[0][0]
    assert node_not_restarted == 'el6*'


def test_get_next_nodes_most_not_restarted():
    """Test to get row that have the most not restarted nodes first."""
    remote = mock.MagicMock(spec_set=Remote)
    since = datetime.utcfromtimestamp(20 / 1000)
    nodes = {
        'ELASTIC1':
            {'name': 'el1', 'attributes': {'row': 'row1'}, 'jvm': {'start_time_in_millis': 10}},
        'ELASTIC4':
            {'name': 'el5', 'attributes': {'row': 'row2'}, 'jvm': {'start_time_in_millis': 10}},
        'ELASTIC5':
            {'name': 'el6', 'attributes': {'row': 'row2'}, 'jvm': {'start_time_in_millis': 10}},
        'ELASTIC6':
            {'name': 'el7', 'attributes': {'row': 'row2'}, 'jvm': {'start_time_in_millis': 30}},
    }
    elasticsearch = Elasticsearch('test-endpoint:9200')
    elasticsearch.nodes.info = mock.Mock(return_value={'nodes': nodes})
    elasticsearchcluster = ec.ElasticsearchCluster(elasticsearch, remote, dry_run=False)
    elasticsearchcluster.get_next_nodes(since, 2)
    nodes_not_restarted = remote.query.call_args[0][0]
    nodes_not_restarted = nodes_not_restarted.split(',')
    nodes_not_restarted.sort()
    assert nodes_not_restarted == ['el5*', 'el6*']


def test_get_next_nodes_no_rows():
    """Test that all nodes have been restarted."""
    since = datetime.utcfromtimestamp(20 / 1000)
    nodes = {
        'ELASTIC2':
            {'name': 'el2', 'attributes': {'row': 'row1'}, 'jvm': {'start_time_in_millis': 30}},
        'ELASTIC3':
            {'name': 'el3', 'attributes': {'row': 'row1'}, 'jvm': {'start_time_in_millis': 30}},
        'ELASTIC4':
            {'name': 'el5', 'attributes': {'row': 'row2'}, 'jvm': {'start_time_in_millis': 87}},
        'ELASTIC5':
            {'name': 'el6', 'attributes': {'row': 'row2'}, 'jvm': {'start_time_in_millis': 77}},
    }
    elasticsearch = Elasticsearch('test-endpoint:9200')
    elasticsearch.nodes.info = mock.Mock(return_value={'nodes': nodes})
    elasticsearchcluster = ec.ElasticsearchCluster(elasticsearch, None, dry_run=False)
    result = elasticsearchcluster.get_next_nodes(since, 2)
    assert result is None
