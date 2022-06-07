"""Mysql module tests."""
from pathlib import Path
from unittest import mock

import pytest

from spicerack import mysql
from spicerack.constants import PUPPET_CA_PATH


class TestMysql:
    """Mysql class tests."""

    def make_match_from_defaults(self, kwargs, match):
        """Removes the need to put 'obvious' expectations in match."""
        if "charset" not in match:
            match["charset"] = kwargs.get("charset", "utf8mb4")

        if "read_default_file" not in match:
            match["read_default_file"] = kwargs.get("read_default_file", str(Path("~/.my.cnf").expanduser()))
        if "read_default_group" not in match:
            match["read_default_group"] = kwargs.get("read_default_group", "client")

        if "ssl" not in match:
            match["ssl"] = kwargs.get("ssl", {"ca": PUPPET_CA_PATH})

    @pytest.mark.parametrize(
        "kwargs, match",
        (
            ({}, {}),
            ({"host": "db9999"}, {"host": "db9999"}),
            ({"charset": "ascii"}, {"charset": "ascii"}),
            ({"charset": ""}, {"charset": ""}),
            ({"read_default_file": "/my.cnf"}, {"read_default_file": "/my.cnf"}),
            (
                {"read_default_file": None},
                {"read_default_file": None, "read_default_group": None},
            ),
            (
                {"read_default_group": "client_test"},
                {"read_default_group": "client_test"},
            ),
            (
                {"host": "labsdb9999"},
                {"host": "labsdb9999", "read_default_group": "clientlabsdb"},
            ),
            ({"ssl": {}}, {"ssl": {}}),
            ({"ssl": {1: 3}}, {"ssl": {1: 3}}),
        ),
    )
    @mock.patch("spicerack.mysql.Connection", autospec=True)
    def test_connect(self, mocked_pymsql_connect, kwargs, match):
        """It should call pymysql with the correct parameters."""
        my = mysql.Mysql(dry_run=False)
        self.make_match_from_defaults(kwargs, match)
        with my.connect(**kwargs) as conn:
            assert conn == mocked_pymsql_connect.return_value
            mocked_pymsql_connect.assert_called_once_with(**match)
            # Ensure close is not called before context manager exits
            conn.close.assert_not_called()  # pylint: disable=maybe-no-member
        conn.close.assert_called_once_with()  # pylint: disable=maybe-no-member

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
    def test_connect_read_only(self, mocked_pymsql_connect, dry_run, read_only, transaction_ro):
        """It should start a read-only transaction if either dry-run or read-only are set."""
        my = mysql.Mysql(dry_run=dry_run)
        with my.connect(read_only=read_only) as conn:
            assert conn == mocked_pymsql_connect.return_value
            if transaction_ro:
                conn.query.assert_called_once_with(  # pylint: disable=maybe-no-member
                    "SET SESSION TRANSACTION READ ONLY"
                )
            else:
                conn.query.assert_not_called()  # pylint: disable=maybe-no-member
