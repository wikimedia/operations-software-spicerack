"""Mysql module tests."""
from unittest import mock

import pytest

from cumin import Config, NodeSet

from spicerack import mysql
from spicerack.remote import Remote

from spicerack.tests import get_fixture_path
from spicerack.tests.unit.test_remote import mock_cumin


def test_mysql_remote_hosts_factory():
    """It should return an instance of MysqlRemoteHosts."""
    target = mysql.mysql_remote_hosts_factory({}, NodeSet('host[1-9]'), dry_run=False)
    assert isinstance(target, mysql.MysqlRemoteHosts)


class TestMysqlRemoteHosts:
    """Test class for the MysqlRemoteHosts class."""

    @mock.patch('spicerack.remote.transports', autospec=True)
    def setup_method(self, _, mocked_transports):
        """Setup the test environment."""
        # pylint: disable=attribute-defined-outside-init
        self.config = Config(get_fixture_path('remote', 'config.yaml'))
        self.mocked_transports = mocked_transports
        self.mysql_remote_hosts = mysql.MysqlRemoteHosts(self.config, NodeSet('host[1-9]'), dry_run=False)
        self.expected = [('host1', 'output1')]

    def test_execute(self):
        """Calling run_query() should run the given query in the target hosts."""
        mock_cumin(self.mocked_transports, 0)
        results = self.mysql_remote_hosts.run_query('query1')
        assert list(results) == self.expected


class TestMysql:
    """Mysql class tests."""

    def setup_method(self):
        """Initialize the test environment for Mysql."""
        # pylint: disable=attribute-defined-outside-init
        self.mocked_remote = mock.MagicMock(spec_set=Remote)
        self.mocked_remote.query.return_value = mock.MagicMock(spec_set=mysql.MysqlRemoteHosts)
        self.mysql = mysql.Mysql(self.mocked_remote, dry_run=False)

    @pytest.mark.parametrize('kwargs, query, match', (
        ({}, 'P{O:mariadb::core}', 'db10[01-99],db20[01-99]'),
        ({'datacenter': 'eqiad'}, 'P{O:mariadb::core} and A:eqiad', 'db10[01-99]'),
        ({'section': 's1'}, 'P{O:mariadb::core} and P{C:mariadb::heartbeat and R:Class%shard = "s1"}',
         'db10[01-10],db20[01-10]'),
        ({'replication_role': 'master'},
         'P{O:mariadb::core} and P{C:mariadb::config and R:Class%replication_role = "master"}',
         'db10[01-11],db20[01-11]'),
        ({'datacenter': 'eqiad', 'section': 's1'},
         'P{O:mariadb::core} and A:eqiad and P{C:mariadb::heartbeat and R:Class%shard = "s1"}', 'db10[01-10]'),
        ({'datacenter': 'eqiad', 'replication_role': 'master'},
         'P{O:mariadb::core} and A:eqiad and P{C:mariadb::config and R:Class%replication_role = "master"}',
         'db10[01-11]'),
        ({'section': 's1', 'replication_role': 'master'},
         ('P{O:mariadb::core} and P{C:mariadb::heartbeat and R:Class%shard = "s1"} and '
          'P{C:mariadb::config and R:Class%replication_role = "master"}'), 'db1001,db2001'),
        ({'datacenter': 'eqiad', 'section': 's1', 'replication_role': 'master'},
         ('P{O:mariadb::core} and A:eqiad and P{C:mariadb::heartbeat and R:Class%shard = "s1"} and '
          'P{C:mariadb::config and R:Class%replication_role = "master"}'), 'db1001'),
    ))
    def test_get_core_dbs_ok(self, kwargs, query, match):
        """It should return the right DBs based on the parameters."""
        self.mocked_remote.query.return_value.hosts = NodeSet(match)
        self.mysql.get_core_dbs(**kwargs)
        self.mocked_remote.query.assert_called_once_with(query, remote_hosts_factory=mysql.mysql_remote_hosts_factory)

    @pytest.mark.parametrize('kwargs', (
        {'datacenter': 'invalid'},
        {'section': 'invalid'},
        {'replication_role': 'invalid'},
    ))
    def test_get_core_dbs_fail(self, kwargs):
        """It should raise MysqlError if called with invalid parameters."""
        message = 'Got invalid {key}'.format(key=list(kwargs.keys())[0])
        with pytest.raises(mysql.MysqlError, match=message):
            self.mysql.get_core_dbs(**kwargs)

        assert not self.mocked_remote.query.called

    def test_get_core_dbs_fail_sanity_check(self):
        """It should raise MysqlError if matching an invalid number of hosts when looking for masters."""
        self.mocked_remote.query.return_value.hosts = NodeSet('db1001')
        with pytest.raises(mysql.MysqlError, match='Matched 1 masters, expected 11'):
            self.mysql.get_core_dbs(datacenter='eqiad', replication_role='master')

        assert self.mocked_remote.query.called

    @pytest.mark.parametrize('mode, value', (('readonly', '1'), ('readwrite', '0')))
    def test_set_core_masters_readonly(self, mode, value):
        """It should set the masters as read-only/read-write."""
        self.mocked_remote.query.return_value.hosts = NodeSet('db10[01-11]')
        getattr(self.mysql, 'set_core_masters_' + mode)('eqiad')
        argument = self.mocked_remote.query.return_value.run_query.call_args_list[0][0][0]
        assert 'SET GLOBAL read_only=' + value in argument

    @pytest.mark.parametrize('readonly, reply', ((True, '1'), (False, '0')))
    def test_verify_core_masters_readonly_ok(self, readonly, reply):
        """Should verify that the masters have the intended read-only value."""
        answer = mock.MagicMock()
        answer.message.return_value = reply.encode()
        self.mocked_remote.query.return_value.hosts = NodeSet('db10[01-11]')
        self.mocked_remote.query.return_value.run_query.return_value = [[NodeSet('db10[01-11]'), answer]]
        self.mysql.verify_core_masters_readonly('eqiad', readonly)
        assert 'SELECT @@global.read_only' in self.mocked_remote.query.return_value.run_query.call_args[0][0]

    def test_verify_core_masters_readonly_fail(self):
        """Should raise MysqlError if some masters do not have the intended read-only value."""
        answer = mock.MagicMock()
        answer.message.side_effect = [b'0', b'1']
        self.mocked_remote.query.return_value.hosts = NodeSet('db10[01-11]')
        self.mocked_remote.query.return_value.run_query.return_value = [
            [NodeSet('db1001'), answer], [NodeSet('db10[02-11]'), answer]]
        with pytest.raises(mysql.MysqlError, match='Verification failed that core DB masters'):
            self.mysql.verify_core_masters_readonly('eqiad', True)

    def test_ensure_core_masters_in_sync_ok(self):
        """Should ensure that all core masters are in sync with the master in the other DC."""
        answer = mock.MagicMock()
        answer.message.side_effect = [b'GTID_POSITION', b'0'] * 11
        self.mocked_remote.query.return_value.hosts = NodeSet('db1001')
        self.mocked_remote.query.return_value.run_query.return_value = [[NodeSet('db1001'), answer]]
        self.mysql.ensure_core_masters_in_sync('eqiad', 'codfw')

    def test_ensure_core_masters_in_sync_fail_gtid(self):
        """Should raise MysqlError if unable to get the GTID position from the current master."""
        self.mocked_remote.query.return_value.hosts = NodeSet('db1001')
        with pytest.raises(mysql.MysqlError, match='Unable to get GTID pos from master'):
            self.mysql.ensure_core_masters_in_sync('eqiad', 'codfw')

    def test_ensure_core_masters_in_sync_not_in_sync(self):
        """Should raise MysqlError if a master is not in sync with the one in the other DC."""
        answer = mock.MagicMock()
        answer.message.side_effect = [b'GTID_POSITION', b'1']
        self.mocked_remote.query.return_value.hosts = NodeSet('db1001')
        self.mocked_remote.query.return_value.run_query.return_value = [[NodeSet('db1001'), answer]]
        with pytest.raises(mysql.MysqlError, match='GTID not in sync after timeout for host'):
            self.mysql.ensure_core_masters_in_sync('eqiad', 'codfw')
