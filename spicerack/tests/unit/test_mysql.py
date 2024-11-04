"""Mysql module tests."""

from unittest import mock

import pytest
from pymysql.cursors import DictCursor

from spicerack import mysql
from spicerack.constants import PUPPET_CA_PATH


class TestMysql:
    """Mysql class tests."""

    @mock.patch("spicerack.mysql.Connection", autospec=True)
    def test_connect_default(self, mocked_pymsql_connection):
        """It should call pymysql with the correct parameters."""
        my = mysql.Mysql(dry_run=False)
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
        assert call_args["ssl"] == {"ca": PUPPET_CA_PATH}

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
        my = mysql.Mysql(dry_run=False)
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
        my = mysql.Mysql(dry_run=dry_run)
        with my.connect(read_only=read_only) as conn:
            assert conn == mocked_pymsql_connection.return_value
            execute = conn.cursor.return_value.__enter__.return_value.execute  # pylint: disable=no-member
            print(mocked_pymsql_connection.mock_calls)
            if transaction_ro:
                execute.assert_called_once_with("SET SESSION TRANSACTION READ ONLY")
            else:
                execute.assert_not_called()
