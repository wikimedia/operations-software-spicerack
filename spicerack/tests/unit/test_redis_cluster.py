"""RedisCluster module tests."""
from unittest import mock

import pytest

from spicerack.redis_cluster import RedisCluster, RedisClusterError
from spicerack.tests import get_fixture_path


class TestRedisCluster:
    """RedisCluster class tests."""

    @mock.patch("spicerack.redis_cluster.StrictRedis")
    def setup_method(self, _, mocked_redis):
        """Initialize the test environment for RedisCluster."""
        config_dir = get_fixture_path("redis_cluster")
        # pylint: disable=attribute-defined-outside-init
        self.mocked_redis = mocked_redis
        self.redis_cluster = RedisCluster("cluster", config_dir, dry_run=False)
        self.redis_cluster_dry_run = RedisCluster("cluster", config_dir)

    def test_start_replica(self):
        """Should start the replica and verify it."""
        self.mocked_redis.return_value.info.side_effect = [
            {"role": "master"},
            {"role": "slave", "master_host": "host1", "master_port": 123},
            {"role": "master"},
            {"role": "slave", "master_host": "host2", "master_port": 123},
        ]
        self.redis_cluster.start_replica("dc2", "dc1")
        assert self.mocked_redis.return_value.slaveof.called

    def test_start_replica_dry_run(self):
        """Should skip starting the replica in dry-run mode and not raise exception."""
        self.mocked_redis.return_value.info.side_effect = [{"role": "master"}] * 2
        self.redis_cluster_dry_run.start_replica("dc2", "dc1")
        assert not self.mocked_redis.return_value.slaveof.called

    def test_start_replica_noop(self):
        """Should be a noop if the replica is already correctly configured."""
        self.mocked_redis.return_value.info.side_effect = [
            {"role": "slave", "master_host": "host1", "master_port": 123},
            {"role": "slave", "master_host": "host2", "master_port": 123},
        ]
        self.redis_cluster.start_replica("dc2", "dc1")
        assert not self.mocked_redis.return_value.slaveof.called

    def test_start_replica_fail(self):
        """Should raise RedisClusterError if not able to verify that is started."""
        self.mocked_redis.return_value.info.side_effect = [{"role": "master"}] * 3
        with pytest.raises(RedisClusterError, match="is not correctly configured"):
            self.redis_cluster.start_replica("dc2", "dc1")

    def test_start_replica_same_dc(self):
        """Should raise RedisClusterError when trying to set the replica with it's own datacenter."""
        with pytest.raises(
            RedisClusterError,
            match="Master datacenter must be different from the current datacenter",
        ):
            self.redis_cluster.start_replica("dc1", "dc1")

        assert not self.mocked_redis.return_value.info.called

    def test_stop_replica(self):
        """Should stop the replica and verify it."""
        self.mocked_redis.return_value.info.side_effect = [
            {"role": "slave", "master_host": "host1", "master_port": 123},
            {"role": "master"},
        ] * 2
        self.redis_cluster.stop_replica("dc2")
        assert self.mocked_redis.return_value.slaveof.called

    def test_stop_replica_dry_run(self):
        """Should stop the replica and verify it."""
        self.mocked_redis.return_value.info.side_effect = [
            {"role": "slave", "master_host": "host1", "master_port": 123},
            {"role": "master"},
        ] * 2
        self.redis_cluster_dry_run.stop_replica("dc2")
        assert not self.mocked_redis.return_value.slaveof.called

    def test_stop_replica_noop(self):
        """Should skip stopping the replica in dry-run mode and not raise exception."""
        self.mocked_redis.return_value.info.side_effect = [{"role": "master"}] * 2
        self.redis_cluster.stop_replica("dc2")
        assert not self.mocked_redis.return_value.slaveof.called

    def test_stop_replica_fail(self):
        """Should raise RedisClusterError if not able to verify that is stopped."""
        self.mocked_redis.return_value.info.side_effect = [
            {"role": "slave", "master_host": "host1", "master_port": 123}
        ] * 3
        with pytest.raises(RedisClusterError, match="is still a slave of"):
            self.redis_cluster.stop_replica("dc2")
