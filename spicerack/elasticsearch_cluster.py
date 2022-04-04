"""ElasticsearchCluster module."""
import logging
from collections import defaultdict
from contextlib import ExitStack, contextmanager
from datetime import datetime, timedelta
from math import floor
from random import shuffle
from typing import DefaultDict, Dict, Iterable, Iterator, List, Optional, Sequence

import curator
from elasticsearch import ConflictError, Elasticsearch, RequestError, TransportError
from urllib3.exceptions import HTTPError
from wmflib.prometheus import Prometheus

from spicerack.administrative import Reason
from spicerack.decorators import retry
from spicerack.exceptions import SpicerackCheckError, SpicerackError
from spicerack.remote import Remote, RemoteHosts, RemoteHostsAdapter

logger = logging.getLogger(__name__)


class ElasticsearchClusterError(SpicerackError):
    """Custom Exception class for errors of this module."""


class ElasticsearchClusterCheckError(SpicerackCheckError):
    """Custom Exception class for check errors of this module."""


def create_elasticsearch_clusters(
    configuration: Dict[str, Dict[str, Dict[str, str]]],
    clustergroup: str,
    write_queue_datacenters: Sequence[str],
    remote: Remote,
    prometheus: Prometheus,
    dry_run: bool = True,
) -> "ElasticsearchClusters":
    """Create ElasticsearchClusters instance.

    Arguments:
        clustergroup (str): name of cluster group.
        write_queue_datacenters (Sequence[str]): Sequence of which core DCs to query write queues for.
        remote (spicerack.remote.Remote): the Remote instance.
        prometheus (wmflib.prometheus.Prometheus): the prometheus instance.
        dry_run (bool, optional):  whether this is a DRY-RUN.

    Raises:
        spicerack.elasticsearch_cluster.ElasticsearchClusterError: Thrown when the requested cluster configuration is
            not found.

    Returns:
        spicerack.elasticsearch_cluster.ElasticsearchClusters: ElasticsearchClusters instance.

    """
    try:
        endpoints = configuration["search"][clustergroup].values()
    except KeyError as e:
        raise ElasticsearchClusterError(f"No cluster group named {clustergroup}") from e

    clusters = [Elasticsearch(endpoint) for endpoint in endpoints]
    elasticsearch_clusters = [ElasticsearchCluster(cluster, remote, dry_run=dry_run) for cluster in clusters]
    return ElasticsearchClusters(
        elasticsearch_clusters,
        remote,
        prometheus,
        write_queue_datacenters,
        dry_run=dry_run,
    )


class ElasticsearchHosts(RemoteHostsAdapter):
    """Remotehosts Adapter for managing elasticsearch nodes."""

    def __init__(
        self,
        remote_hosts: RemoteHosts,
        nodes: Sequence["NodesGroup"],
        dry_run: bool = True,
    ) -> None:
        """After calling the super's constructor, initialize other instance variables.

        Arguments:
            remote_hosts (spicerack.remote.RemoteHosts): the instance with the target hosts.
            nodes (list): list of dicts containing clusters hosts belong to.
            dry_run (bool, optional): whether this is a DRY-RUN.

        """
        super().__init__(remote_hosts)
        self._nodes = nodes
        self._dry_run = dry_run

    def get_remote_hosts(self) -> RemoteHosts:
        """Returns elasticsearch remote hosts.

        Returns:
            spicerack.remote.RemoteHosts: RemoteHosts instance for this adapter.

        """
        return self._remote_hosts

    def start_elasticsearch(self) -> None:
        """Starts all elasticsearch instances."""
        self._systemctl_for_each_instance("start")

    def stop_elasticsearch(self) -> None:
        """Stops all elasticsearch instances."""
        self._systemctl_for_each_instance("stop")

    def restart_elasticsearch(self) -> None:
        """Restarts all elasticsearch instances."""
        self._systemctl_for_each_instance("restart")

    def _systemctl_for_each_instance(self, action: str) -> None:
        logger.info("%s all elasticsearch instances on %s", action, self)
        self._remote_hosts.run_sync(f"cat /etc/elasticsearch/instances | xargs systemctl {action}")

    def depool_nodes(self) -> None:
        """Depool the hosts."""
        logger.info("Depooling %s", self)
        self._remote_hosts.run_sync("depool")

    def pool_nodes(self) -> None:
        """Pool the hosts."""
        logger.info("Pooling %s", self)
        self._remote_hosts.run_sync("pool")

    def wait_for_elasticsearch_up(self, timeout: timedelta = timedelta(minutes=15)) -> None:
        """Check if elasticsearch instances on each node are up.

        Arguments:
            timeout (datetime.timedelta, optional): represent how long to wait for all instances to be up.

        """
        delay = timedelta(seconds=5)
        tries = max(floor(timeout / delay), 1)

        logger.info("waiting for elasticsearch instances to come up on %s", self)

        @retry(
            tries=tries,
            delay=delay,
            backoff_mode="constant",
            exceptions=(ElasticsearchClusterError, ElasticsearchClusterCheckError),
        )
        def inner_wait() -> None:
            for node in self._nodes:
                node.check_all_nodes_up()

        if not self._dry_run:
            inner_wait()


class ElasticsearchClusters:
    """Class to manage elasticsearch clusters."""

    def __init__(
        self,
        clusters: Sequence["ElasticsearchCluster"],
        remote: Remote,
        prometheus: Prometheus,
        write_queue_datacenters: Sequence[str],
        dry_run: bool = True,
    ) -> None:
        """Initialize ElasticsearchClusters.

        Arguments:
            clusters (list): list of :py:class:`spicerack.elasticsearch_cluster.ElasticsearchCluster` instances.
            remote (spicerack.remote.Remote): the Remote instance.
            prometheus (wmflib.prometheus.Prometheus): the prometheus instance.
            write_queue_datacenters (Sequence[str]): Sequence of which core DCs to query write queues for.
            dry_run (bool, optional): whether this is a DRY-RUN.

        """
        self._clusters = clusters
        self._remote = remote
        self._prometheus = prometheus
        self._write_queue_datacenters = write_queue_datacenters
        self._dry_run = dry_run

    def __str__(self) -> str:
        """Class string method."""
        return str(self._clusters)

    def flush_markers(self, timeout: timedelta = timedelta(seconds=60)) -> None:
        """Flush markers on all clusters.

        Arguments:
            timeout (datetime.timedelta, optional): timedelta object for elasticsearch request timeout.

        """
        for cluster in self._clusters:
            cluster.flush_markers(timeout)

    def force_allocation_of_all_unassigned_shards(self) -> None:
        """Force allocation of unassigned shards on all clusters."""
        for cluster in self._clusters:
            cluster.force_allocation_of_all_unassigned_shards()

    @contextmanager
    def frozen_writes(self, reason: Reason) -> Iterator[List[None]]:
        """Freeze all writes to the clusters and then perform operations before unfreezing writes.

        Arguments:
            reason (spicerack.administrative.Reason): Reason for freezing writes.

        Yields:
            list: a side-effect list of :py:data:`None`, as a result of the stack of context managers.

        """
        logger.info("Freezing writes on %s", self)
        with ExitStack() as stack:
            yield [stack.enter_context(cluster.frozen_writes(reason)) for cluster in self._clusters]

    @contextmanager
    def stopped_replication(self) -> Iterator[List[None]]:
        """Stops replication for all clusters.

        Yields:
            list: a side-effect list of :py:data:`None`, as a result of the stack of context managers.

        """
        logger.info("stopping replication on %s", self)
        with ExitStack() as stack:
            yield [stack.enter_context(cluster.stopped_replication()) for cluster in self._clusters]

    def wait_for_green(self, timeout: timedelta = timedelta(hours=1)) -> None:
        """Wait for green on all clusters.

        Arguments:
            timeout (datetime.timedelta, optional): timedelta object to represent how long to wait for green status
                on all clusters.

        """
        delay = timedelta(seconds=10)
        tries = max(floor(timeout / delay), 1)
        logger.info("waiting for clusters to be green")

        @retry(
            tries=tries,
            delay=delay,
            backoff_mode="constant",
            exceptions=(ElasticsearchClusterCheckError,),
        )
        def inner_wait() -> None:
            for cluster in self._clusters:
                cluster.check_green()

        inner_wait()

    def wait_for_yellow_w_no_moving_shards(self, timeout: timedelta = timedelta(hours=1)) -> None:
        """Wait for a yellow cluster status with no relocating or initializing shards.

        Arguments:
            timeout (datetime.timedelta, optional): timedelta object to represent how long to wait
                 for no yellow status with no initializing or relocating shards on all clusters.

        """
        delay = timedelta(seconds=10)
        tries = max(floor(timeout / delay), 1)
        logger.info("waiting for clusters to be yellow with no initializing or relocating shards")

        @retry(
            tries=tries,
            delay=delay,
            backoff_mode="constant",
            exceptions=(ElasticsearchClusterCheckError,),
        )
        def inner_wait() -> None:
            for cluster in self._clusters:
                cluster.check_yellow_w_no_moving_shards()

        inner_wait()

    def get_next_clusters_nodes(self, started_before: datetime, size: int = 1) -> Optional[ElasticsearchHosts]:
        """Get next set of cluster nodes for cookbook operations like upgrade, rolling restart etc.

        Nodes are selected from the row with the least restarted nodes. This ensures that a row is fully upgraded
        before moving to the next row. Since shards cannot move to a node with an older version of elasticsearch,
        this should help to keep all shards allocated at all times.

        Arguments:
            started_before (datetime.datetime): the time against after which we check if the node has been restarted.
            size (int, optional): size of nodes not restarted in a row.

        Returns:
            spicerack.elasticsearch_cluster.ElasticsearchHosts: next eligible nodes for ElasticsearchHosts or
                :py:data:`None` when all nodes have been processed.

        """
        if size < 1:
            raise ElasticsearchClusterError("Size of next nodes must be at least 1")

        nodes_group = self._get_nodes_group()
        nodes_to_process = [node for node in nodes_group if not node.restarted_since(started_before)]
        if not nodes_to_process:
            return None
        rows = ElasticsearchClusters._to_rows(nodes_to_process)
        sorted_rows = sorted(rows.values(), key=len)
        next_nodes = sorted_rows[0][:size]
        node_names = ",".join([node.fqdn for node in next_nodes])
        return ElasticsearchHosts(self._remote.query(node_names), next_nodes, dry_run=self._dry_run)

    def _get_nodes_group(self) -> Iterable["NodesGroup"]:
        """Create nodes_group for each nodes.

        Returns:
            dict: merged clusters nodes.

        """
        nodes_group: Dict[str, NodesGroup] = {}
        for cluster in self._clusters:
            for json_node in cluster.get_nodes().values():
                node_name = json_node["attributes"]["hostname"]

                if node_name not in nodes_group:
                    nodes_group[node_name] = NodesGroup(json_node, cluster)
                else:
                    nodes_group[node_name].accumulate(json_node, cluster)
        return nodes_group.values()

    @staticmethod
    def _to_rows(nodes: Sequence["NodesGroup"]) -> DefaultDict[str, List["NodesGroup"]]:
        """Arrange nodes in rows, so each node belongs in their respective row.

        Arguments:
            nodes (list): list containing dicts of elasticsearch nodes.

        Returns:
            defaultdict: defaultdict object containing a normalized rows of elasticsearch nodes. For example::

                {'row1': [{'name': 'el1'}, {'name': 'el2'}], 'row2': [{'name': 'el6'}]}

        """
        rows: DefaultDict[str, List[NodesGroup]] = defaultdict(list)
        for node in nodes:
            rows[node.row].append(node)
        return rows

    def reset_indices_to_read_write(self) -> None:
        """Reset all readonly indices to read/write.

        In some cases (running low on disk space), indices are switched to
        readonly. This method will update all readonly indices to read/write.
        """
        for cluster in self._clusters:
            cluster.reset_indices_to_read_write()

    @retry(
        tries=60,
        delay=timedelta(seconds=60),
        backoff_mode="constant",
        exceptions=(ElasticsearchClusterCheckError,),
    )
    def wait_for_all_write_queues_empty(self) -> None:
        """Wait for all relevant CirrusSearch write queues to be empty.

        Checks the Prometheus server in each of the CORE_DATACENTERS

        At most waits for 60*60 seconds = 1 hour.

        Does not retry if prometheus returns empty results for all datacenters.
        """
        # We expect all DCs except one to return empty results, but we have a problem if all return empty
        have_received_results = False

        for dc in self._write_queue_datacenters:
            query = (
                "kafka_burrow_partition_lag{"
                '    group="cpjobqueue-cirrusSearchElasticaWrite",'
                '    topic=~"[[:alpha:]]*.cpjobqueue.partitioned.mediawiki.job.cirrusSearchElasticaWrite"'
                "}"
            )
            # Query returns a list of dictionaries each of format {'metric': {}, 'value': [$timestamp, $value]}
            results = self._prometheus.query(query, dc)
            if not results:
                logger.info("Prometheus returned no results for query %s in dc %s", query, dc)
                continue

            have_received_results = True

            # queue_results => (topic, partition, value)
            queue_results = [
                (
                    partitioned_result["metric"]["topic"],
                    partitioned_result["metric"]["partition"],
                    int(partitioned_result["value"][1]),
                )
                for partitioned_result in results
            ]
            logger.debug("Prom query %s returned queue_results of %s", query, queue_results)

            # If any of the partitions are non-empty, raise an error
            for (topic, partition, queue_size) in queue_results:
                if queue_size > 0:
                    raise ElasticsearchClusterCheckError(
                        f"Write queue not empty (had value of {queue_size}) for partition {partition} of topic {topic}."
                    )
        if not have_received_results:
            raise ElasticsearchClusterError(
                f"Prometheus query {query} returned empty response for all dcs in {self._write_queue_datacenters}, "
                f"is query correct?"
            )


class ElasticsearchCluster:
    """Class to manage elasticsearch cluster."""

    def __init__(self, elasticsearch: Elasticsearch, remote: Remote, dry_run: bool = True) -> None:
        """Initialize ElasticsearchCluster.

        Arguments:
            elasticsearch (elasticsearch.Elasticsearch): elasticsearch instance.
            remote (spicerack.remote.Remote): the Remote instance.
            dry_run (bool, optional):  whether this is a DRY-RUN.

        """
        self._elasticsearch = elasticsearch
        self._remote = remote
        self._dry_run = dry_run
        self._freeze_writes_index: str = "mw_cirrus_metastore"
        self._freeze_writes_doc_type: str = "mw_cirrus_metastore"

    def __str__(self) -> str:
        """Class string method."""
        return str(self._elasticsearch)

    def get_nodes(self) -> Dict:
        """Get all Elasticsearch Nodes.

        Returns:
            dict: dictionary of elasticsearch nodes in the cluster.

        """
        try:
            return self._elasticsearch.nodes.info()["nodes"]
        except (TransportError, HTTPError) as e:
            raise ElasticsearchClusterError("Could not connect to the cluster") from e

    def is_node_in_cluster_nodes(self, node: str) -> bool:
        """Checks if node is in a list of elasticsearch cluster nodes.

        Arguments:
            node (str): the elasticsearch host.

        Returns:
            bool: :py:data:`True` if node is present and :py:data:`False` if not.

        """
        nodes_names = [node["attributes"]["hostname"] for node in self.get_nodes().values()]
        if node in nodes_names:
            return True

        return False

    @contextmanager
    def stopped_replication(self) -> Iterator[None]:
        """Context manager to perform actions while the cluster replication is stopped."""
        self._stop_replication()
        try:
            yield
        finally:
            self._start_replication()

    def _stop_replication(self) -> None:
        """Stops cluster replication."""
        logger.info("stop replication - %s", self)
        self._do_cluster_routing(
            curator.ClusterRouting(
                self._elasticsearch,
                routing_type="allocation",
                setting="enable",
                value="primaries",
                wait_for_completion=False,
            )
        )

    def _start_replication(self) -> None:
        """Starts cluster replication."""
        logger.info("start replication - %s", self)
        self._do_cluster_routing(
            curator.ClusterRouting(
                self._elasticsearch,
                routing_type="allocation",
                setting="enable",
                value="all",
                wait_for_completion=False,
            )
        )

    def _do_cluster_routing(self, cluster_routing: curator.ClusterRouting) -> None:
        """Performs cluster routing of shards.

        Arguments:
            cluster_routing (curator.ClusterRouting): Curator's cluster routing object.

        """
        if self._dry_run:
            cluster_routing.do_dry_run()
        else:
            cluster_routing.do_action()

    def check_green(self) -> None:
        """Cluster health status.

        Raises:
            spicerack.elasticsearch_cluster.ElasticsearchClusterCheckError:
                This is raised when request times and cluster is not green.

        """
        try:
            self._elasticsearch.cluster.health(wait_for_status="green", timeout="1s")
        except (TransportError, HTTPError) as e:
            raise ElasticsearchClusterCheckError("Error while waiting for green") from e

    def check_yellow_w_no_moving_shards(self) -> None:
        """Cluster health status.

        Raises:
            spicerack.elasticsearch_cluster.ElasticsearchClusterCheckError:
                This is raised when request times and cluster is not yellow with no initializing or relocating shards.

        """
        try:
            self._elasticsearch.cluster.health(
                wait_for_status="yellow",
                wait_for_no_initializing_shards=True,
                wait_for_no_relocating_shards=True,
                timeout="1s",
            )
        except (TransportError, HTTPError) as e:
            raise ElasticsearchClusterCheckError(
                "Error while waiting for yellow with no initializing or relocating shards"
            ) from e

    @contextmanager
    def frozen_writes(self, reason: Reason) -> Iterator[None]:
        """Stop writes to all elasticsearch indices and enable them on exit.

        Arguments:
            reason (spicerack.administrative.Reason): Reason for freezing writes.

        """
        self._freeze_writes(reason)
        try:
            yield
        finally:
            try:
                self._unfreeze_writes()
            except ElasticsearchClusterError as e:
                # Unfreeze failed, we can try to freeze and unfreeze again,
                # which might work. If it throws an exception again, we won't
                # try a third time and let that new exception bubble up.
                logger.warning(
                    "Could not unfreeze writes, trying to freeze and unfreeze again: %s",
                    e,
                )
                self._freeze_writes(reason)
                self._unfreeze_writes()

    def _freeze_writes(self, reason: Reason) -> None:
        """Stop writes to all elasticsearch indices.

        Arguments:
            reason (spicerack.administrative.Reason): Reason for freezing writes.

        """
        doc = {
            "host": reason.hostname,
            "timestamp": datetime.utcnow().timestamp(),
            "reason": str(reason),
        }
        logger.info("Freezing all indices in %s", self)
        if self._dry_run:
            return
        try:
            self._elasticsearch.index(
                index=self._freeze_writes_index,
                doc_type=self._freeze_writes_doc_type,
                id="freeze-everything",
                body=doc,
            )
        except TransportError as e:
            raise ElasticsearchClusterError("Encountered error while creating document to freeze cluster writes") from e

    def _unfreeze_writes(self) -> None:
        """Enable writes on all elasticsearch indices."""
        logger.info("Unfreezing all indices in %s", self)
        if self._dry_run:
            return
        try:
            self._elasticsearch.delete(
                index=self._freeze_writes_index,
                doc_type=self._freeze_writes_doc_type,
                id="freeze-everything",
            )
        except TransportError as e:
            raise ElasticsearchClusterError(
                "Encountered error while deleting document to unfreeze cluster writes"
            ) from e

    def flush_markers(self, timeout: timedelta = timedelta(seconds=60)) -> None:
        """Flush markers unsynced.

        Note:
            ``flush`` and ``flush_synced`` are called here because from experience, it results in fewer shards not
            syncing. This also makes the recovery faster.

        Arguments:
            timeout (datetime.timedelta): timedelta object for elasticsearch request timeout.

        """
        logger.info("flush markers on %s", self)
        try:
            self._elasticsearch.indices.flush(force=True, request_timeout=timeout.seconds)
        except ConflictError:
            logger.warning("Not all shards were flushed on %s.", self)

        try:
            self._elasticsearch.indices.flush_synced(request_timeout=timeout.seconds)
        except ConflictError:
            logger.warning("Not all shards were synced flushed on %s.", self)

    def force_allocation_of_all_unassigned_shards(self) -> None:
        """Manual allocation of unassigned shards."""
        cluster_nodes_names = [node["name"] for node in self.get_nodes().values()]
        unassigned_shards = self._get_unassigned_shards()
        for unassigned_shard in unassigned_shards:
            self._force_allocation_of_shard(unassigned_shard, cluster_nodes_names)

    def _get_unassigned_shards(self) -> List[Dict]:
        """Fetch unassigned shards.

        Returns:
            list: list of unassigned shards from the cluster.

        """
        shards = self._elasticsearch.cat.shards(format="json", h="index,shard,state")
        return [s for s in shards if s["state"] == "UNASSIGNED"]

    def _force_allocation_of_shard(self, shard: Dict, nodes: List[str]) -> None:
        """Force allocation of shard.

        Arguments:
            shard (dict): shard of an index to be relocated.
            nodes (list): list of nodes to allocate shards to.

        Todo:
            It was found that forcing allocation of shards may perform better in terms of speed than
            letting elasticsearch do its recovery on its own.
            We should verify from time to time that elastic recovery performance has not gotten better
            and remove this step if proven unnecessary.

        """
        # shuffle nodes so that we don't allocate all shards on the same node
        shuffle(nodes)
        for node in nodes:
            try:
                logger.debug(
                    "Trying to allocate [%s:%s] on [%s]",
                    shard["index"],
                    shard["shard"],
                    node,
                )
                self._elasticsearch.cluster.reroute(
                    retry_failed=True,
                    body={
                        "commands": [
                            {
                                "allocate_replica": {
                                    "index": shard["index"],
                                    "shard": shard["shard"],
                                    "node": node,
                                }
                            }
                        ]
                    },
                )
                # successful allocation, we can exit
                logger.info(
                    "Successfully allocated shard [%s:%s] on [%s]",
                    shard["index"],
                    shard["shard"],
                    node,
                )
                break
            except RequestError:
                # error allocating shard, let's try the next node
                logger.debug(
                    "Could not reallocate shard [%s:%s] on [%s]",
                    shard["index"],
                    shard["shard"],
                    node,
                )
        else:
            logger.warning(
                "Could not reallocate shard [%s:%s] on any node",
                shard["index"],
                shard["shard"],
            )

    def reset_indices_to_read_write(self) -> None:
        """Reset all readonly indices to read/write.

        In some cases (running low on disk space), indices are switched to
        readonly. This method will update all readonly indices to read/write.
        """
        try:
            self._elasticsearch.indices.put_settings(body={"index.blocks.read_only_allow_delete": None}, index="_all")
        except (RequestError, TransportError, HTTPError) as e:
            raise ElasticsearchClusterError("Could not reset read only status") from e


class NodesGroup:
    """Internal class, used for parsing responses from the elasticsearch node API.

    Since the same server can host multiple elasticsearch instances, this class can consolidate those multiple
    instances in a single object.
    """

    def __init__(self, json_node: Dict, cluster: ElasticsearchCluster) -> None:
        """Instantiate a new node.

        Arguments:
            json_node (dict): a single node, as returned from the elasticsearch API.
            cluster (spicerack.elasticsearch_cluster.ElasticsearchCluster): an elasticsearch instance

        """
        self._hostname: str = json_node["attributes"]["hostname"]
        self._fqdn: str = json_node["attributes"]["fqdn"]
        self._clusters_names: List[str] = [json_node["settings"]["cluster"]["name"]]
        self._clusters_instances: List[ElasticsearchCluster] = [cluster]
        self._row: str = json_node["attributes"]["row"]
        self._oldest_start_time = datetime.utcfromtimestamp(json_node["jvm"]["start_time_in_millis"] / 1000)

    def accumulate(self, json_node: Dict, cluster: ElasticsearchCluster) -> None:
        """Accumulate information from other elasticsearch instances running on the same server.

        Arguments:
            json_node (dict): a single node, as returned from the elasticsearch API.
            cluster (elasticsearch.Elasticsearch): an elasticsearch instance

        """
        if self._fqdn != json_node["attributes"]["fqdn"]:
            # should never happen
            fqdn1 = self._fqdn
            fqdn2 = json_node["attributes"]["fqdn"]
            raise AssertionError(f"Invalid data, two instances on the same node with different fqdns [{fqdn1}/{fqdn2}]")
        cluster_name = json_node["settings"]["cluster"]["name"]
        if cluster_name not in self._clusters_names:
            self._clusters_names.append(cluster_name)
        if cluster not in self._clusters_instances:
            self._clusters_instances.append(cluster)
        if self._row != json_node["attributes"]["row"]:
            # should never happen
            row1 = self._row
            row2 = json_node["attributes"]["row"]
            raise AssertionError(
                f"Invalid data, two instances on the same node with different rows {self._hostname}:[{row1}/{row2}]"
            )
        start_time = datetime.utcfromtimestamp(json_node["jvm"]["start_time_in_millis"] / 1000)
        self._oldest_start_time = min(self._oldest_start_time, start_time)

    @property
    def row(self) -> str:
        """Datacenter row."""
        return self._row

    @property
    def fqdn(self) -> str:
        """Fully Qualified Domain Name."""
        return self._fqdn

    @property
    def clusters_instances(self) -> Sequence[ElasticsearchCluster]:
        """Cluster instances running on this node group."""
        return self._clusters_instances

    def restarted_since(self, since: datetime) -> bool:
        """Check if node has been restarted.

        Arguments:
            since (datetime.datetime): the time against after which we check if the node has been restarted.

        Returns:
            bool: True if the node has been restarted after since, false otherwise.

        """
        return self._oldest_start_time > since

    def check_all_nodes_up(self) -> None:
        """Check that all the nodes on this hosts are up and have joined their respective clusters.

        Raises:
            spicerack.elasticsearch_cluster.ElasticsearchClusterCheckError: if not all nodes have joined.

        """
        for cluster_instance in self._clusters_instances:
            if not cluster_instance.is_node_in_cluster_nodes(self._hostname):
                raise ElasticsearchClusterCheckError("Elasticsearch is not up yet")
