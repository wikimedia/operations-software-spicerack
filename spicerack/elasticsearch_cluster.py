"""ElasticsearchCluster module."""
import logging

from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timedelta
from math import floor

import curator

from elasticsearch import Elasticsearch, TransportError

from spicerack.decorators import retry
from spicerack.exceptions import SpicerackError
from spicerack.remote import RemoteHostsAdapter


logger = logging.getLogger(__name__)  # pylint: disable=invalid-name
ELASTICSEARCH_CLUSTERS = {
    'search': {
        'eqiad': 'search.svc.eqiad.wmnet:9200',
        'codfw': 'search.svc.codfw.wmnet:9200',
        'relforge': 'relforge1002.eqiad.wmnet:9200'
    }
}
# TODO: to be moved to puppet


class ElasticsearchClusterError(SpicerackError):
    """Exception class for errors of this module."""


def create_elasticsearch_cluster(name, remote, dry_run=True):
    """Create ElasticsearchCluster instance.

    Arguments:
        name (str): name of the cluster.
        remote (spicerack.remote.Remote): the Remote instance.
        dry_run (bool, optional):  whether this is a DRY-RUN.

    Raises:
        spicerack.elasticsearch_cluster.ElasticsearchClusterError:
            Thrown when the requested cluster configuration is not found.

    Returns:
        spicerack.elasticsearch_cluster.ElasticsearchCluster: ElasticsearchCluster instance.

    """
    try:
        endpoint = ELASTICSEARCH_CLUSTERS['search'][name]
    except KeyError:
        raise ElasticsearchClusterError('No cluster named {name}'.format(name=name))
    return ElasticsearchCluster(Elasticsearch(endpoint), remote, dry_run)


class ElasticsearchHosts(RemoteHostsAdapter):
    """Class for managing elasticsearch nodes."""

    def start_elasticsearch(self):
        """Starts elasticsearch service"""
        logger.info('Stopping elasticsearch on %s', self)
        self._remote_hosts.run_sync('systemctl start elasticsearch')

    def stop_elasticsearch(self):
        """Stops elasticsearch service"""
        logger.info('Starting elasticsearch on %s', self)
        self._remote_hosts.run_sync('systemctl stop elasticsearch')


class ElasticsearchCluster:
    """Class to manage elasticsearch cluster."""

    def __init__(self, elasticsearch, remote, dry_run=True):
        """Initialize ElasticsearchCluster

        Arguments:
            elasticsearch (elasticsearch.Elasticsearch): elasticsearch instance
            remote (spicerack.remote.Remote): the Remote instance.
            dry_run (bool, optional):  whether this is a DRY-RUN.
        """
        self._elasticsearch = elasticsearch
        self._remote = remote
        self._dry_run = dry_run

    def __str__(self):
        """Class string method"""
        return str(self._elasticsearch)

    @contextmanager
    def stopped_replication(self):
        """Context manager to perform actions while the cluster replication is stopped."""
        self._stop_replication()
        try:
            yield
        finally:
            self._start_replication()

    def _stop_replication(self):
        """Stops cluster replication"""
        logger.info('stop replication - %s', self)
        self._do_cluster_routing(
            curator.ClusterRouting(self._elasticsearch, routing_type='allocation', setting='enable',
                                   value='primaries', wait_for_completion=False)
        )

    def _start_replication(self):
        """Starts cluster replication"""
        logger.info('start replication - %s', self)
        self._do_cluster_routing(
            curator.ClusterRouting(self._elasticsearch, routing_type='allocation', setting='enable',
                                   value='all', wait_for_completion=False)
        )

    def _do_cluster_routing(self, cluster_routing):
        """Performs cluster routing of shards.

        Arguments:
            cluster_routing (curator.ClusterRouting): Curator's cluster routing object.
        """
        if self._dry_run:
            cluster_routing.do_dry_run()
        else:
            cluster_routing.do_action()

    def wait_for_green(self, timeout=timedelta(hours=1)):
        """Cluster health status.

        Arguments:
            timeout (datetime.timedelta, optional): timedelta object to represent how long to wait for green status.
        """
        delay = timedelta(seconds=10)
        tries = max(floor(timeout / delay), 1)
        logger.info('waiting for cluster to be green')

        @retry(tries=tries, delay=delay, backoff_mode='constant', exceptions=(TransportError,))
        def inner_wait():
            self._elasticsearch.cluster.health(wait_for_status='green', params={'timeout': '1s'})

        inner_wait()

    def get_next_nodes(self, started_before, size=1):
        """Get the next set of nodes to be upgraded.

        Arguments:
            started_before (datetime.datetime): the time against after which we check if the node has been restarted.
            size (int, optional): size of nodes not restarted in a row.

        Returns:
            spicerack.elasticsearch_cluster.ElasticsearchHosts: ElasticsearchHosts instance.

        """
        nodes = self._elasticsearch.nodes.info()['nodes']
        nodes_to_process = [node for node in nodes.values()
                            if not ElasticsearchCluster._node_has_been_restarted(node, started_before)]
        if not nodes_to_process:
            return None
        rows = ElasticsearchCluster._to_rows(nodes_to_process)
        sorted_rows = sorted(rows.values(), key=len, reverse=True)
        nodes_names = [node['name'] + '*' for node in sorted_rows[0][:size]]
        return ElasticsearchHosts(self._remote.query(','.join(nodes_names)))

    @staticmethod
    def _to_rows(nodes):
        """Arrange nodes in rows, so each node belongs in their respective row.

        Arguments:
            nodes (list): list containing dicts of elasticsearch nodes.

        Returns:
            dict: dict object containing a normalized rows of elasticsearch nodes.
                E.g {'row1': [{'name': 'el1'}, {'name': 'el2'}], 'row2': [{'name': 'el6'}]}

        """
        rows = defaultdict(list)
        for node in nodes:
            row = node['attributes']['row']
            rows[row].append(node)
        return rows

    @staticmethod
    def _node_has_been_restarted(node, since):
        """Check if node has been restarted.

        Arguments:
            node (dict): elasticsearch node
            since (datetime.datetime): the time against after which we check if the node has been restarted.

        Returns:
            bool: True if the node has been restarted after since, false otherwise.

        """
        jvm_start = datetime.utcfromtimestamp(node['jvm']['start_time_in_millis'] / 1000)
        return jvm_start > since
