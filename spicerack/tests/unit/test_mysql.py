"""Mysql module tests."""

import json
import logging
import re
from datetime import datetime
from decimal import Decimal
from unittest import mock

import pytest
from ClusterShell.MsgTree import MsgTreeElem
from cumin import Config, nodeset
from cumin.transports import Command
from pymysql.cursors import DictCursor

from spicerack import mysql
from spicerack.constants import WMF_CA_BUNDLE_PATH
from spicerack.remote import Remote, RemoteExecutionError, RemoteHosts
from spicerack.tests import get_fixture_path
from spicerack.tests.unit.test_remote import mock_cumin

EQIAD_CORE_MASTERS_QUERY = "db10[01-11]"
CODFW_CORE_MASTERS_QUERY = "db20[01-11]"
VERTICAL_QUERY_NEWLINE = """*************************** 1. row ***************************
test: line with
a newline
"""
MASTER_STATUS = {"Binlog_Do_DB": "", "Binlog_Ignore_DB": "", "File": "host1-bin.001234", "Position": 123456782}


class TestInstance:
    """Test class for the Instance class."""

    @mock.patch("spicerack.mysql.MysqlClient", autospec=True)
    def setup_method(self, _, mocked_pymysql_connection):
        """Setup the test environment."""
        # pylint: disable=attribute-defined-outside-init
        self.mocked_pymysql = mocked_pymysql_connection.return_value
        self.mocked_cursor = (
            self.mocked_pymysql.connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        )
        self.mocked_run_sync = mock.Mock()
        self.config = Config(get_fixture_path("remote", "config.yaml"))
        single = RemoteHosts(self.config, nodeset("single1"), dry_run=False)
        single_dry_run = RemoteHosts(self.config, nodeset("single1"))
        single.run_sync = self.mocked_run_sync
        multi = RemoteHosts(self.config, nodeset("multi1"), dry_run=False)
        multi.run_sync = self.mocked_run_sync
        self.single_instance = mysql.Instance(single)
        self.multi_instance = mysql.Instance(multi, name="instance1")
        self.single_instance_dry_run = mysql.Instance(single_dry_run)

    def test_init_raise(self):
        """It should raise a NotImplementedError exception if more than one host is passed to the constructor."""
        with pytest.raises(NotImplementedError, match="Only single hosts are currently supported"):
            mysql.Instance(RemoteHosts(self.config, nodeset("host[1-2]")))

    @pytest.mark.parametrize(
        "instance, expected",
        (("single_instance", "single1 (single-instance)"), ("multi_instance", "multi1 (instance1)")),
    )
    def test_str(self, instance, expected):
        """It should return a string representation of the instance."""
        assert str(getattr(self, instance)) == expected

    @pytest.mark.parametrize(
        "instance, expected",
        [
            ("single_instance", "/srv/sqldata"),
            ("multi_instance", "/srv/sqldata.instance1"),
        ],
    )
    def test_data_dir(self, instance, expected):
        """It should return the correct data directory path for single and multi instances."""
        assert getattr(self, instance).data_dir == expected

    @pytest.mark.parametrize(
        "instance, expected",
        [
            ("single_instance", "/run/mysqld/mysqld.sock"),
            ("multi_instance", "/run/mysqld/mysqld.instance1.sock"),
        ],
    )
    def test_socket(self, instance, expected):
        """It should return the correct socket path for single and multi instances."""
        assert getattr(self, instance).socket == expected

    def test_cursor(self):
        """It should allow to perform queries on the target instance via the pymysql library."""
        with self.single_instance.cursor(database="mydatabase") as (connection, cursor):
            assert connection is self.mocked_pymysql.connect.return_value.__enter__.return_value
            assert self.mocked_pymysql.connect.call_args.kwargs["database"] == "mydatabase"
            cursor.execute("SELECT * FROM table")
            cursor.fetchall()

        self.mocked_cursor.execute.assert_called_once_with("SELECT * FROM table")
        self.mocked_cursor.fetchall.assert_called_once_with()

    def test_check_warnings_absent(self):
        """It should just return if there are no warnings."""
        self.mocked_cursor.execute.return_value = 0
        with self.single_instance.cursor() as (_connection, cursor):
            cursor.execute("SELECT 1")
            self.single_instance.check_warnings(cursor)

        self.mocked_cursor.execute.assert_called_with("SHOW WARNINGS")

    @mock.patch("spicerack.mysql.ask_confirmation")
    def test_check_warnings_present(self, mocked_ask_confirmation, caplog):
        """It should log the warnings and ask the operator what to do if there are warnings."""
        self.mocked_cursor.execute.side_effect = [0, 1]
        self.mocked_cursor.fetchall.return_value = [{"Level": "Warning", "Code": 123, "Message": "Some error"}]

        with caplog.at_level(logging.WARNING):
            with self.single_instance.cursor() as (_connection, cursor):
                cursor.execute("SELECT 1")
                self.single_instance.check_warnings(cursor)

        self.mocked_cursor.execute.assert_called_with("SHOW WARNINGS")
        mocked_ask_confirmation.assert_called_once_with(
            "The above warnings were raised during the last query, do you want to proceed anyway?"
        )
        assert "[Warning] 123: Some error" in caplog.text

    @pytest.mark.parametrize(
        "instance, is_safe",
        (
            ("single_instance", False),
            ("single_instance", True),
            ("single_instance_dry_run", True),
        ),
    )
    def test_execute(self, instance, is_safe):
        """It should execute a query within a cursor context just returning the number of affected rows."""
        self.mocked_cursor.execute.side_effect = [2, 0]
        num_rows = getattr(self, instance).execute("RESET SLAVE ALL", is_safe=is_safe)
        assert num_rows == 2
        self.mocked_cursor.execute.assert_has_calls([mock.call("RESET SLAVE ALL", None), mock.call("SHOW WARNINGS")])

    def test_execute_dry_run_unsafe(self):
        """It should not execute the query and return 0."""
        self.mocked_cursor.mogrify.return_value = "RESET SLAVE ALL"
        num_rows = self.single_instance_dry_run.execute("RESET SLAVE ALL")
        assert num_rows == 0
        self.mocked_cursor.mogrify.assert_called_once_with("RESET SLAVE ALL", None)
        self.mocked_cursor.execute.assert_not_called()

    def test_fetch_one_row_ok(self):
        """It should return the row, checking for warnings."""
        self.mocked_cursor.execute.side_effect = [1, 0]
        self.mocked_cursor.fetchone.return_value = {"value": 1}
        row = self.single_instance.fetch_one_row("SELECT 1 AS value")
        assert row == {"value": 1}
        self.mocked_cursor.execute.assert_has_calls([mock.call("SELECT 1 AS value", None), mock.call("SHOW WARNINGS")])
        self.mocked_cursor.fetchone.assert_called_once_with()

    def test_fetch_one_row_empty(self):
        """It should return None if no rows are returned."""
        self.mocked_cursor.execute.return_value = 0
        row = self.single_instance.fetch_one_row("SELECT 1 WHERE 2 > 1")
        assert row == {}
        self.mocked_cursor.execute.assert_has_calls(
            [mock.call("SELECT 1 WHERE 2 > 1", None), mock.call("SHOW WARNINGS")]
        )
        self.mocked_cursor.fetchone.assert_not_called()

    def test_fetch_one_row_too_many(self):
        """It should raise a MysqlError if more than one row is returned."""
        self.mocked_cursor.execute.side_effect = [3, 0]
        with pytest.raises(mysql.MysqlError, match="Expected query to return zero or one row, got 3 instead"):
            self.single_instance.fetch_one_row("SELECT * FROM mytable", database="mydb")
        self.mocked_cursor.execute.assert_has_calls(
            [mock.call("SELECT * FROM mytable", None), mock.call("SHOW WARNINGS")]
        )
        self.mocked_cursor.fetchone.assert_not_called()

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
        """It should raise a MysqlError exception if the query execution fails."""
        self.mocked_run_sync.side_effect = RemoteExecutionError(retcode=1, message="error", results=iter(()))
        with pytest.raises(mysql.MysqlError, match="Failed to run 'invalid' on multi1"):
            self.multi_instance.run_query("invalid")

        self.mocked_run_sync.assert_called_once_with(
            '/usr/local/bin/mysql --socket /run/mysqld/mysqld.instance1.sock --batch --execute "invalid"',
            print_progress_bars=False,
            print_output=False,
        )

    def test_run_vertical_query_ok(self):
        """It should return the current slave status of the database."""
        status = get_fixture_path("mysql", "single_show_slave_status.out").read_text()
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

    def test_run_vertical_query_no_reponse(self):
        """It should return an empty list. This should not happen in real life."""
        self.mocked_run_sync.return_value = []
        rows = self.single_instance.run_vertical_query("SELECT")  # dummy query
        assert rows == []  # pylint: disable=use-implicit-booleaness-not-comparison

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

    @pytest.mark.parametrize(
        "output,expected",
        (
            (b"ActiveState=active\nSubState=running", True),
            (b"ActiveState=inactive\nSubState=running", False),
            (b"ActiveState=active\nSubState=stopped", False),
        ),
    )
    def test_is_running(self, output, expected):
        """It should return True if the service is active and running."""
        self.mocked_run_sync.return_value = [(nodeset("single1"), MsgTreeElem(output, parent=MsgTreeElem()))]
        assert self.single_instance.is_running() is expected

    @pytest.mark.parametrize("instance", ("single_instance", "multi_instance"))
    @pytest.mark.parametrize(
        "method, expected",
        (
            ("stop_slave", "STOP SLAVE"),
            ("start_slave", "START SLAVE"),
        ),
    )
    @mock.patch("spicerack.mysql.sleep", return_value=None)
    def test_run_stop_start_slave_ok(self, mocked_sleep, method, expected, instance):
        """It should run the method called and execute the related query."""
        self.mocked_cursor.execute.return_value = 0
        getattr(getattr(self, instance), method)()
        self.mocked_cursor.execute.assert_any_call(expected, None)
        assert mocked_sleep.called == (method == "start_slave")

    def test_single_show_slave_status_ok(self):
        """It should return the current slave status of the database."""
        mocked_status = json.loads(get_fixture_path("mysql", "single_show_slave_status.json").read_text())
        self.mocked_cursor.execute.return_value = 1
        self.mocked_cursor.fetchone.return_value = mocked_status

        status = self.single_instance.show_slave_status()
        assert status["Master_Host"] == "host1.example.org"
        assert status["Seconds_Behind_Master"] == 0
        assert status == mocked_status
        self.mocked_cursor.execute.assert_called_once_with("SHOW SLAVE STATUS")
        self.mocked_cursor.fetchone.assert_called_once_with()

    def test_single_show_slave_status_on_master(self):
        """It should raise a MysqlError exception if show slave status is called on a master."""
        self.mocked_cursor.execute.return_value = 0

        with pytest.raises(
            mysql.MysqlError, match=re.escape("SHOW SLAVE STATUS seems to have been executed on a master")
        ):
            self.single_instance.show_slave_status()

        self.mocked_cursor.fetchone.assert_not_called()

    def test_single_show_slave_status_multisource(self):
        """It should raise a MysqlError exception if show slave status is called on a multisource instance."""
        self.mocked_cursor.execute.return_value = 2
        with pytest.raises(NotImplementedError, match="Multisource setup are not implemented"):
            self.single_instance.show_slave_status()

        self.mocked_cursor.fetchone.assert_not_called()

    def test_single_show_master_status_ok(self):
        """It should return the current master status of the database."""
        self.mocked_cursor.execute.side_effect = [1, 0]
        self.mocked_cursor.fetchone.return_value = MASTER_STATUS

        status = self.single_instance.show_master_status()

        assert status["File"] == "host1-bin.001234"
        assert status["Position"] == 123456782
        self.mocked_cursor.execute.assert_has_calls([mock.call("SHOW MASTER STATUS", None), mock.call("SHOW WARNINGS")])
        self.mocked_cursor.fetchone.assert_called_once_with()

    def test_single_show_master_status_no_binlog(self):
        """It should raise a MysqlError if show master status is run on a host with binlog disabled."""
        self.mocked_cursor.execute.return_value = 0
        with pytest.raises(
            mysql.MysqlError,
            match=re.escape("SHOW MASTER STATUS seems to have been executed on a host with binlog disabled"),
        ):
            self.single_instance.show_master_status()

        self.mocked_cursor.execute.assert_has_calls([mock.call("SHOW MASTER STATUS", None), mock.call("SHOW WARNINGS")])
        self.mocked_cursor.fetchone.assert_not_called()

    @pytest.mark.parametrize(
        "setting, expected",
        (
            (mysql.MasterUseGTID.CURRENT_POS, "current_pos"),
            (mysql.MasterUseGTID.SLAVE_POS, "slave_pos"),
            (mysql.MasterUseGTID.NO, "no"),
        ),
    )
    def test_set_master_use_gtid_ok(self, setting, expected):
        """It should execute MASTER_USE_GTID with the given value."""
        self.mocked_cursor.execute.return_value = 0
        self.single_instance.set_master_use_gtid(setting)
        self.mocked_cursor.execute.assert_any_call(f"CHANGE MASTER TO MASTER_USE_GTID={expected}", None)

    def test_set_master_use_gtid_invalid(self):
        """It should raise MysqlError if called with an invalid setting."""
        with pytest.raises(
            mysql.MysqlError,
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

        command = f"/usr/bin/systemctl {method} mariadb{suffix}.service"
        if method == "status":
            command = Command(command, ok_codes=[])
        self.mocked_run_sync.assert_called_once_with(command, **kwargs)

    @pytest.mark.parametrize(
        "instance, path",
        (
            ("single_instance", "/srv/sqldata"),
            ("multi_instance", "/srv/sqldata.instance1"),
        ),
    )
    @pytest.mark.parametrize("skip_confirmation", (False, True))
    @mock.patch("spicerack.mysql.ask_confirmation")
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
        mocked_status = json.loads(get_fixture_path("mysql", "single_show_slave_status.json").read_text())
        self.mocked_cursor.execute.return_value = 1
        self.mocked_cursor.fetchone.return_value = mocked_status

        info = self.single_instance.get_replication_info()

        assert info.primary == "host1.example.org"
        assert info.binlog == "host1-bin.001234"
        assert info.position == 123456782
        self.mocked_cursor.execute.assert_called_once_with("SHOW SLAVE STATUS")
        self.mocked_cursor.fetchone.assert_called_once_with()

    def test_get_replication_info_raise(self):
        """It should raise a MysqlError if unable to get the replication information."""
        mocked_status = json.loads(get_fixture_path("mysql", "single_show_slave_status.json").read_text())
        del mocked_status["Master_Host"]  # Make it invalid
        self.mocked_cursor.execute.return_value = 1
        self.mocked_cursor.fetchone.return_value = mocked_status

        with pytest.raises(mysql.MysqlError, match="Could not find the replication position"):
            self.single_instance.get_replication_info()

        self.mocked_cursor.execute.assert_called_once_with("SHOW SLAVE STATUS")
        self.mocked_cursor.fetchone.assert_called_once_with()

    def test_primary_ok(self):
        """It should return the hostname of the primary host for this host."""
        mocked_status = json.loads(get_fixture_path("mysql", "single_show_slave_status.json").read_text())
        self.mocked_cursor.execute.return_value = 1
        self.mocked_cursor.fetchone.return_value = mocked_status

        assert self.single_instance.primary == "host1.example.org"

        self.mocked_cursor.execute.assert_called_once_with("SHOW SLAVE STATUS")
        # Ensure the caching of the result works
        self.single_instance.primary  # pylint: disable=pointless-statement
        assert self.mocked_cursor.execute.call_count == 1
        assert self.mocked_cursor.fetchone.call_count == 1

    @pytest.mark.parametrize("no_content", (False, True))
    def test_primary_raise(self, no_content):
        """It should raise a MysqlError if there is no primary or is run on a master."""
        mocked_status = json.loads(get_fixture_path("mysql", "single_show_slave_status.json").read_text())
        del mocked_status["Master_Host"]  # Make it invalid
        self.mocked_cursor.execute.return_value = 0 if no_content else 1
        self.mocked_cursor.fetchone.return_value = None if no_content else mocked_status

        with pytest.raises(mysql.MysqlError, match="Unable to retrieve master host"):
            self.single_instance.primary  # pylint: disable=pointless-statement

        if not no_content:
            self.mocked_cursor.fetchone.assert_called_once_with()

    def test_prep_src_for_cloning(self):
        """It should run the preparation commands before cloning."""
        mocked_status = json.loads(get_fixture_path("mysql", "single_show_slave_status.json").read_text())
        self.mocked_cursor.execute.side_effect = [0, 0, 1, 0]
        self.mocked_cursor.fetchone.return_value = mocked_status
        self.mocked_run_sync.return_value = [(nodeset("single1"), iter(()))]

        info = self.single_instance.prep_src_for_cloning()

        assert info.primary == "host1.example.org"
        self.mocked_run_sync.assert_called_once_with("/usr/bin/systemctl stop mariadb.service")
        self.mocked_cursor.execute.assert_any_call("STOP SLAVE", None)
        self.mocked_cursor.execute.assert_any_call("SHOW SLAVE STATUS")
        self.mocked_cursor.fetchone.assert_called_once_with()

    def test_set_replication_parameters(self):
        """It should set the replication to the given parameters."""
        info = mysql.ReplicationInfo(
            primary="host1.example.org", binlog="host1-bin.001234", position=123456782, port=3306
        )
        self.mocked_cursor.execute.return_value = 0

        self.multi_instance.set_replication_parameters(replication_info=info, user="user", password="dummy")

        call_args = self.mocked_cursor.execute.call_args_list[0].args
        for part in (
            "CHANGE MASTER TO",
            "master_host=%(primary)s",
            "master_port=%(port)s",
            "master_ssl=1",
            "master_log_file=%(binlog)s",
            "master_log_pos=%(position)s",
            "master_user=%(user)s",
            "password=%(password)s",
        ):
            assert part in call_args[0]

        expected = {
            "primary": "host1.example.org",
            "port": 3306,
            "binlog": "host1-bin.001234",
            "position": 123456782,
            "user": "user",
            "password": "dummy",
        }
        for key, value in expected.items():
            assert call_args[1][key] == value

    def test_post_clone_reset_with_slave_stopped(self):
        """It should start mysql with slave stopped and reset all slave information."""
        self.mocked_run_sync.side_effect = [[(nodeset("single1"), iter(()))]] * 3
        self.mocked_cursor.execute.return_value = 0

        self.single_instance.post_clone_reset_with_slave_stopped()

        calls = self.mocked_run_sync.call_args_list
        assert calls[0][0][0].endswith("chown -R mysql:mysql /srv/sqldata")
        assert calls[0][0][1].endswith('set-environment MYSQLD_OPTS="--skip-slave-start"')
        assert calls[1][0][0].endswith("systemctl start mariadb.service")
        self.mocked_cursor.execute.assert_any_call("STOP SLAVE", None)
        self.mocked_cursor.execute.assert_any_call("RESET SLAVE ALL", None)

    @mock.patch("spicerack.mysql.sleep", return_value=None)
    def test_resume_replication(self, mocked_sleep):
        """It should start mysql, upgrade it, restart it and resume the replication."""
        self.mocked_run_sync.side_effect = [[(nodeset("single1"), iter(()))]] * 4
        self.mocked_cursor.execute.return_value = 0

        self.single_instance.resume_replication()

        calls = self.mocked_run_sync.call_args_list
        assert calls[0][0][0].endswith('set-environment MYSQLD_OPTS="--skip-slave-start"')
        assert calls[1][0][0].endswith("systemctl start mariadb.service")
        assert calls[2][0][0].endswith(
            "$(readlink -f /usr/local/bin/mysql_upgrade) --socket /run/mysqld/mysqld.sock --force"
        )
        assert calls[3][0][0].endswith("systemctl restart mariadb.service")
        self.mocked_cursor.execute.assert_any_call("START SLAVE", None)
        mocked_sleep.assert_called_once_with(1)

    @pytest.mark.parametrize("threshold", (0, Decimal("0.1234"), 0.5))
    @mock.patch("wmflib.decorators.time.sleep", return_value=None)
    def test_wait_for_replication_already_ok(self, mocked_sleep, threshold):
        """If the replication is already in sync it should return immediately."""
        self.mocked_cursor.execute.side_effect = [1, 0]
        self.mocked_cursor.fetchone.return_value = {"lag": Decimal("0.1234")}
        if threshold:
            self.single_instance.wait_for_replication(threshold)
        else:
            threshold = 1.0
            self.multi_instance.wait_for_replication()

        assert self.mocked_cursor.execute.call_count == 2
        assert self.mocked_pymysql.connect.call_args.kwargs["database"] == "heartbeat"
        self.mocked_cursor.fetchone.assert_called_once_with()
        mocked_sleep.assert_not_called()

    @mock.patch("wmflib.decorators.time.sleep", return_value=None)
    def test_wait_for_replication_sleep_ok(self, mocked_sleep):
        """If the replication is not yet in sync it should wait until it gets in sync, within the timeout."""
        self.mocked_cursor.execute.side_effect = [1, 0] * 6
        lags = [{"lag": Decimal("1.2345")}] * 5
        lags.append({"lag": Decimal("0.1234")})
        self.mocked_cursor.fetchone.side_effect = lags

        self.single_instance.wait_for_replication()

        assert mocked_sleep.call_count == 5

    @mock.patch("wmflib.decorators.time.sleep", return_value=None)
    def test_wait_for_replication_fail(self, mocked_sleep):
        """If the replication is not in sync within the timeout it should raise a MysqlReplagError exception."""
        self.mocked_cursor.execute.side_effect = [1, 0] * 480
        self.mocked_cursor.fetchone.side_effect = [{"lag": Decimal("1.2345")}] * 480

        with pytest.raises(
            mysql.MysqlReplagError,
            match=re.escape("Replication lag higher than the threshold (1.0s): 1.2345s"),
        ):
            self.single_instance.wait_for_replication()

        assert mocked_sleep.call_count == 479

    def test_replication_lag_ok(self):
        """It should return the current replication lag as float."""
        self.mocked_cursor.execute.side_effect = [1, 0]
        self.mocked_cursor.fetchone.return_value = {"lag": Decimal("0.1234")}
        assert self.single_instance.replication_lag() == Decimal("0.1234")
        assert "TIMESTAMPDIFF" in self.mocked_cursor.execute.call_args_list[0].args[0]

    def test_replication_lag_no_data(self):
        """It should raise a MysqlError if the query returns no rows."""
        self.mocked_cursor.execute.return_value = 0
        with pytest.raises(mysql.MysqlError, match="The replication lag query returned no data"):
            self.single_instance.replication_lag()

        self.mocked_cursor.fetchone.assert_not_called()

    @pytest.mark.parametrize(
        "row",
        (
            {"lag": None},
            {"invalid": Decimal(0.1234)},
        ),
    )
    def test_replication_lag_no_lag(self, row):
        """It should raise a MysqlLegacyError if the returned lag is None or invalid."""
        self.mocked_cursor.execute.side_effect = [1, 0]
        self.mocked_cursor.fetchone.return_value = row
        error_message = f"Unable to get lag information from: {row}"

        with pytest.raises(mysql.MysqlError, match=re.escape(error_message)):
            self.single_instance.replication_lag()

        self.mocked_cursor.fetchone.assert_called_once_with()


class TestMysqlRemoteHosts:
    """Test class for the MysqlRemoteHosts class."""

    def setup_method(self):
        """Setup the test environment."""
        # pylint: disable=attribute-defined-outside-init
        self.mocked_run_sync = mock.Mock()
        self.config = Config(get_fixture_path("remote", "config.yaml"))

        remote_hosts = RemoteHosts(self.config, nodeset("host[1-9]"), dry_run=False)
        remote_hosts.run_sync = self.mocked_run_sync
        self.mysql_remote_hosts = mysql.MysqlRemoteHosts(remote_hosts)

        remote_host = RemoteHosts(self.config, nodeset("host1"), dry_run=False)
        remote_host.run_sync = self.mocked_run_sync
        self.mysql_remote_host = mysql.MysqlRemoteHosts(remote_host)

    def test_iter(self):
        """It should iterate the instance yielding instances of the same class with one host."""
        expected = ["host1", "host2", "host3", "host4", "host5", "host6", "host7", "host8", "host9"]
        for index, mysql_remote_host in enumerate(self.mysql_remote_hosts):
            assert isinstance(mysql_remote_host, mysql.MysqlRemoteHosts)
            assert str(mysql_remote_host) == expected[index]

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
        self.mocked_run_sync.side_effect = [
            [],  # Empty ls result
            RemoteExecutionError(retcode=1, message="error", results=iter(())),  # Empty grep result
        ]
        instances = self.mysql_remote_host.list_hosts_instances()
        assert isinstance(instances, list)
        assert not instances

    def test_list_host_instances_single(self):
        """It should return a list with just one Instance object for the single instance."""
        self.mocked_run_sync.side_effect = [[], []]  # Empty ls and successful grep -q
        instances = self.mysql_remote_host.list_hosts_instances()
        assert len(instances) == 1
        assert isinstance(instances[0], mysql.Instance)
        assert str(instances[0].host) == "host1"
        assert instances[0].name == ""

    def test_list_host_instances_multi(self):
        """It should return a list with all the instances of a multi-instance host."""
        configs = b"instance1.cnf\ninstance2.cnf"
        self.mocked_run_sync.return_value = [(nodeset("host1"), MsgTreeElem(configs, parent=MsgTreeElem()))]
        instances = self.mysql_remote_host.list_hosts_instances()
        assert len(instances) == 2
        for instance in instances:
            assert isinstance(instance, mysql.Instance)
            assert str(instance.host) == "host1"

        assert instances[0].name == "instance1"
        assert instances[1].name == "instance2"

    def test_list_host_instances_not_single_host(self):
        """It should raise a NotImplementedError if the MysqlRemoteHosts instance has multiple hosts."""
        with pytest.raises(NotImplementedError, match="Only single host are supported at this time"):
            self.mysql_remote_hosts.list_hosts_instances()

    def test_list_host_instances_grouped(self):
        """It should raise a NotImplementedError if the grouped parameter is set to True."""
        with pytest.raises(NotImplementedError, match="Grouping and parallelization are not supported at this time"):
            self.mysql_remote_host.list_hosts_instances(group=True)


class TestMysql:
    """Mysql class tests."""

    @mock.patch("spicerack.remote.transports", autospec=True)
    def setup_method(self, _, mocked_transports):
        """Initialize the test environment for Mysql."""
        # pylint: disable=attribute-defined-outside-init
        self.config = Config(get_fixture_path("remote", "config.yaml"))
        self.mocked_transports = mocked_transports
        self.mocked_remote = mock.MagicMock(spec_set=Remote)
        self.mysql = mysql.Mysql(self.mocked_remote, dry_run=False)

    def test_get_dbs(self):
        """It should return and instance of MysqlRemoteHosts for the matching hosts."""
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
        """It should raise MysqlError if called with invalid parameters."""
        key = list(kwargs.keys())[0]
        message = f"Got invalid {key}"
        with pytest.raises(mysql.MysqlError, match=message):
            self.mysql.get_core_dbs(**kwargs)

        assert not self.mocked_remote.query.called

    def test_get_core_dbs_fail_sanity_check(self):
        """It should raise MysqlError if matching an invalid number of hosts when looking for masters."""
        self.mocked_remote.query.return_value = RemoteHosts(self.config, nodeset("db1001"))
        with pytest.raises(mysql.MysqlError, match="Matched 1 masters, expected 11"):
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
        """Should raise MysqlError if some masters do not have the intended read-only value."""
        self.mocked_remote.query.return_value = RemoteHosts(self.config, nodeset("db10[01-11]"))
        mock_cumin(
            self.mocked_transports,
            0,
            retvals=[[("db1001", b"0"), ("db10[02-11]", b"1")]],
        )
        with pytest.raises(
            mysql.MysqlError,
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
        """Should raise MysqlError if unable to get the heartbeat from the current master."""
        self.mocked_remote.query.return_value = RemoteHosts(self.config, nodeset("db1001"))
        mock_cumin(self.mocked_transports, 0, retvals=[])
        with pytest.raises(mysql.MysqlError, match="Unable to get heartbeat from master"):
            self.mysql.check_core_masters_in_sync("eqiad", "codfw")
        assert not mocked_sleep.called

    @mock.patch("wmflib.decorators.time.sleep", return_value=None)
    def test_check_core_masters_in_sync_not_in_sync(self, mocked_sleep):
        """Should raise MysqlError if a master is not in sync with the one in the other DC."""
        hosts = nodeset(EQIAD_CORE_MASTERS_QUERY)
        self.mocked_remote.query.side_effect = [RemoteHosts(self.config, nodeset(host)) for host in hosts] + [
            RemoteHosts(self.config, nodeset("db1001"))
        ] * 3
        retvals = [[(host, b"2018-09-06T10:00:00.000000")] for host in hosts]  # first heartbeat
        retvals += [[("db1001", b"2018-09-06T10:00:00.000000")]] * 3  # 3 failed retries of second heartbeat
        mock_cumin(self.mocked_transports, 0, retvals=retvals)
        with pytest.raises(
            mysql.MysqlError,
            match=r"Heartbeat from master db1001 for section .* not yet in sync",
        ):
            self.mysql.check_core_masters_in_sync("eqiad", "codfw")

        assert mocked_sleep.called

    def test_get_core_masters_heartbeats_wrong_data(self):
        """Should raise MysqlError if unable to convert the heartbeat into a datetime."""
        self.mocked_remote.query.return_value = RemoteHosts(self.config, nodeset("db1001"))
        mock_cumin(
            self.mocked_transports,
            0,
            retvals=[[("db1001", b"2018-09-06-10:00:00.000000")]],
        )
        with pytest.raises(mysql.MysqlError, match="Unable to convert heartbeat"):
            self.mysql.get_core_masters_heartbeats("eqiad", "codfw")

    @mock.patch("wmflib.decorators.time.sleep", return_value=None)
    def test_check_core_masters_heartbeats_fail(self, mocked_sleep):
        """Should raise MysqlError if unable to get the heartbeat from the master."""
        self.mocked_remote.query.return_value = RemoteHosts(self.config, nodeset("db1001"))
        mock_cumin(self.mocked_transports, 0, retvals=[])
        with pytest.raises(mysql.MysqlError, match="Unable to get heartbeat from master"):
            self.mysql.check_core_masters_heartbeats("eqiad", "codfw", {"s1": datetime.utcnow()})

        assert mocked_sleep.called


class TestMysqlClient:
    """MysqlClient class tests."""

    @mock.patch("spicerack.mysql.Connection", autospec=True)
    def test_connect_default(self, mocked_pymsql_connection):
        """It should call pymysql with the correct parameters."""
        my = mysql.MysqlClient(dry_run=False)
        with my.connect() as conn:
            assert conn == mocked_pymsql_connection.return_value
            call_args = mocked_pymsql_connection.call_args.kwargs
            # Ensure close is not called before context manager exits
            conn.close.assert_not_called()  # pylint: disable=maybe-no-member

        conn.close.assert_called_once_with()  # pylint: disable=maybe-no-member

        # Ensure the default args were passed
        if call_args.get("host") == "clouddb1001":
            assert call_args["read_default_group"] == "clientlabsdb"
        else:
            assert call_args["read_default_group"] == "client"

        assert call_args["charset"] == "utf8mb4"
        assert call_args["cursorclass"] == DictCursor
        assert call_args["read_default_file"].endswith("/.my.cnf")
        assert call_args["ssl"] == {"ca": WMF_CA_BUNDLE_PATH}

    @pytest.mark.parametrize(
        "kwargs",
        (
            {"host": "db9999"},
            {"charset": "ascii"},
            {"charset": ""},
            {"read_default_file": "/my.cnf"},
            {"read_default_file": None, "read_default_group": None},
            {"read_default_group": "client_test"},
            {"host": "clouddb1001"},
            {"ssl": {}},
            {"ssl": {1: 3}},
        ),
    )
    @mock.patch("spicerack.mysql.Connection", autospec=True)
    def test_connect(self, mocked_pymsql_connection, kwargs):
        """It should call pymysql with the correct parameters."""
        my = mysql.MysqlClient(dry_run=False)
        with my.connect(**kwargs) as conn:
            assert conn == mocked_pymsql_connection.return_value
            call_args = mocked_pymsql_connection.call_args.kwargs
            # Ensure close is not called before context manager exits
            conn.close.assert_not_called()  # pylint: disable=maybe-no-member

        conn.close.assert_called_once_with()  # pylint: disable=maybe-no-member
        # Ensure the args we passed were passed along
        for key, value in kwargs.items():
            assert call_args[key] == value

    @pytest.mark.parametrize(
        "dry_run, read_only, transaction_ro",
        (
            (False, False, False),
            (False, True, True),
            (True, False, True),
            (True, True, True),
        ),
    )
    @mock.patch("spicerack.mysql.Connection", autospec=True)
    def test_connect_read_only(self, mocked_pymsql_connection, dry_run, read_only, transaction_ro):
        """It should start a read-only transaction if either dry-run or read-only are set."""
        my = mysql.MysqlClient(dry_run=dry_run)
        with my.connect(read_only=read_only) as conn:
            assert conn == mocked_pymsql_connection.return_value
            execute = conn.cursor.return_value.__enter__.return_value.execute  # pylint: disable=no-member
            print(mocked_pymsql_connection.mock_calls)
            if transaction_ro:
                execute.assert_called_once_with("SET SESSION TRANSACTION READ ONLY")
            else:
                execute.assert_not_called()
