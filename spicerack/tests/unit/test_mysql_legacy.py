"""MysqlLegacy module tests."""
import logging
from datetime import datetime
from unittest import mock

import pytest
from cumin import Config, NodeSet

from spicerack import mysql_legacy
from spicerack.remote import Remote, RemoteHosts
from spicerack.tests import get_fixture_path
from spicerack.tests.unit.test_remote import mock_cumin

EQIAD_CORE_MASTERS_QUERY = "db10[01-12]"
CODFW_CORE_MASTERS_QUERY = "db20[01-12]"


class TestMysqlLegacyRemoteHosts:
    """Test class for the MysqlLegacyRemoteHosts class."""

    @mock.patch("spicerack.remote.transports", autospec=True)
    def setup_method(self, _, mocked_transports):
        """Setup the test environment."""
        # pylint: disable=attribute-defined-outside-init
        self.config = Config(get_fixture_path("remote", "config.yaml"))
        self.mocked_transports = mocked_transports
        self.mysql_remote_hosts = mysql_legacy.MysqlLegacyRemoteHosts(
            RemoteHosts(self.config, NodeSet("host[1-9]"), dry_run=False)
        )
        self.expected = [(NodeSet("host1"), "output1")]

    def test_execute(self):
        """Calling run_query() should run the given query in the target hosts."""
        mock_cumin(self.mocked_transports, 0)
        results = self.mysql_remote_hosts.run_query("query1")
        assert [(host, msg.message().decode()) for host, msg in results] == self.expected


class TestMysqlLegacy:
    """MysqlLegacy class tests."""

    @mock.patch("spicerack.remote.transports", autospec=True)
    def setup_method(self, _, mocked_transports):
        """Initialize the test environment for MysqlLegacy."""
        # pylint: disable=attribute-defined-outside-init
        self.config = Config(get_fixture_path("remote", "config.yaml"))
        self.mocked_transports = mocked_transports
        self.mocked_remote = mock.MagicMock(spec_set=Remote)
        self.mysql = mysql_legacy.MysqlLegacy(self.mocked_remote, dry_run=False)

    def test_get_dbs(self):
        """It should return and instance of MysqlLegacyRemoteHosts for the matching hosts."""
        self.mysql.get_dbs("query")
        self.mocked_remote.query.assert_called_once_with("query")

    @pytest.mark.parametrize(
        "kwargs, query, match",
        (
            ({}, "A:db-core", "db10[01-99],db20[01-99]"),
            ({"datacenter": "eqiad"}, "A:db-core and A:eqiad", "db10[01-99]"),
            (
                {"section": "s1"},
                "A:db-core and A:db-section-s1",
                "db10[01-10],db20[01-10]",
            ),
            (
                {"replication_role": "master"},
                "A:db-core and A:db-role-master",
                ",".join([EQIAD_CORE_MASTERS_QUERY, CODFW_CORE_MASTERS_QUERY]),
            ),
            (
                {"datacenter": "eqiad", "section": "s1"},
                "A:db-core and A:eqiad and A:db-section-s1",
                "db10[01-10]",
            ),
            (
                {"datacenter": "eqiad", "replication_role": "master"},
                "A:db-core and A:eqiad and A:db-role-master",
                EQIAD_CORE_MASTERS_QUERY,
            ),
            (
                {"datacenter": "eqiad", "replication_role": "master", "excludes": ("x2",)},
                "A:db-core and A:eqiad and not A:db-section-x2 and A:db-role-master",
                "db10[01-11]",
            ),
            (
                {"section": "s1", "replication_role": "master"},
                "A:db-core and A:db-section-s1 and A:db-role-master",
                "db1001,db2001",
            ),
            (
                {"datacenter": "eqiad", "section": "s1", "replication_role": "master"},
                "A:db-core and A:eqiad and A:db-section-s1 and A:db-role-master",
                "db1001",
            ),
        ),
    )
    def test_get_core_dbs_ok(self, kwargs, query, match):
        """It should return the right DBs based on the parameters."""
        self.mocked_remote.query.return_value = RemoteHosts(self.config, NodeSet(match))
        self.mysql.get_core_dbs(**kwargs)
        self.mocked_remote.query.assert_called_once_with(query)

    @pytest.mark.parametrize(
        "kwargs",
        (
            {"datacenter": "invalid"},
            {"section": "invalid"},
            {"replication_role": "invalid"},
            {"excludes": ("invalid",)},
        ),
    )
    def test_get_core_dbs_fail(self, kwargs):
        """It should raise MysqlLegacyError if called with invalid parameters."""
        key = list(kwargs.keys())[0]
        message = f"Got invalid {key}"
        with pytest.raises(mysql_legacy.MysqlLegacyError, match=message):
            self.mysql.get_core_dbs(**kwargs)

        assert not self.mocked_remote.query.called

    def test_get_core_dbs_fail_sanity_check(self):
        """It should raise MysqlLegacyError if matching an invalid number of hosts when looking for masters."""
        self.mocked_remote.query.return_value = RemoteHosts(self.config, NodeSet("db1001"))
        with pytest.raises(mysql_legacy.MysqlLegacyError, match="Matched 1 masters, expected 12"):
            self.mysql.get_core_dbs(datacenter="eqiad", replication_role="master")

        assert self.mocked_remote.query.called

    @pytest.mark.parametrize("mode, value", (("readonly", b"1"), ("readwrite", b"0")))
    def test_set_core_masters_readonly(self, mode, value, caplog):
        """It should set the masters as read-only/read-write."""
        self.mocked_remote.query.return_value = RemoteHosts(self.config, NodeSet("db10[01-11]"))
        mock_cumin(self.mocked_transports, 0, retvals=[[("db10[01-11]", value)]])
        with caplog.at_level(logging.DEBUG):
            getattr(self.mysql, "set_core_masters_" + mode)("eqiad")
        assert "SET GLOBAL read_only=" + value.decode() in caplog.text

    @pytest.mark.parametrize("readonly, reply", ((True, b"1"), (False, b"0")))
    def test_verify_core_masters_readonly_ok(self, readonly, reply, caplog):
        """Should verify that the masters have the intended read-only value."""
        self.mocked_remote.query.return_value = RemoteHosts(self.config, NodeSet("db10[01-11]"))
        mock_cumin(self.mocked_transports, 0, retvals=[[("db10[01-11]", reply)]])
        with caplog.at_level(logging.DEBUG):
            self.mysql.verify_core_masters_readonly("eqiad", readonly)
        assert "SELECT @@global.read_only" in caplog.text

    def test_verify_core_masters_readonly_fail(self):
        """Should raise MysqlLegacyError if some masters do not have the intended read-only value."""
        self.mocked_remote.query.return_value = RemoteHosts(self.config, NodeSet("db10[01-11]"))
        mock_cumin(
            self.mocked_transports,
            0,
            retvals=[[("db1001", b"0"), ("db10[02-11]", b"1")]],
        )
        with pytest.raises(
            mysql_legacy.MysqlLegacyError,
            match="Verification failed that core DB masters",
        ):
            self.mysql.verify_core_masters_readonly("eqiad", True)

    @mock.patch("wmflib.decorators.time.sleep", return_value=None)
    def test_check_core_masters_in_sync_ok(self, mocked_sleep):
        """Should check that all core masters are in sync with the master in the other DC."""
        hosts = NodeSet(EQIAD_CORE_MASTERS_QUERY)
        self.mocked_remote.query.side_effect = [RemoteHosts(self.config, NodeSet(host)) for host in hosts] * 2
        retvals = [[(host, b"2018-09-06T10:00:00.000000")] for host in hosts]  # first heartbeat
        retvals += [[(host, b"2018-09-06T10:00:01.000000")] for host in hosts]  # second heartbeat
        mock_cumin(self.mocked_transports, 0, retvals=retvals)
        self.mysql.check_core_masters_in_sync("eqiad", "codfw")
        assert not mocked_sleep.called

    @mock.patch("wmflib.decorators.time.sleep", return_value=None)
    def test_check_core_masters_in_sync_fail_heartbeat(self, mocked_sleep):
        """Should raise MysqlLegacyError if unable to get the heartbeat from the current master."""
        self.mocked_remote.query.return_value = RemoteHosts(self.config, NodeSet("db1001"))
        mock_cumin(self.mocked_transports, 0, retvals=[])
        with pytest.raises(mysql_legacy.MysqlLegacyError, match="Unable to get heartbeat from master"):
            self.mysql.check_core_masters_in_sync("eqiad", "codfw")
        assert not mocked_sleep.called

    @mock.patch("wmflib.decorators.time.sleep", return_value=None)
    def test_check_core_masters_in_sync_not_in_sync(self, mocked_sleep):
        """Should raise MysqlLegacyError if a master is not in sync with the one in the other DC."""
        hosts = NodeSet(EQIAD_CORE_MASTERS_QUERY)
        self.mocked_remote.query.side_effect = [RemoteHosts(self.config, NodeSet(host)) for host in hosts] + [
            RemoteHosts(self.config, NodeSet("db1001"))
        ] * 3
        retvals = [[(host, b"2018-09-06T10:00:00.000000")] for host in hosts]  # first heartbeat
        retvals += [[("db1001", b"2018-09-06T10:00:00.000000")]] * 3  # 3 failed retries of second heartbeat
        mock_cumin(self.mocked_transports, 0, retvals=retvals)
        with pytest.raises(
            mysql_legacy.MysqlLegacyError,
            match=r"Heartbeat from master db1001 for section .* not yet in sync",
        ):
            self.mysql.check_core_masters_in_sync("eqiad", "codfw")

        assert mocked_sleep.called

    def test_get_core_masters_heartbeats_wrong_data(self):
        """Should raise MysqlLegacyError if unable to convert the heartbeat into a datetime."""
        self.mocked_remote.query.return_value = RemoteHosts(self.config, NodeSet("db1001"))
        mock_cumin(
            self.mocked_transports,
            0,
            retvals=[[("db1001", b"2018-09-06-10:00:00.000000")]],
        )
        with pytest.raises(mysql_legacy.MysqlLegacyError, match="Unable to convert heartbeat"):
            self.mysql.get_core_masters_heartbeats("eqiad", "codfw")

    @mock.patch("wmflib.decorators.time.sleep", return_value=None)
    def test_check_core_masters_heartbeats_fail(self, mocked_sleep):
        """Should raise MysqlLegacyError if unable to get the heartbeat from the master."""
        self.mocked_remote.query.return_value = RemoteHosts(self.config, NodeSet("db1001"))
        mock_cumin(self.mocked_transports, 0, retvals=[])
        with pytest.raises(mysql_legacy.MysqlLegacyError, match="Unable to get heartbeat from master"):
            self.mysql.check_core_masters_heartbeats("eqiad", "codfw", {"s1": datetime.utcnow()})

        assert mocked_sleep.called
