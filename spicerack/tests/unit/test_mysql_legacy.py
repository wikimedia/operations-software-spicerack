"""MysqlLegacy module tests."""

import logging
import re
from datetime import datetime
from unittest import mock

import pytest
from ClusterShell.MsgTree import MsgTreeElem
from cumin import Config, nodeset

from spicerack import mysql_legacy
from spicerack.remote import Remote, RemoteExecutionError, RemoteHosts
from spicerack.tests import get_fixture_path
from spicerack.tests.unit.test_remote import mock_cumin

EQIAD_CORE_MASTERS_QUERY = "db10[01-11]"
CODFW_CORE_MASTERS_QUERY = "db20[01-11]"
VERTICAL_QUERY_NEWLINE = """*************************** 1. row ***************************
test: line with
a newline
"""


class TestInstance:
    """Test class for the Instance class."""

    def setup_method(self):
        """Setup the test environment."""
        # pylint: disable=attribute-defined-outside-init
        self.mocked_run_sync = mock.Mock()
        self.config = Config(get_fixture_path("remote", "config.yaml"))
        single = RemoteHosts(self.config, nodeset("single1"), dry_run=False)
        single.run_sync = self.mocked_run_sync
        multi = RemoteHosts(self.config, nodeset("multi1"), dry_run=False)
        multi.run_sync = self.mocked_run_sync
        self.single_instance = mysql_legacy.Instance(single)
        self.multi_instance = mysql_legacy.Instance(multi, name="instance1")

    def test_init_raise(self):
        """It should raise a NotImplementedError exception if more than one host is passed to the constructor."""
        with pytest.raises(NotImplementedError, match="Only single hosts are currently supported"):
            mysql_legacy.Instance(RemoteHosts(self.config, nodeset("host[1-2]")))

    @pytest.mark.parametrize(
        "query, database, kwargs",
        (
            ("SELECT 1 AS test", "", {}),
            ("SELECT 1 AS test FROM dbname", "dbname", {}),
            ("SELECT 1 AS test", "", {"is_safe": True}),
            ("SELECT 1 AS test", "", {"print_progress_bars": True, "print_output": True}),
        ),
    )
    def test_single_run_query_ok(self, query, database, kwargs):
        """It should run the query and return the results."""
        self.mocked_run_sync.return_value = [(nodeset("single1"), MsgTreeElem(b"test\n1", parent=MsgTreeElem()))]
        results = self.single_instance.run_query(query, database=database, **kwargs)
        assert [(str(host), msg.message().decode()) for host, msg in results] == [("single1", "test\n1")]
        expected_kwargs = {"print_progress_bars": False, "print_output": False, **kwargs}
        self.mocked_run_sync.assert_called_once_with(
            f'/usr/local/bin/mysql --socket /run/mysqld/mysqld.sock --batch --execute "{query}" {database}'.strip(),
            **expected_kwargs,
        )

    def test_multi_query_raise(self):
        """It should raise a MysqlLegacyError exception if the query execution fails."""
        self.mocked_run_sync.side_effect = RemoteExecutionError(retcode=1, message="error", results=iter(()))
        with pytest.raises(mysql_legacy.MysqlLegacyError, match="Failed to run 'invalid' on multi1"):
            self.multi_instance.run_query("invalid")

        self.mocked_run_sync.assert_called_once_with(
            '/usr/local/bin/mysql --socket /run/mysqld/mysqld.instance1.sock --batch --execute "invalid"',
            print_progress_bars=False,
            print_output=False,
        )

    def test_run_vertical_query_ok(self):
        """It should return the current slave status of the database."""
        status = get_fixture_path("mysql_legacy", "single_show_slave_status.out").read_text()
        self.mocked_run_sync.return_value = [
            (nodeset("single1"), MsgTreeElem("".join((status, status)).encode(), parent=MsgTreeElem()))
        ]
        rows = self.single_instance.run_vertical_query("SELECT")  # dummy query
        self.mocked_run_sync.assert_called_once_with(
            r'/usr/local/bin/mysql --socket /run/mysqld/mysqld.sock --batch --execute "SELECT\G"',
            print_progress_bars=False,
            print_output=False,
        )
        assert len(rows) == 2
        assert rows[0]["Seconds_Behind_Master"] == rows[1]["Seconds_Behind_Master"] == "0"

    def test_run_vertical_query_empty(self):
        """It should return an empty list. This should not happen in real life."""
        response = "*************************** 1. row ***************************\n".encode()
        self.mocked_run_sync.return_value = [(nodeset("single1"), MsgTreeElem(response, parent=MsgTreeElem()))]
        rows = self.single_instance.run_vertical_query("SELECT")  # dummy query
        assert rows == []  # pylint: disable=use-implicit-booleaness-not-comparison

    def test_run_vertical_query_parse_error(self, caplog):
        """It should log the skipping of some lines that were not properly parser."""
        self.mocked_run_sync.return_value = [
            (nodeset("single1"), MsgTreeElem(VERTICAL_QUERY_NEWLINE.encode(), parent=MsgTreeElem()))
        ]
        with caplog.at_level(logging.ERROR):
            rows = self.single_instance.run_vertical_query("SELECT")  # dummy query

        assert rows == [{"test": "line with"}]
        assert "Failed to parse into key/value for query 'SELECT' this line: a newline" in caplog.text

    @pytest.mark.parametrize("instance", ("single_instance", "multi_instance"))
    @pytest.mark.parametrize(
        "method, expected",
        (
            ("stop_slave", "STOP SLAVE"),
            ("start_slave", "START SLAVE"),
        ),
    )
    @mock.patch("spicerack.mysql_legacy.sleep", return_value=None)
    def test_run_method_ok(self, mocked_sleep, method, expected, instance):
        """It should run the method called and execute the related query."""
        self.mocked_run_sync.return_value = iter(())

        getattr(getattr(self, instance), method)()
        suffix = ".instance1" if instance == "multi_instance" else ""
        self.mocked_run_sync.assert_called_once_with(
            f'/usr/local/bin/mysql --socket /run/mysqld/mysqld{suffix}.sock --batch --execute "{expected}"',
            print_progress_bars=False,
            print_output=False,
        )
        assert mocked_sleep.called == (method == "start_slave")

    def test_single_show_slave_status_ok(self):
        """It should return the current slave status of the database."""
        status = get_fixture_path("mysql_legacy", "single_show_slave_status.out").read_text().encode()
        self.mocked_run_sync.return_value = [(nodeset("single1"), MsgTreeElem(status, parent=MsgTreeElem()))]
        status = self.single_instance.show_slave_status()
        assert status["Master_Host"] == "host1.example.org"
        assert status["Seconds_Behind_Master"] == "0"
        self.mocked_run_sync.assert_called_once_with(
            r'/usr/local/bin/mysql --socket /run/mysqld/mysqld.sock --batch --execute "SHOW SLAVE STATUS\G"',
            is_safe=True,
            print_progress_bars=False,
            print_output=False,
        )

    def test_single_show_slave_status_on_master(self):
        """It should raise a MysqlLegacyError exception if show slave status is called on a master."""
        self.mocked_run_sync.return_value = iter(())
        with pytest.raises(
            mysql_legacy.MysqlLegacyError, match=re.escape("SHOW SLAVE STATUS seems to have been executed on a master")
        ):
            self.single_instance.show_slave_status()

    def test_single_show_slave_status_multisource(self):
        """It should raise a MysqlLegacyError exception if show slave status is called on a multisource instance."""
        status = get_fixture_path("mysql_legacy", "single_show_slave_status.out").read_text()
        self.mocked_run_sync.return_value = [
            (nodeset("single1"), MsgTreeElem("".join((status, status)).encode(), parent=MsgTreeElem()))
        ]
        with pytest.raises(NotImplementedError, match="Multisource setup are not implemented"):
            self.single_instance.show_slave_status()

    def test_single_show_master_status_ok(self):
        """It should return the current master status of the database."""
        status = get_fixture_path("mysql_legacy", "single_show_master_status.out").read_text().encode()
        self.mocked_run_sync.return_value = [(nodeset("single1"), MsgTreeElem(status, parent=MsgTreeElem()))]
        status = self.single_instance.show_master_status()
        assert status["File"] == "host2-bin.001234"
        assert status["Position"] == "123456789"

    def test_single_show_master_status_no_binlog(self):
        """It should raise a MysqlLegacyError if show master status is run on a host with binlog disabled."""
        self.mocked_run_sync.return_value = iter(())
        with pytest.raises(
            mysql_legacy.MysqlLegacyError,
            match=re.escape("SHOW MASTER STATUS seems to have been executed on a host with binlog disabled"),
        ):
            self.single_instance.show_master_status()

    @pytest.mark.parametrize(
        "setting, expected",
        (
            (mysql_legacy.MasterUseGTID.CURRENT_POS, "current_pos"),
            (mysql_legacy.MasterUseGTID.SLAVE_POS, "slave_pos"),
            (mysql_legacy.MasterUseGTID.NO, "no"),
        ),
    )
    def test_set_master_use_gtid_ok(self, setting, expected):
        """It should execute MASTER_USE_GTID with the given value."""
        self.mocked_run_sync.return_value = iter(())

        self.single_instance.set_master_use_gtid(setting)
        query = f"CHANGE MASTER TO MASTER_USE_GTID={expected}"
        self.mocked_run_sync.assert_called_once_with(
            f'/usr/local/bin/mysql --socket /run/mysqld/mysqld.sock --batch --execute "{query}"',
            print_progress_bars=False,
            print_output=False,
        )

    def test_set_master_use_gtid_invalid(self):
        """It should raise MysqlLegacyError if called with an invalid setting."""
        with pytest.raises(
            mysql_legacy.MysqlLegacyError,
            match=re.escape("Only instances of MasterUseGTID are accepted, got: <class 'str'>"),
        ):
            self.single_instance.set_master_use_gtid("invalid")

    @pytest.mark.parametrize("instance", ("single_instance", "multi_instance"))
    @pytest.mark.parametrize("method", ("stop", "start", "status", "restart"))
    def test_single_systemctl_action_ok(self, method, instance):
        """It should perform the systemctl action on the mysql process."""
        self.mocked_run_sync.return_value = iter(())
        getattr(getattr(self, instance), f"{method}_mysql")()
        suffix = "@instance1" if instance == "multi_instance" else ""
        kwargs = {}
        if method == "status":
            kwargs["is_safe"] = True
        if method == "start":
            kwargs["print_output"] = True

        self.mocked_run_sync.assert_called_once_with(f"/usr/bin/systemctl {method} mariadb{suffix}.service", **kwargs)

    @pytest.mark.parametrize(
        "instance, path",
        (
            ("single_instance", "/srv/sqldata"),
            ("multi_instance", "/srv/sqldata.instance1"),
        ),
    )
    @pytest.mark.parametrize("skip_confirmation", (False, True))
    @mock.patch("spicerack.mysql_legacy.ask_confirmation")
    def test_clean_data_dir(self, mocked_ask_confirmation, skip_confirmation, instance, path):
        """It should delete the data directory."""
        self.mocked_run_sync.return_value = iter(())
        obj = getattr(self, instance)
        obj.clean_data_dir(skip_confirmation=skip_confirmation)
        self.mocked_run_sync.assert_called_once_with(f"/usr/bin/rm -rf {path}")
        if skip_confirmation:
            mocked_ask_confirmation.assert_not_called()
        else:
            mocked_ask_confirmation.assert_called_once_with(
                f"ATTENTION: destructive action for {obj.host}: /usr/bin/rm -rf {path}. Are you sure to proceed?"
            )

    @pytest.mark.parametrize("instance", ("single_instance", "multi_instance"))
    def test_upgrade(self, instance):
        """It should run the mysql upgrade command."""
        self.mocked_run_sync.return_value = iter(())
        getattr(self, instance).upgrade()
        suffix = ".instance1" if instance == "multi_instance" else ""
        self.mocked_run_sync.assert_called_once_with(
            f"$(readlink -f /usr/local/bin/mysql_upgrade) --socket /run/mysqld/mysqld{suffix}.sock --force",
            print_output=True,
        )

    def test_get_replication_info_ok(self):
        """It should return a ReplicationInfo instance with the proper data."""
        status = get_fixture_path("mysql_legacy", "single_show_slave_status.out").read_text().encode()
        self.mocked_run_sync.return_value = [(nodeset("single1"), MsgTreeElem(status, parent=MsgTreeElem()))]
        info = self.single_instance.get_replication_info()
        self.mocked_run_sync.assert_called_once_with(
            r'/usr/local/bin/mysql --socket /run/mysqld/mysqld.sock --batch --execute "SHOW SLAVE STATUS\G"',
            is_safe=True,
            print_progress_bars=False,
            print_output=False,
        )
        assert info.primary == "host1.example.org"
        assert info.binlog == "host1-bin.001234"
        assert info.position == 123456782

    def test_get_replication_info_raise(self):
        """It should raise a MysqlLegacyError if unable to get the replication information."""
        status = (
            get_fixture_path("mysql_legacy", "single_show_slave_status.out")
            .read_text()
            .replace("Master_Host", "Master_Host_Invalid")
        )
        self.mocked_run_sync.return_value = [(nodeset("single1"), MsgTreeElem(status.encode(), parent=MsgTreeElem()))]
        with pytest.raises(mysql_legacy.MysqlLegacyError, match="Could not find the replication position"):
            self.single_instance.get_replication_info()

    def test_primary_ok(self):
        """It should return the hostname of the primary host for this host."""
        status = get_fixture_path("mysql_legacy", "single_show_slave_status.out").read_text().encode()
        self.mocked_run_sync.return_value = [(nodeset("single1"), MsgTreeElem(status, parent=MsgTreeElem()))]
        assert self.single_instance.primary == "host1.example.org"
        self.mocked_run_sync.assert_called_once()
        # Ensure the caching of the result works
        self.single_instance.primary  # pylint: disable=pointless-statement
        self.mocked_run_sync.assert_called_once()

    @pytest.mark.parametrize("no_content", (False, True))
    def test_primary_raise(self, no_content):
        """It should raise a MysqlLegacyError if there is no primary or is run on a master."""
        if no_content:
            self.mocked_run_sync.return_value = iter(())
        else:
            status = (
                get_fixture_path("mysql_legacy", "single_show_slave_status.out")
                .read_text()
                .replace("Master_Host", "Master_Host_Invalid")
            )
            self.mocked_run_sync.return_value = [
                (nodeset("single1"), MsgTreeElem(status.encode(), parent=MsgTreeElem()))
            ]

        with pytest.raises(mysql_legacy.MysqlLegacyError, match="Unable to retrieve master host"):
            self.single_instance.primary  # pylint: disable=pointless-statement

    def test_prep_src_for_cloning(self):
        """It should run the preparation commands before cloning."""
        status = get_fixture_path("mysql_legacy", "single_show_slave_status.out").read_text().encode()
        node = nodeset("single1")
        self.mocked_run_sync.side_effect = [
            [(node, iter(()))],
            [(node, MsgTreeElem(status, parent=MsgTreeElem()))],
            [(node, iter(()))],
        ]
        info = self.single_instance.prep_src_for_cloning()
        assert info.primary == "host1.example.org"
        calls = self.mocked_run_sync.call_args_list
        assert calls[0][0][0].endswith('STOP SLAVE"')
        assert calls[1][0][0].endswith(r'SHOW SLAVE STATUS\G"')
        assert calls[2][0][0] == "/usr/bin/systemctl stop mariadb.service"

    def test_set_replication_parameters(self):
        """It should set the replication to the given parameters."""
        status = get_fixture_path("mysql_legacy", "single_show_slave_status.out").read_text().encode()
        self.mocked_run_sync.return_value = [(nodeset("single1"), MsgTreeElem(status, parent=MsgTreeElem()))]
        info = self.single_instance.get_replication_info()
        self.mocked_run_sync.reset_mock()

        self.multi_instance.set_replication_parameters(replication_info=info, user="user", password="dummy")

        query = self.mocked_run_sync.call_args[0][0]
        for part in (
            "CHANGE MASTER TO",
            "master_host='host1.example.org'",
            "master_port=3306",
            "master_ssl=1",
            "master_log_file='host1-bin.001234'",
            "master_log_pos=123456782",
            "master_user='user'",
            "password='dummy'",
        ):
            assert part in query

    def test_post_clone_reset_with_slave_stopped(self):
        """It should start mysql with slave stopped and reset all slave information."""
        self.mocked_run_sync.side_effect = [[(nodeset("single1"), iter(()))]] * 5
        self.single_instance.post_clone_reset_with_slave_stopped()
        calls = self.mocked_run_sync.call_args_list
        assert calls[0][0][0].endswith("chown -R mysql:mysql /srv/sqldata")
        assert calls[0][0][1].endswith('set-environment MYSQLD_OPTS="--skip-slave-start"')
        assert calls[1][0][0].endswith("systemctl start mariadb.service")
        assert calls[2][0][0].endswith('STOP SLAVE"')
        assert calls[3][0][0].endswith('RESET SLAVE ALL"')

    def test_resume_replication(self):
        """It should start mysql, upgrade it, restart it and resume the replication."""
        self.mocked_run_sync.side_effect = [[(nodeset("single1"), iter(()))]] * 5
        self.single_instance.resume_replication()
        calls = self.mocked_run_sync.call_args_list
        assert calls[0][0][0].endswith('set-environment MYSQLD_OPTS="--skip-slave-start"')
        assert calls[1][0][0].endswith("systemctl start mariadb.service")
        assert calls[2][0][0].endswith(
            "$(readlink -f /usr/local/bin/mysql_upgrade) --socket /run/mysqld/mysqld.sock --force"
        )
        assert calls[3][0][0].endswith("systemctl restart mariadb.service")
        assert calls[4][0][0].endswith('START SLAVE"')

    @pytest.mark.parametrize("threshold", (0, 0.1234, 0.5))
    @mock.patch("wmflib.decorators.time.sleep", return_value=None)
    def test_wait_for_replication_already_ok(self, mocked_sleep, threshold):
        """If the replication is already in sync it should return immediately."""
        self.mocked_run_sync.return_value = [(nodeset("single1"), MsgTreeElem(b"lag\n0.1234", parent=MsgTreeElem()))]
        if threshold:
            self.single_instance.wait_for_replication(threshold)
        else:
            threshold = 1.0
            self.multi_instance.wait_for_replication()

        mocked_sleep.assert_not_called()

    @mock.patch("wmflib.decorators.time.sleep", return_value=None)
    def test_wait_for_replication_sleep_ok(self, mocked_sleep):
        """If the replication is not yet in sync it should wait until it gets in sync, within the timeout."""
        results = [[(nodeset("single1"), MsgTreeElem(b"lag\n1.1234", parent=MsgTreeElem()))]] * 5
        results.append([(nodeset("single1"), MsgTreeElem(b"lag\n0.1234", parent=MsgTreeElem()))])
        self.mocked_run_sync.side_effect = results
        self.single_instance.wait_for_replication()
        assert mocked_sleep.call_count == 5

    @mock.patch("wmflib.decorators.time.sleep", return_value=None)
    def test_wait_for_replication_fail(self, mocked_sleep):
        """If the replication is not in sync within the timeout it should raise a MysqlLegacyReplagError exception."""
        self.mocked_run_sync.side_effect = [
            [(nodeset("single1"), MsgTreeElem(b"lag\n1.1234", parent=MsgTreeElem()))]
        ] * 480
        with pytest.raises(
            mysql_legacy.MysqlLegacyReplagError,
            match=re.escape("Replication lag higher than the threshold (1.0s): 1.1234s"),
        ):
            self.single_instance.wait_for_replication()

        assert mocked_sleep.call_count == 479

    def test_replication_lag_ok(self):
        """It should return the current replication lag as float."""
        self.mocked_run_sync.return_value = [(nodeset("single1"), MsgTreeElem(b"lag\n0.1234", parent=MsgTreeElem()))]
        assert self.single_instance.replication_lag() == pytest.approx(0.1234)

    @pytest.mark.parametrize(
        "results, error_message",
        (
            (None, "Got no output from the replication lag query"),
            (MsgTreeElem(b"invalid", parent=MsgTreeElem()), "Unable to parse replication lag from: ['invalid']"),
            (
                MsgTreeElem(b"invalid\nnot-a-float", parent=MsgTreeElem()),
                "Unable to parse replication lag from: ['invalid', 'not-a-float']",
            ),
        ),
    )
    def test_replication_lag_fail(self, results, error_message):
        """It should raise a MysqlLegacyError if there is no output or the output cannot be parsed as lag."""
        self.mocked_run_sync.return_value = [(nodeset("single1"), results)] if results is not None else []
        with pytest.raises(mysql_legacy.MysqlLegacyError, match=re.escape(error_message)):
            self.single_instance.replication_lag()


class TestMysqlLegacyRemoteHosts:
    """Test class for the MysqlLegacyRemoteHosts class."""

    def setup_method(self):
        """Setup the test environment."""
        # pylint: disable=attribute-defined-outside-init
        self.mocked_run_sync = mock.Mock()
        self.config = Config(get_fixture_path("remote", "config.yaml"))

        remote_hosts = RemoteHosts(self.config, nodeset("host[1-9]"), dry_run=False)
        remote_hosts.run_sync = self.mocked_run_sync
        self.mysql_remote_hosts = mysql_legacy.MysqlLegacyRemoteHosts(remote_hosts)

        remote_host = RemoteHosts(self.config, nodeset("host1"), dry_run=False)
        remote_host.run_sync = self.mocked_run_sync
        self.mysql_remote_host = mysql_legacy.MysqlLegacyRemoteHosts(remote_host)

    def test_run_query(self):
        """Calling run_query() should run the given query in the target hosts."""
        self.mocked_run_sync.return_value = [(nodeset("host[1-9]"), MsgTreeElem(b"result", parent=MsgTreeElem()))]
        results = self.mysql_remote_hosts.run_query("SELECT 'result'")
        assert [(str(host), msg.message().decode()) for host, msg in results] == [("host[1-9]", "result")]
        self.mocked_run_sync.assert_called_once_with(
            "/usr/local/bin/mysql --skip-ssl --skip-column-names --batch -e \"SELECT 'result'\"",
            print_progress_bars=False,
            print_output=False,
        )

    def test_list_host_instances_no_instance(self):
        """It should return an empty list if there are no instances on the host."""
        self.mocked_run_sync.return_value = iter(())
        instances = self.mysql_remote_host.list_hosts_instances()
        assert instances == []  # pylint: disable=use-implicit-booleaness-not-comparison

    def test_list_host_instances_single(self):
        """It should return a list with just one Instance object for the single instance."""
        service = b"mariadb.service loaded active running mariadb database server"
        self.mocked_run_sync.return_value = [(nodeset("host1"), MsgTreeElem(service, parent=MsgTreeElem()))]
        instances = self.mysql_remote_host.list_hosts_instances()
        assert len(instances) == 1
        assert isinstance(instances[0], mysql_legacy.Instance)
        assert str(instances[0].host) == "host1"
        assert instances[0].name == ""
        self.mocked_run_sync.assert_called_once_with(
            "/usr/bin/systemctl --no-pager --type=service --plain --no-legend  list-units 'mariadb*'",
            is_safe=True,
            print_progress_bars=False,
            print_output=False,
        )

    def test_list_host_instances_multi(self):
        """It should return a list with all the instances of a multi-instance host."""
        services = b"\n".join(
            [
                b"mariadb@s1.service loaded active running mariadb database server",
                b"mariadb@s2.service loaded active running mariadb database server",
                b"mariadb-spurious.service loaded active running mariadb database server",
            ]
        )
        self.mocked_run_sync.return_value = [(nodeset("host1"), MsgTreeElem(services, parent=MsgTreeElem()))]
        instances = self.mysql_remote_host.list_hosts_instances()
        assert len(instances) == 2
        for instance in instances:
            assert isinstance(instance, mysql_legacy.Instance)
            assert str(instance.host) == "host1"

        assert instances[0].name == "s1"
        assert instances[1].name == "s2"

    def test_list_host_instances_not_single_host(self):
        """It should raise a NotImplementedError if the MysqlLegacyRemoteHosts instance has multiple hosts."""
        with pytest.raises(NotImplementedError, match="Only single host are supported at this time"):
            self.mysql_remote_hosts.list_hosts_instances()

    def test_list_host_instances_grouped(self):
        """It should raise a NotImplementedError if the grouped parameter is set to True."""
        with pytest.raises(NotImplementedError, match="Grouping and parallelization are not supported at this time"):
            self.mysql_remote_host.list_hosts_instances(group=True)


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
                {"datacenter": "eqiad", "replication_role": "master", "excludes": ("s2",)},
                "A:db-core and A:eqiad and not A:db-section-s2 and A:db-role-master",
                "db10[01-10]",
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
        self.mocked_remote.query.return_value = RemoteHosts(self.config, nodeset(match))
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
        self.mocked_remote.query.return_value = RemoteHosts(self.config, nodeset("db1001"))
        with pytest.raises(mysql_legacy.MysqlLegacyError, match="Matched 1 masters, expected 11"):
            self.mysql.get_core_dbs(datacenter="eqiad", replication_role="master")

        assert self.mocked_remote.query.called

    @pytest.mark.parametrize("mode, value", (("readonly", b"1"), ("readwrite", b"0")))
    def test_set_core_masters_readonly(self, mode, value, caplog):
        """It should set the masters as read-only/read-write."""
        self.mocked_remote.query.return_value = RemoteHosts(self.config, nodeset("db10[01-11]"))
        mock_cumin(self.mocked_transports, 0, retvals=[[("db10[01-11]", value)]])
        with caplog.at_level(logging.DEBUG):
            getattr(self.mysql, "set_core_masters_" + mode)("eqiad")
        assert "SET GLOBAL read_only=" + value.decode() in caplog.text

    @pytest.mark.parametrize("readonly, reply", ((True, b"1"), (False, b"0")))
    def test_verify_core_masters_readonly_ok(self, readonly, reply, caplog):
        """Should verify that the masters have the intended read-only value."""
        self.mocked_remote.query.return_value = RemoteHosts(self.config, nodeset("db10[01-11]"))
        mock_cumin(self.mocked_transports, 0, retvals=[[("db10[01-11]", reply)]])
        with caplog.at_level(logging.DEBUG):
            self.mysql.verify_core_masters_readonly("eqiad", readonly)
        assert "SELECT @@global.read_only" in caplog.text

    def test_verify_core_masters_readonly_fail(self):
        """Should raise MysqlLegacyError if some masters do not have the intended read-only value."""
        self.mocked_remote.query.return_value = RemoteHosts(self.config, nodeset("db10[01-11]"))
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
        hosts = nodeset(EQIAD_CORE_MASTERS_QUERY)
        self.mocked_remote.query.side_effect = [RemoteHosts(self.config, nodeset(host)) for host in hosts] * 2
        retvals = [[(host, b"2018-09-06T10:00:00.000000")] for host in hosts]  # first heartbeat
        retvals += [[(host, b"2018-09-06T10:00:01.000000")] for host in hosts]  # second heartbeat
        mock_cumin(self.mocked_transports, 0, retvals=retvals)
        self.mysql.check_core_masters_in_sync("eqiad", "codfw")
        assert not mocked_sleep.called

    @mock.patch("wmflib.decorators.time.sleep", return_value=None)
    def test_check_core_masters_in_sync_fail_heartbeat(self, mocked_sleep):
        """Should raise MysqlLegacyError if unable to get the heartbeat from the current master."""
        self.mocked_remote.query.return_value = RemoteHosts(self.config, nodeset("db1001"))
        mock_cumin(self.mocked_transports, 0, retvals=[])
        with pytest.raises(mysql_legacy.MysqlLegacyError, match="Unable to get heartbeat from master"):
            self.mysql.check_core_masters_in_sync("eqiad", "codfw")
        assert not mocked_sleep.called

    @mock.patch("wmflib.decorators.time.sleep", return_value=None)
    def test_check_core_masters_in_sync_not_in_sync(self, mocked_sleep):
        """Should raise MysqlLegacyError if a master is not in sync with the one in the other DC."""
        hosts = nodeset(EQIAD_CORE_MASTERS_QUERY)
        self.mocked_remote.query.side_effect = [RemoteHosts(self.config, nodeset(host)) for host in hosts] + [
            RemoteHosts(self.config, nodeset("db1001"))
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
        self.mocked_remote.query.return_value = RemoteHosts(self.config, nodeset("db1001"))
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
        self.mocked_remote.query.return_value = RemoteHosts(self.config, nodeset("db1001"))
        mock_cumin(self.mocked_transports, 0, retvals=[])
        with pytest.raises(mysql_legacy.MysqlLegacyError, match="Unable to get heartbeat from master"):
            self.mysql.check_core_masters_heartbeats("eqiad", "codfw", {"s1": datetime.utcnow()})

        assert mocked_sleep.called
