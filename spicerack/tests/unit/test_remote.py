"""Interactive module tests."""
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
        self.remote_hosts = remote.RemoteHosts(self.config, NodeSet('host[1-9]'), dry_run=False)
        self.remote_hosts_dry_run = remote.RemoteHosts(self.config, NodeSet('host[1-9]'))
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
        assert self.mocked_transports.clustershell.ClusterShellWorker.execute.called_once_with()

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
