"""Interactive module tests."""
from datetime import datetime, timedelta
from unittest import mock

import pytest

from ClusterShell.MsgTree import MsgTreeElem
from cumin import Config, NodeSet
from cumin.transports import clustershell, Target

from spicerack import remote

from spicerack.tests import get_fixture_path


def mock_cumin(mocked_transports, retcode, retvals=None):
    """Given a mocked cumin.transports, add the necessary mocks for these tests and set the retcode."""
    if retvals is None:
        retvals = [[('host1', b'output1')]]

    results = []
    for retval in retvals:
        result = []
        for host, message in retval:
            result.append((NodeSet(host), MsgTreeElem(message, parent=MsgTreeElem())))

        results.append(result)

    mocked_transports.clustershell = clustershell
    mocked_execute = mock.Mock()
    mocked_execute.return_value = retcode
    mocked_get_results = mock.Mock()
    if results:
        mocked_get_results.side_effect = results
    else:
        mocked_get_results.return_value = iter(())

    mocked_transports.clustershell.ClusterShellWorker.execute = mocked_execute
    mocked_transports.clustershell.ClusterShellWorker.get_results = mocked_get_results
    mocked_transports.Target = Target


class TestRemoteHostsAdapter:
    """Test class for the RemoteHostsAdapter class."""

    def setup_method(self):
        """Setup the test environment."""
        # pylint: disable=attribute-defined-outside-init
        config = get_fixture_path('remote', 'config.yaml')
        self.hosts = NodeSet('host[1-9]')
        self.remote_hosts = remote.RemoteHostsAdapter(remote.RemoteHosts(config, self.hosts, dry_run=False))

    def test_str(self):
        """The str() of an instance should return the string representation of the target hosts."""
        assert str(self.remote_hosts) == str(self.hosts)

    def test_len(self):
        """The len() of an instance should return the number of target hosts."""
        assert len(self.remote_hosts) == len(self.hosts)


class TestRemote:
    """Test class for the Remote class."""

    def setup_method(self):
        """Setup the test environment."""
        # pylint: disable=attribute-defined-outside-init
        config = get_fixture_path('remote', 'config.yaml')
        self.remote = remote.Remote(config)

    def test_query_ok(self):
        """Calling query() should return the matching hosts."""
        query = 'host[1-9]'
        remote_hosts = self.remote.query(query)

        assert isinstance(remote_hosts, remote.RemoteHosts)
        assert remote_hosts.hosts == NodeSet(query)
        assert str(remote_hosts) == 'host[1-9]'
        assert len(remote_hosts) == 9

    def test_query_invalid(self):
        """Calling query() with an invalid query should raise RemoteError."""
        with pytest.raises(remote.RemoteError, match='Failed to execute Cumin query'):
            self.remote.query('or invalid')


class TestRemoteHosts:
    """Test class for the RemoteHosts class."""

    @mock.patch('spicerack.remote.transports', autospec=True)
    def setup_method(self, _, mocked_transports):
        """Setup the test environment."""
        # pylint: disable=attribute-defined-outside-init
        self.config = Config(get_fixture_path('remote', 'config.yaml'))
        self.mocked_transports = mocked_transports
        self.hosts = NodeSet('host[1-9]')
        self.remote_hosts = remote.RemoteHosts(self.config, self.hosts, dry_run=False)
        self.remote_hosts_dry_run = remote.RemoteHosts(self.config, self.hosts)
        self.expected = [(NodeSet('host1'), 'output1')]

    def test_init_no_hosts(self):
        """Should raise RemoteError if initialized without hosts."""
        with pytest.raises(remote.RemoteError, match='No hosts provided'):
            remote.RemoteHosts(self.config, NodeSet(), dry_run=False)

    @pytest.mark.parametrize('func_name', ('run_sync', 'run_async'))
    def test_execute(self, func_name):
        """Calling execute() should run the given commands in the target hosts."""
        mock_cumin(self.mocked_transports, 0)
        results = getattr(self.remote_hosts, func_name)('command1')
        assert [(host, msg.message().decode()) for host, msg in results] == self.expected

    @pytest.mark.parametrize('func_name', ('run_sync', 'run_async'))
    def test_execute_fail(self, func_name):
        """Calling execute() should raise RemoteError if the Cumin execution fails."""
        mock_cumin(self.mocked_transports, 11)
        with pytest.raises(remote.RemoteExecutionError, match=r'Cumin execution failed \(exit_code=11\)') as exc_info:
            getattr(self.remote_hosts, func_name)('command1')

        assert exc_info.value.retcode == 11
        self.mocked_transports.clustershell.ClusterShellWorker.execute.assert_called_once_with()

    @pytest.mark.parametrize('func_name', ('run_sync', 'run_async'))
    def test_execute_dry_run_safe(self, func_name):
        """Calling execute() in dry_run mode should run the given commands if marked safe."""
        mock_cumin(self.mocked_transports, 11)  # Simulate a failure
        # In DRY-RUN when is_safe=True all executions are considered successful.
        results = getattr(self.remote_hosts_dry_run, func_name)('command1', is_safe=True)
        assert [(host, msg.message().decode()) for host, msg in results] == self.expected

    @pytest.mark.parametrize('func_name', ('run_sync', 'run_async'))
    def test_execute_dry_run_unsafe(self, func_name):
        """Calling execute() in dry_run mode should not run the given commands, considered unsafe by default."""
        results = getattr(self.remote_hosts_dry_run, func_name)('command1')
        assert list(results) == []

    @pytest.mark.parametrize('func_name', ('run_sync', 'run_async'))
    def test_execute_batch_size(self, func_name):
        """Calling execute() with batch_size should parse it to detect percentage or absolute value."""
        mock_cumin(self.mocked_transports, 0)
        getattr(self.remote_hosts, func_name)('command1', batch_size=2)
        # TODO: remove this test once the logic has been moved to Cumin itself

    @mock.patch('spicerack.remote.transports.Target')
    def test_reboot_single(self, mocked_target):
        """It should call the reboot script on the target host with default batch size and no sleep."""
        hosts = NodeSet('host1')
        remote_hosts = remote.RemoteHosts(self.config, hosts, dry_run=False)
        mock_cumin(self.mocked_transports, 0)
        remote_hosts.reboot()
        self.mocked_transports.clustershell.ClusterShellWorker.execute.assert_called_once_with()
        mocked_target.assert_has_calls([
            mock.call(hosts, batch_size_ratio=None, batch_sleep=None, batch_size=1)])

    @mock.patch('spicerack.remote.transports.Target')
    def test_reboot_many(self, mocked_target):
        """It should call the reboot script on the target hosts with the given batch size and sleep."""
        mock_cumin(self.mocked_transports, 0)
        self.remote_hosts.reboot(batch_size=2, batch_sleep=30.0)
        self.mocked_transports.clustershell.ClusterShellWorker.execute.assert_called_once_with()
        mocked_target.assert_has_calls([
            mock.call(self.hosts, batch_size_ratio=None, batch_sleep=30.0, batch_size=2)])

    @mock.patch('spicerack.remote.RemoteHosts.uptime')
    def test_wait_reboot_since_ok(self, mocked_uptime):
        """It should return immediately if the host has already a small enough uptime."""
        since = datetime.utcnow() - timedelta(minutes=5)
        mocked_uptime.return_value = [(self.hosts, 30.0)]
        self.remote_hosts.wait_reboot_since(since)
        mocked_uptime.assert_called_once_with()

    @mock.patch('spicerack.decorators.time.sleep', return_value=None)
    @mock.patch('spicerack.remote.RemoteHosts.uptime')
    def test_wait_reboot_since_remaining_hosts(self, mocked_uptime, mocked_sleep):
        """It should raise RemoteCheckError if unable to get the uptime from all hosts."""
        since = datetime.utcnow() - timedelta(minutes=5)
        mocked_uptime.return_value = [(NodeSet('host1'), 30.0)]
        with pytest.raises(remote.RemoteCheckError, match=r'Unable to check uptime from 8 hosts: host\[2-9\]'):
            self.remote_hosts.wait_reboot_since(since)

        mocked_uptime.assert_called_with()
        assert mocked_sleep.called

    @mock.patch('spicerack.decorators.time.sleep', return_value=None)
    @mock.patch('spicerack.remote.RemoteHosts.uptime')
    def test_wait_reboot_since_uptime_too_big(self, mocked_uptime, mocked_sleep):
        """It should raise RemoteCheckError if any host doesn't have a small-enough uptime."""
        since = datetime.utcnow()
        mocked_uptime.return_value = [(NodeSet('host[1-9]'), 30.0)]
        with pytest.raises(remote.RemoteCheckError, match=r'Uptime for host\[1-9\] higher than threshold'):
            self.remote_hosts.wait_reboot_since(since)

        mocked_uptime.assert_called_with()
        assert mocked_sleep.called

    def test_uptime(self):
        """It should gather the current uptime from the target hosts."""
        nodes_a = 'host1'
        nodes_b = 'host[2-9]'
        mock_cumin(self.mocked_transports, 0, retvals=[[(nodes_a, b'1514768400'), (nodes_b, b'1514768401')]])
        uptimes = self.remote_hosts.uptime()
        assert sorted(uptimes) == sorted([(NodeSet(nodes_a), 1514768400.0), (NodeSet(nodes_b), 1514768401.0)])

    def test_init_system(self):
        """It should gather the current init system from the target hosts."""
        nodes_a = 'host1'
        nodes_b = 'host[2-9]'
        mock_cumin(self.mocked_transports, 0, retvals=[[(nodes_a, b'init'), (nodes_b, b'systemd')]])
        uptimes = self.remote_hosts.init_system()
        assert sorted(uptimes) == sorted([(NodeSet(nodes_a), 'init'), (NodeSet(nodes_b), 'systemd')])

    def test_results_to_list_callback(self):
        """It should return the output string coverted by the callback."""
        results = (item for item in [(self.hosts, MsgTreeElem(b'test', parent=MsgTreeElem()))])

        extracted = remote.RemoteHosts.results_to_list(results, callback=lambda x: x.upper())
        assert sorted(extracted) == sorted([(self.hosts, 'TEST')])

    def test_results_to_list_no_callback(self):
        """It should return the output string without any conversion."""
        results = (item for item in [(self.hosts, MsgTreeElem(b'test', parent=MsgTreeElem()))])
        extracted = remote.RemoteHosts.results_to_list(results)
        assert sorted(extracted) == sorted([(self.hosts, 'test')])

    def test_results_to_list_callback_raise(self):
        """It should raise RemoteError if the callback call raises any exception."""
        results = (item for item in [(self.hosts, MsgTreeElem(b'test', parent=MsgTreeElem()))])
        with pytest.raises(remote.RemoteError,
                           match=r'Unable to extract data with <lambda> for host\[1-9\] from: test'):
            remote.RemoteHosts.results_to_list(results, callback=lambda x: 1 / 0)
