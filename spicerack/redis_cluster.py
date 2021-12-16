"""Redis cluster module."""
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any, DefaultDict, Dict, Tuple, Union

from redis import StrictRedis
from wmflib.config import load_yaml_config

from spicerack.exceptions import SpicerackError

logger = logging.getLogger(__name__)


class RedisClusterError(SpicerackError):
    """Custom exception class for errors in the RedisCluster class."""


class RedisCluster:
    """Class to manage a Redis Cluster."""

    def __init__(self, cluster: str, config_dir: Path, *, dry_run: bool = True) -> None:
        """Initialize the instance.

        Arguments:
            cluster (str): the name of the cluster to connect to.
            config_dir (str): path to the directory containing the configuration files for the Redis clusters.
            dry_run (bool, optional): whether this is a DRY-RUN.

        """
        self._dry_run = dry_run
        self._shards: DefaultDict[str, Dict] = defaultdict(dict)
        config = load_yaml_config(config_dir / f"{cluster}.yaml")

        for datacenter, shards in config["shards"].items():
            for shard, data in shards.items():
                self._shards[datacenter][shard] = RedisInstance(
                    host=data["host"],
                    port=data["port"],
                    password=config["password"],
                    decode_responses=True,
                )

    def start_replica(self, datacenter: str, master_datacenter: str) -> None:
        """Start the cluster replica in a datacenter from a master datacenter.

        Arguments:
            datacenter (str): the datacenter on which to start the replica.
            master_datacenter (str): the datacenter from which to replicate.

        Raises:
            RedisClusterError: on error and invalid parameters.

        """
        if master_datacenter == datacenter:
            raise RedisClusterError(
                f"Master datacenter must be different from the current datacenter, got {datacenter}"
            )

        for shard, instance in sorted(self._shards[datacenter].items()):
            self._start_instance_replica(instance, self._shards[master_datacenter][shard])

    def stop_replica(self, datacenter: str) -> None:
        """Stop the cluster replica in a datacenter.

        Arguments:
            datacenter (str): the datacenter on which to stop the replica.

        Raises:
            RedisClusterError: on error.

        """
        for instance in self._shards[datacenter].values():
            self._stop_instance_replica(instance)

    def _start_instance_replica(self, instance: "RedisInstance", master: "RedisInstance") -> None:
        """Start the replica in a specific instance from a master instance.

        Arguments:
            instance (spicerack.redis_cluster.RedisInstance): the instance where to start the replica.
            master (spicerack.redis_cluster.RedisInstance): the master instance to replicate from.

        Raises:
            RedisClusterError: if unable to verify the replica has started.

        """
        if instance.master_info == master.info:
            logger.debug("Replica already configured on %s", instance)
            return

        if self._dry_run:
            logger.debug("Skip starting replica on %s in dry-run mode", instance)
        else:
            logger.debug("Starting replica %s => %s", master, instance)
            instance.start_replica(master)

        if not self._dry_run and instance.master_info != master.info:
            raise RedisClusterError(f"Replica on {instance} is not correctly configured: {instance.master_info}")

    def _stop_instance_replica(self, instance: "RedisInstance") -> None:
        """Stop the replica in a specific instance.

        Arguments:
            instance (spicerack.redis_cluster.RedisInstance): the instance where to stop the replica.

        Raises:
            RedisClusterError: on error.

        """
        if instance.is_master:
            logger.debug("Instance %s is already master, doing nothing", instance)
            return

        if self._dry_run:
            logger.debug("Skip stopping replica on %s in dry-run mode", instance)
        else:
            logger.debug("Stopping replica on %s", instance)
            instance.stop_replica()

        if not self._dry_run and not instance.is_master:
            raise RedisClusterError(f"Instance {instance} is still a slave of {instance.master_info}, aborting")


class RedisInstance:
    """Class to manage a Redis instance, a simple wrapper around `redis.StrictRedis`."""

    def __init__(self, **kwargs: Any) -> None:
        """Initialize the instance.

        Arguments:
            **kwargs (mixed): arbitrary keyword arguments, to be passed to the `redis.StrictRedis` constructor.

        """
        self.host: str = kwargs.get("host", "")
        self.port: int = kwargs.get("port", 0)
        self._client = StrictRedis(**kwargs)

    @property
    def is_master(self) -> bool:
        """Getter to check if the current instance is a master.

        Returns:
            bool: :py:data:`True` if the instance is a master, :py:data:`False` otherwise.

        """
        return self._client.info("replication")["role"] == "master"

    @property
    def master_info(self) -> Union[Tuple[None, None], Tuple[str, int]]:
        """Getter to know the master of this instance.

        Returns:
            tuple: a 2-element tuple with (host/IP, port) of the master instance. If there is no master configured
            (None, None) is returned.

        """
        data = self._client.info("replication")
        try:
            return data["master_host"], data["master_port"]
        except (KeyError, TypeError):
            return (None, None)

    @property
    def info(self) -> Tuple[str, int]:
        """Getter to know the detail of this instance.

        Returns:
            tuple: a 2-element tuple with (host/IP, port) of the instance.

        """
        return self.host, self.port

    def stop_replica(self) -> None:
        """Stop the replica on the instance."""
        self._client.slaveof()

    def start_replica(self, master: "RedisInstance") -> None:
        """Start the replica from the given master instance.

        Arguments:
            master (spicerack.redis_cluster.RedisInstance): the master instance.

        """
        self._client.slaveof(master.host, master.port)

    def __str__(self) -> str:
        """String representation of the instance.

        Returns:
            str: the host or IP and port of the instance.

        """
        return f"{self.host}:{self.port}"
