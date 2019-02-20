"""ElasticsearchCluster module."""
import logging

from collections import defaultdict
from contextlib import contextmanager, ExitStack
from datetime import datetime, timedelta
from math import floor
from random import shuffle
from socket import gethostname

import curator

from elasticsearch import ConflictError, Elasticsearch, RequestError, TransportError
from urllib3.exceptions import HTTPError

from spicerack.decorators import retry
from spicerack.exceptions import SpicerackCheckError, SpicerackError
from spicerack.remote import RemoteHostsAdapter


logger = logging.getLogger(__name__)  # pylint: disable=invalid-name
ELASTICSEARCH_CLUSTERS = {
    'search': {
        'search_eqiad': {
            'production-search-eqiad': 'https://search.svc.eqiad.wmnet:9243',
            'production-search-omega-eqiad': 'https://search.svc.eqiad.wmnet:9443',
            'production-search-psi-eqiad': 'https://search.svc.eqiad.wmnet:9643',
        },
        'search_codfw': {
            'production-search-codfw': 'https://search.svc.codfw.wmnet:9243',
            'production-search-omega-codfw': 'https://search.svc.codfw.wmnet:9443',
            'production-search-psi-codfw': 'https://search.svc.codfw.wmnet:9643',
        },
        'relforge': {
            'relforge-eqiad': 'relforge1002.eqiad.wmnet:9200',
            'relforge-eqiad-small-alpha': 'relforge1002.eqiad.wmnet:9400',
        },
    }
}
# TODO: to be moved to puppet


class ElasticsearchClusterError(SpicerackError):
    """Custom Exception class for errors of this module."""


class ElasticsearchClusterCheckError(SpicerackCheckError):
    """Custom Exception class for check errors of this module."""


def create_elasticsearch_clusters(clustergroup, remote, dry_run=True):
    """Create ElasticsearchClusters instance.

    Arguments:
        clustergroup (str): name of cluster group.
        remote (spicerack.remote.Remote): the Remote instance.
        dry_run (bool, optional):  whether this is a DRY-RUN.

    Raises:
        spicerack.elasticsearch_cluster.ElasticsearchClusterError: Thrown when the requested cluster configuration is
            not found.

    Returns:
        spicerack.elasticsearch_cluster.ElasticsearchClusters: ElasticsearchClusters instance.

    """
    try:
        endpoints = ELASTICSEARCH_CLUSTERS['search'][clustergroup].values()
    except KeyError:
        raise ElasticsearchClusterError('No cluster group named {name}'.format(name=clustergroup))

    clusters = [Elasticsearch(endpoint) for endpoint in endpoints]
    elasticsearch_clusters = [ElasticsearchCluster(cluster, remote, dry_run=dry_run) for cluster in clusters]
    return ElasticsearchClusters(elasticsearch_clusters, remote, dry_run=dry_run)


class ElasticsearchHosts(RemoteHostsAdapter):
    """Remotehosts Adapter for managing elasticsearch nodes."""

    def __init__(self, remote_hosts, nodes, dry_run=True):
        """After calling the super's constructor, initialize other instance variables.

        Arguments:
            remote_hosts (spicerack.remote.RemoteHosts): the instance with the target hosts.
            nodes (list): list of dicts containing clusters hosts belong to.
            dry_run (bool, optional): whether this is a DRY-RUN.
        """
        super().__init__(remote_hosts)
        self._nodes = nodes
        self._dry_run = dry_run

    def get_remote_hosts(self):
        """Returns elasticsearch remote hosts.

        Returns:
            spicerack.remote.RemoteHosts: RemoteHosts instance for this adapter.

        """
        return self._remote_hosts

    def start_elasticsearch(self):
        """Starts all elasticsearch instances."""
        logger.info('Starting all elasticsearch instances on %s', self)
        self._remote_hosts.run_sync('systemctl start "elasticsearch_*@*" --all')

    def stop_elasticsearch(self):
        """Stops all elasticsearch instances."""
        logger.info('Stopping all elasticsearch instances on %s', self)
        self._remote_hosts.run_sync('systemctl stop "elasticsearch_*@*" --all')

    def restart_elasticsearch(self):
        """Restarts all elasticsearch instances."""
        logger.info('Restarting all elasticsearch instances on %s', self)
        self._remote_hosts.run_sync('systemctl restart "elasticsearch_*@*" --all')

    def depool_nodes(self):
        """Depool the hosts."""
        logger.info('Depooling %s', self)
        self._remote_hosts.run_sync('depool')

    def pool_nodes(self):
        """Pool the hosts."""
        logger.info('Pooling %s', self)
        self._remote_hosts.run_sync('pool')

    def wait_for_elasticsearch_up(self, timeout=timedelta(minutes=15)):
        """Check if elasticsearch instances on each node are up.

        Arguments:
            timeout (datetime.timedelta, optional): represent how long to wait for all instances to be up.
        """
        delay = timedelta(seconds=5)
        tries = max(floor(timeout / delay), 1)

        logger.info('waiting for elasticsearch instances to come up on %s', self)

        @retry(tries=tries, delay=delay, backoff_mode='constant',
               exceptions=(ElasticsearchClusterError, ElasticsearchClusterCheckError))
        def inner_wait():
            for node in self._nodes:
                for cluster_instance in node['clusters_instances']:
                    try:
                        if not cluster_instance.is_node_in_cluster_nodes(node['name']):
                            raise ElasticsearchClusterCheckError('Elasticsearch is not up yet')
                    except (TransportError, HTTPError) as e:
                        raise ElasticsearchClusterError('Could not connect to the cluster') from e

        if not self._dry_run:
            inner_wait()


class ElasticsearchClusters:
    """Class to manage elasticsearch clusters."""

    def __init__(self, clusters, remote, dry_run=True):
        """Initialize ElasticsearchClusters.

        Arguments:
            clusters (list): list of :py:class:`spicerack.elasticsearch_cluster.ElasticsearchCluster` instances.
            remote (spicerack.remote.Remote): the Remote instance.
            dry_run (bool, optional): whether this is a DRY-RUN.
        """
        self._clusters = clusters
        self._remote = remote
        self._dry_run = dry_run

    def __str__(self):
        """Class string method."""
        return str(self._clusters)

    def flush_markers(self, timeout=timedelta(seconds=60)):
        """Flush markers on all clusters.

        Arguments:
            timeout (datetime.timedelta, optional): timedelta object for elasticsearch request timeout.
        """
        for cluster in self._clusters:
            cluster.flush_markers(timeout)

    def force_allocation_of_all_unassigned_shards(self):
        """Force allocation of unassigned shards on all clusters."""
        for cluster in self._clusters:
            cluster.force_allocation_of_all_unassigned_shards()

    @contextmanager
    def frozen_writes(self, reason):
        """Freeze all writes to the clusters and then perform operations before unfreezing writes.

        Arguments:
            reason (spicerack.administrative.Reason): Reason for freezing writes.
        """
        logger.info('Freezing writes on %s', self)
        with ExitStack() as stack:
            yield [stack.enter_context(cluster.frozen_writes(reason)) for cluster in self._clusters]

    @contextmanager
    def stopped_replication(self):
        """Stops replication for all clusters."""
        logger.info('stopping replication on %s', self)
        with ExitStack() as stack:
            yield [stack.enter_context(cluster.stopped_replication()) for cluster in self._clusters]

    def wait_for_green(self, timeout=timedelta(hours=1)):
        """Wait for green on all clusters.

        Arguments:
            timeout (datetime.timedelta, optional): timedelta object to represent how long to wait for green status
                on all clusters.
        """
        delay = timedelta(seconds=10)
        tries = max(floor(timeout / delay), 1)
        logger.info('waiting for clusters to be green')

        @retry(tries=tries, delay=delay, backoff_mode='constant', exceptions=(ElasticsearchClusterCheckError,))
        def inner_wait():
            for cluster in self._clusters:
                cluster.check_green()

        inner_wait()

    def get_next_clusters_nodes(self, started_before, size=1):
        """Get next set of cluster nodes for cookbook operations like upgrade, rolling restart etc.

        Arguments:
            started_before (datetime.datetime): the time against after which we check if the node has been restarted.
            size (int, optional): size of nodes not restarted in a row.

        Returns:
            spicerack.elasticsearch_cluster.ElasticsearchHosts: next eligible nodes for ElasticsearchHosts.

        """
        if size < 1:
            raise ElasticsearchClusterCheckError("Size of next nodes must be at least 1")

        nodes_group = self._get_nodes_group()
        nodes_to_process = [node for node in nodes_group.values()
                            if not ElasticsearchClusters._node_has_been_restarted(node, started_before)]
        if not nodes_to_process:
            return None
        rows = ElasticsearchClusters._to_rows(nodes_to_process)
        sorted_rows = sorted(rows.values(), key=len, reverse=True)
        next_nodes = sorted_rows[0][:size]
        node_names = ','.join([node['name'] + '*' for node in next_nodes])
        return ElasticsearchHosts(self._remote.query(node_names), next_nodes, dry_run=self._dry_run)

    def _get_nodes_group(self):
        """Create nodes_group for each nodes.

        Returns:
            dict: merged clusters nodes. e.g::

                {'el5':
                    {'name': 'el5', 'clusters': ['alpha', 'beta],
                    'clusters_instances': [spicerack.elasticsearch_cluster.ElasticsearchCluster],
                        'row': 'row2', 'oldest_start_time': 10
                    }
                }

        """
        nodes_group = {}
        for cluster in self._clusters:
            for cluster_node in cluster.get_nodes().values():
                ElasticsearchClusters._append_to_nodegroup(nodes_group, cluster_node, cluster)
        return nodes_group

    @staticmethod
    def _append_to_nodegroup(nodes_group, cluster_node, cluster):
        """Merge node of different clusters.

        Arguments:
            nodes_group (dict): contains group of nodes that have been merged from different clusters.
            cluster_node (dict): the specific cluster node to add to nodes_group.
            cluster (spicerack.elasticsearch_cluster.ElasticsearchCluster): ElasticsearchCluster for cluster node
        """
        node_name_and_group = ElasticsearchCluster.split_node_name(cluster_node['name'])
        node_name = node_name_and_group['name']
        cluster_group_name = node_name_and_group['cluster_group']

        if node_name not in nodes_group.keys():
            nodes_group[node_name] = {
                'name': node_name,
                'clusters': [cluster_group_name],
                'clusters_instances': [cluster],
                'row': cluster_node['attributes']['row'],
                'oldest_start_time': cluster_node['jvm']['start_time_in_millis']
            }
        else:
            if cluster_group_name not in nodes_group[node_name]['clusters']:
                nodes_group[node_name]['clusters'].append(cluster_group_name)
                nodes_group[node_name]['clusters_instances'].append(cluster)

            if nodes_group[node_name]['row'] != cluster_node['attributes']['row']:
                raise ElasticsearchClusterError('The same nodes of different clusters must be in the same row')

            nodes_group[node_name]['oldest_start_time'] = min(nodes_group[node_name]['oldest_start_time'],
                                                              cluster_node['jvm']['start_time_in_millis'])

    @staticmethod
    def _to_rows(nodes):
        """Arrange nodes in rows, so each node belongs in their respective row.

        Arguments:
            nodes (list): list containing dicts of elasticsearch nodes.

        Returns:
            dict: dict object containing a normalized rows of elasticsearch nodes. For example::

                {'row1': [{'name': 'el1'}, {'name': 'el2'}], 'row2': [{'name': 'el6'}]}

        """
        rows = defaultdict(list)
        for node in nodes:
            rows[node['row']].append(node)
        return rows

    @staticmethod
    def _node_has_been_restarted(node, since):
        """Check if node has been restarted.

        Arguments:
            node (dict): elasticsearch node.
            since (datetime.datetime): the time against after which we check if the node has been restarted.

        Returns:
            bool: True if the node has been restarted after since, false otherwise.

        """
        start_time = datetime.utcfromtimestamp(node['oldest_start_time'] / 1000)
        return start_time > since


class ElasticsearchCluster:
    """Class to manage elasticsearch cluster."""

    def __init__(self, elasticsearch, remote, dry_run=True):
        """Initialize ElasticsearchCluster

        Arguments:
            elasticsearch (elasticsearch.Elasticsearch): elasticsearch instance.
            remote (spicerack.remote.Remote): the Remote instance.
            dry_run (bool, optional):  whether this is a DRY-RUN.

        Todo:
            ``self._hostname`` class member will be replaced by the formatted message obtained via Reason,
            this can't be done right now as it needs to be inline with what
            the MW maint script and the Icinga check do at the moment.
        """
        self._elasticsearch = elasticsearch
        self._remote = remote
        self._dry_run = dry_run
        self._hostname = gethostname()
        self._freeze_writes_index = 'mw_cirrus_metastore'
        self._freeze_writes_doc_type = 'mw_cirrus_metastore'

    def __str__(self):
        """Class string method"""
        return str(self._elasticsearch)

    def get_nodes(self):
        """Get all Elasticsearch Nodes.

        Returns:
            dict: dictionary of elasticsearch nodes in the cluster.

        """
        return self._elasticsearch.nodes.info()['nodes']

    def is_node_in_cluster_nodes(self, node):
        """Checks if node is in a list of elasticsearch cluster nodes.

        Arguments:
            node (str): the elasticsearch host.

        Returns:
            bool: :py:data:`True` if node is present and :py:data:`False` if not.

        """
        nodes_names = [ElasticsearchCluster.split_node_name(node['name'])['name'] for node in self.get_nodes().values()]
        if node in nodes_names:
            return True

        return False

    @staticmethod
    def split_node_name(node_name):
        """Split node name into hostname and cluster group name.

        Arguments:
            node_name (str): node name containing hostname and cluster name separated by ``-``.

        Returns:
            dict: dictionary containing the node name and the cluster name.

        """
        node_name_and_group = {}
        splitted_names = node_name.split('-')
        node_name_and_group['name'] = splitted_names[0]
        node_name_and_group['cluster_group'] = splitted_names[1]
        return node_name_and_group

    @contextmanager
    def stopped_replication(self):
        """Context manager to perform actions while the cluster replication is stopped."""
        self._stop_replication()
        try:
            yield
        finally:
            self._start_replication()

    def _stop_replication(self):
        """Stops cluster replication."""
        logger.info('stop replication - %s', self)
        self._do_cluster_routing(
            curator.ClusterRouting(self._elasticsearch, routing_type='allocation', setting='enable',
                                   value='primaries', wait_for_completion=False)
        )

    def _start_replication(self):
        """Starts cluster replication."""
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

    def check_green(self):
        """Cluster health status.

        Raises:
            spicerack.elasticsearch_cluster.ElasticsearchClusterCheckError:
                This is raised when request times and cluster is not green.

        """
        try:
            self._elasticsearch.cluster.health(wait_for_status='green', params={'timeout': '1s'})
        except (TransportError, HTTPError) as e:
            raise ElasticsearchClusterCheckError('Error while waiting for green') from e

    @contextmanager
    def frozen_writes(self, reason):
        """Stop writes to all elasticsearch indices and enable them on exit.

        Arguments:
            reason (spicerack.administrative.Reason): Reason for freezing writes.
        """
        self._freeze_writes(reason)
        try:
            yield
        finally:
            self._unfreeze_writes()

    def _freeze_writes(self, reason):
        """Stop writes to all elasticsearch indices.

        Arguments:
            reason (spicerack.administrative.Reason): Reason for freezing writes.
        """
        doc = {'host': self._hostname, 'timestamp': datetime.utcnow().timestamp(), 'reason': str(reason)}
        logger.info('Freezing all indices in %s', self)
        if self._dry_run:
            return
        try:
            self._elasticsearch.index(index=self._freeze_writes_index, doc_type=self._freeze_writes_doc_type,
                                      id='freeze-everything', body=doc)
        except TransportError as e:
            raise ElasticsearchClusterError(
                'Encountered error while creating document to freeze cluster writes'
            ) from e

    def _unfreeze_writes(self):
        """Enable writes on all elasticsearch indices"""
        logger.info('Unfreezing all indices in %s', self)
        if self._dry_run:
            return
        try:
            self._elasticsearch.delete(index=self._freeze_writes_index, doc_type=self._freeze_writes_doc_type,
                                       id='freeze-everything')
        except TransportError as e:
            raise ElasticsearchClusterError(
                'Encountered error while deleting document to unfreeze cluster writes'
            ) from e

    def flush_markers(self, timeout=timedelta(seconds=60)):
        """Flush markers unsynced.

        Note:
            ``flush`` and ``flush_synced`` are called here because from experience, it results in fewer shards not
            syncing. This also makes the recovery faster.

        Arguments:
            timeout (datetime.timedelta): timedelta object for elasticsearch request timeout.
        """
        logger.info('flush markers on %s', self)
        try:
            self._elasticsearch.indices.flush(force=True, request_timeout=timeout.seconds)
        except ConflictError:
            logger.warning('Not all shards were flushed on %s.', self)

        try:
            self._elasticsearch.indices.flush_synced(request_timeout=timeout.seconds)
        except ConflictError:
            logger.warning('Not all shards were synced flushed on %s.', self)

    def force_allocation_of_all_unassigned_shards(self):
        """Manual allocation of unassigned shards."""
        cluster_nodes_names = [node['name'] for node in self.get_nodes().values()]
        unassigned_shards = self._get_unassigned_shards()
        for unassigned_shard in unassigned_shards:
            self._force_allocation_of_shard(unassigned_shard, cluster_nodes_names)

    def _get_unassigned_shards(self):
        """Fetch unassigned shards.

        Returns:
            list: list of unassigned shards from the cluster.

        """
        shards = self._elasticsearch.cat.shards(format='json', h='index,shard,state')
        return [s for s in shards if s['state'] == 'UNASSIGNED']

    def _force_allocation_of_shard(self, shard, nodes):
        """Force allocation of shard.

        Arguments:
            shard (dict): shard of an index to be relocated.
            nodes (list): list of nodes to allocate shards to.

        Todo:
            It was found that forcing allocation of shards may perform better in terms of speed than
            letting elasticsearch do its recovery on its own.
            We should verify from time to time that elastic recovery performance has not gone better
            and remove this step if proven unnecessary.
        """
        # shuffle nodes so that we don't allocate all shards on the same node
        shuffle(nodes)
        for node in nodes:
            try:
                logger.info('Trying to allocate [%s:%s] on [%s]', shard['index'], shard['shard'], node)
                self._elasticsearch.cluster.reroute(retry_failed=True, body={
                    'commands': [{
                        'allocate_replica': {
                            'index': shard['index'], 'shard': shard['shard'],
                            'node': node
                        }
                    }]
                })
                # successful allocation, we can exit
                logger.info('allocation successful')
                break
            except RequestError:
                # error allocating shard, let's try the next node
                logger.info('Could not reallocate shard [%s:%s] on %s', shard['index'], shard['shard'], node)
        else:
            logger.warning('Could not reallocate shard [%s:%s] on any node', shard['index'], shard['shard'])
