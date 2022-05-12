"""Interactive module tests."""
from datetime import datetime, timedelta
from unittest import mock

import pytest
from ClusterShell.MsgTree import MsgTreeElem
from cumin import Config, NodeSet
from cumin.transports import Target, clustershell

from spicerack import confctl, remote
from spicerack.tests import get_fixture_path


def mock_cumin(mocked_transports, retcode, retvals=None):
    """Given a mocked cumin.transports, add the necessary mocks for these tests and set the retcode."""
    if retvals is None:
        retvals = [[("host1", b"output1")]]

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
        config = get_fixture_path("remote", "config.yaml")
        self.hosts = NodeSet("host[1-9]")
        self.remote_hosts = remote.RemoteHostsAdapter(remote.RemoteHosts(config, self.hosts, dry_run=False))

    def test_str(self):
        """The str() of an instance should return the string representation of the target hosts."""
        assert str(self.remote_hosts) == str(self.hosts)

    def test_len(self):
        """The len() of an instance should return the number of target hosts."""
        assert len(self.remote_hosts) == len(self.hosts)


class TestLBRemoteCluster:
    """Test class for the LBRemoteCluster class."""

    def setup_method(self):
        """Setup the test environment."""
        # pylint: disable=attribute-defined-outside-init
        config = get_fixture_path("remote", "config.yaml")
        self.hosts = NodeSet("host[1-10]")
        # We want to mock out ConftoolEntity completely here. As far as we're concerned it's just an interface
        self.conftool = mock.MagicMock(spec=confctl.ConftoolEntity)
        self.remote_hosts = remote.RemoteHosts(config, self.hosts, dry_run=False)
        self.remote_hosts.run_async = mock.MagicMock()
        self.lbcluster = remote.LBRemoteCluster(config, self.remote_hosts, self.conftool)

    @pytest.mark.parametrize("size", [0, 10])
    def test_run_wrong_batch_size(self, size):
        """Test run fails with a bad batch size."""
        with pytest.raises(remote.RemoteError, match="Values for batch_size"):
            self.lbcluster.run("some command", batch_size=size)

    def test_run_no_depool(self):
        """Test a run with no service to depool."""
        self.lbcluster.run("some command", "some_other cmd")
        self.remote_hosts.run_async.assert_called_with(
            "some command",
            "some_other cmd",
            success_threshold=1.0,
            batch_size=1,
            batch_sleep=None,
            is_safe=False,
            print_output=True,
            print_progress_bars=True,
        )

    def test_run_no_depool_failures(self):
        """Test a run with no service to depool where we allow failures."""
        self.lbcluster.run("some command", "some_other cmd", max_failed_batches=1)
        self.remote_hosts.run_async.assert_called_with(
            "some command",
            "some_other cmd",
            success_threshold=0.9,
            batch_size=1,
            batch_sleep=None,
            is_safe=False,
            print_output=True,
            print_progress_bars=True,
        )

    @mock.patch("spicerack.remote.RemoteHosts.run_async")
    def test_run_depool(self, run_async):
        """Test a run with services to depool."""
        self.conftool.change_and_revert = mock.MagicMock()
        run_async.return_value = [(NodeSet("host1"), None), (NodeSet("host2"), None)]
        res = self.lbcluster.run(
            "test -d /tmp",
            svc_to_depool=["service1", "service2"],
            batch_size=5,
        )

        # Run has been sliced in two
        assert run_async.call_count == 2
        assert res == [
            (NodeSet("host1"), None),
            (NodeSet("host2"), None),
            (NodeSet("host1"), None),
            (NodeSet("host2"), None),
        ]
        # The depool is called on subsequent groups of servers.
        self.conftool.change_and_revert.assert_called_with(
            "pooled",
            "yes",
            "no",
            service="service1|service2",
            name="host6|host7|host8|host9|host10",
        )

    @mock.patch("spicerack.remote.RemoteHosts.run_async")
    def test_run_depool_failure(self, run_async):
        """Test a run with services to depool where a failure is caused."""
        # Case 1: run_async fails, no max_failed_batches
        run_async.side_effect = [
            [(NodeSet("host1"), None)],
            remote.RemoteExecutionError(message="foobar!", retcode=10),
            remote.RemoteExecutionError(message="barbaz!", retcode=10),
        ]
        with pytest.raises(remote.RemoteClusterExecutionError, match="1 hosts have failed execution") as err:
            self.lbcluster.run(
                "test -d /tmp",
                svc_to_depool=["service1", "service2"],
                batch_size=3,
            )
            assert len(err.results) == 1
            assert len(err.failures) == 1
        # This time, we bailed out after the first failure
        assert run_async.call_count == 2

        run_async.side_effect = [
            [(NodeSet("host1"), None)],
            remote.RemoteExecutionError(message="foobar!", retcode=10),
            remote.RemoteExecutionError(message="barbaz!", retcode=10),
        ]
        run_async.reset_mock()
        with pytest.raises(remote.RemoteClusterExecutionError, match="2 hosts have failed execution") as err:
            self.lbcluster.run(
                "test -d /tmp",
                svc_to_depool=["service1", "service2"],
                batch_size=3,
                max_failed_batches=1,
            )
            assert len(err.results) == 1
            assert len(err.failures) == 2
        # All batches have been run, as we could tolerate one error
        assert run_async.call_count == 3

    @mock.patch("spicerack.remote.RemoteHosts.run_async")
    def test_run_depool_no_sleep(self, _):
        """Test a run with services to depool where a failure is caused."""
        with mock.patch("time.sleep") as ts:
            self.lbcluster.run(
                "test -d /tmp",
                svc_to_depool=["service1", "service2"],
                batch_size=3,
            )
            assert ts.call_count == 0

    @mock.patch("spicerack.remote.RemoteHosts.run_async")
    def test_run_depool_sleep(self, _):
        """Test a run where we have a batch sleep."""
        with mock.patch("time.sleep") as ts:
            self.lbcluster.run(
                "test -d /tmp",
                svc_to_depool=["service1", "service2"],
                batch_sleep=3,
                batch_size=3,
            )
            assert ts.call_count == 4

    def test_reload_services(self):
        """Test a service reload."""
        self.lbcluster.run = mock.MagicMock(return_value="foobar")
        assert self.lbcluster.reload_services(["svc"], ["lbl1", "lbl2"]) == "foobar"
        self.lbcluster.run.assert_called_with(
            'systemctl reload "svc"',
            svc_to_depool=["lbl1", "lbl2"],
            batch_size=1,
            batch_sleep=None,
            is_safe=False,
            print_output=True,
            print_progress_bars=True,
        )

    def test_restart_services(self):
        """Test a service restart."""
        self.lbcluster.run = mock.MagicMock(return_value="foobar")
        assert self.lbcluster.restart_services(["svc1", "svc2"], ["lbl1", "lbl2"]) == "foobar"
        self.lbcluster.run.assert_called_with(
            'systemctl restart "svc1"',
            'systemctl restart "svc2"',
            svc_to_depool=["lbl1", "lbl2"],
            batch_size=1,
            batch_sleep=None,
            is_safe=False,
            print_output=True,
            print_progress_bars=True,
        )


class TestRemote:
    """Test class for the Remote class."""

    def setup_method(self):
        """Setup the test environment."""
        # pylint: disable=attribute-defined-outside-init
        config = get_fixture_path("remote", "config.yaml")
        self.remote = remote.Remote(config)

    def test_query_ok(self):
        """Calling query() should return the matching hosts."""
        query = "host[1-9]"
        remote_hosts = self.remote.query(query)

        assert isinstance(remote_hosts, remote.RemoteHosts)
        assert remote_hosts.hosts == NodeSet(query)
        assert str(remote_hosts) == "host[1-9]"
        assert len(remote_hosts) == 9

    def test_query_accepts_sudo(self):
        """Calling query() should return the matching hosts even if using sudo."""
        query = "host[1-9]"
        remote_hosts = self.remote.query(query, use_sudo=True)

        assert isinstance(remote_hosts, remote.RemoteHosts)
        assert remote_hosts.hosts == NodeSet(query)
        assert str(remote_hosts) == "host[1-9]"
        assert len(remote_hosts) == 9
        assert remote_hosts._use_sudo  # pylint: disable=protected-access

    def test_query_invalid(self):
        """Calling query() with an invalid query should raise RemoteError."""
        with pytest.raises(remote.RemoteError, match="Failed to execute Cumin query"):
            self.remote.query("or invalid")

    def test_query_confctl_ok(self):
        """Succesful query_confctl() should return the correct lbremotehosts instance."""
        conftool = mock.MagicMock(spec=confctl.ConftoolEntity)
        host1 = mock.MagicMock()
        host1.name = "host1"
        host2 = mock.MagicMock()
        host2.name = "host2"
        conftool.get.return_value = [host1, host2]
        lbcluster = self.remote.query_confctl(conftool, dc="a", sometag="someval")
        conftool.get.assert_called_with(dc="a", sometag="someval")
        assert str(lbcluster) == "host[1-2]"
        assert isinstance(lbcluster, remote.LBRemoteCluster)

    def test_query_confctl_error(self):
        """Failing query_confctl() raises a RemoteError."""
        conftool = mock.MagicMock(spec=confctl.ConftoolEntity)
        conftool.get.side_effect = confctl.ConfctlError("test test!")
        with pytest.raises(remote.RemoteError, match="Failed to execute the conftool query"):
            self.remote.query_confctl(conftool, dc="a", sometag="someval")


class TestRemoteHosts:
    """Test class for the RemoteHosts class."""

    @mock.patch("spicerack.remote.transports", autospec=True)
    def setup_method(self, _, mocked_transports):
        """Setup the test environment."""
        # pylint: disable=attribute-defined-outside-init
        self.config = Config(get_fixture_path("remote", "config.yaml"))
        self.mocked_transports = mocked_transports
        self.hosts = NodeSet("host[1-9]")
        self.remote_hosts = remote.RemoteHosts(self.config, self.hosts, dry_run=False)
        self.remote_hosts_dry_run = remote.RemoteHosts(self.config, self.hosts)
        self.expected = [(NodeSet("host1"), "output1")]

    def test_init_no_hosts(self):
        """Should raise RemoteError if initialized without hosts."""
        with pytest.raises(remote.RemoteError, match="No hosts provided"):
            remote.RemoteHosts(self.config, NodeSet(), dry_run=False)

    @pytest.mark.parametrize("func_name", ("run_sync", "run_async"))
    def test_execute(self, func_name):
        """Calling execute() should run the given commands in the target hosts."""
        mock_cumin(self.mocked_transports, 0)
        results = getattr(self.remote_hosts, func_name)("command1")
        assert [(host, msg.message().decode()) for host, msg in results] == self.expected

    @pytest.mark.parametrize("func_name", ("run_sync", "run_async"))
    def test_execute_fail(self, func_name):
        """Calling execute() should raise RemoteError if the Cumin execution fails."""
        mock_cumin(self.mocked_transports, 11)
        with pytest.raises(
            remote.RemoteExecutionError,
            match=r"Cumin execution failed \(exit_code=11\)",
        ) as exc_info:
            getattr(self.remote_hosts, func_name)("command1")

        assert exc_info.value.retcode == 11
        self.mocked_transports.clustershell.ClusterShellWorker.execute.assert_called_once_with()

    @pytest.mark.parametrize("func_name", ("run_sync", "run_async"))
    def test_execute_dry_run_safe(self, func_name):
        """Calling execute() in dry_run mode should run the given commands if marked safe."""
        mock_cumin(self.mocked_transports, 11)  # Simulate a failure
        # In DRY-RUN when is_safe=True all executions are considered successful.
        results = getattr(self.remote_hosts_dry_run, func_name)("command1", is_safe=True)
        assert [(host, msg.message().decode()) for host, msg in results] == self.expected

    @pytest.mark.parametrize("func_name", ("run_sync", "run_async"))
    def test_execute_dry_run_unsafe(self, func_name):
        """Calling execute() in dry_run mode should not run the given commands, considered unsafe by default."""
        results = getattr(self.remote_hosts_dry_run, func_name)("command1")
        assert list(results) == []  # pylint: disable=use-implicit-booleaness-not-comparison

    @pytest.mark.parametrize("func_name", ("run_sync", "run_async"))
    def test_execute_batch_size(self, func_name):
        """Calling execute() with batch_size should parse it to detect percentage or absolute value."""
        mock_cumin(self.mocked_transports, 0)
        getattr(self.remote_hosts, func_name)("command1", batch_size=2)
        # TODO: remove this test once the logic has been moved to Cumin itself

    @mock.patch("spicerack.remote.transports.Target")
    def test_reboot_single(self, mocked_target):
        """It should call the reboot script on the target host with default batch size and no sleep."""
        hosts = NodeSet("host1")
        remote_hosts = remote.RemoteHosts(self.config, hosts, dry_run=False)
        mock_cumin(self.mocked_transports, 0)
        remote_hosts.reboot()
        self.mocked_transports.clustershell.ClusterShellWorker.execute.assert_called_once_with()
        mocked_target.assert_has_calls([mock.call(hosts, batch_size_ratio=None, batch_sleep=None, batch_size=1)])

    @mock.patch("spicerack.remote.transports.Target")
    def test_reboot_many(self, mocked_target):
        """It should call the reboot script on the target hosts with the given batch size and sleep."""
        mock_cumin(self.mocked_transports, 0)
        self.remote_hosts.reboot(batch_size=2, batch_sleep=30.0)
        self.mocked_transports.clustershell.ClusterShellWorker.execute.assert_called_once_with()
        mocked_target.assert_has_calls([mock.call(self.hosts, batch_size_ratio=None, batch_sleep=30.0, batch_size=2)])

    @mock.patch("spicerack.remote.RemoteHosts.uptime")
    def test_wait_reboot_since_ok(self, mocked_uptime):
        """It should return immediately if the host has already a small enough uptime."""
        since = datetime.utcnow() - timedelta(minutes=5)
        mocked_uptime.return_value = [(self.hosts, 30.0)]
        self.remote_hosts.wait_reboot_since(since)
        mocked_uptime.assert_called_once_with(print_progress_bars=True)

    @pytest.mark.parametrize(
        "side_effect",
        (
            remote.RemoteExecutionError(message="unable to connect", retcode=1),
            remote.RemoteError("Unable to extract data"),
        ),
    )
    @mock.patch("wmflib.decorators.time.sleep", return_value=None)
    @mock.patch("spicerack.remote.RemoteHosts.uptime")
    def test_wait_reboot_since_uptime_fails(self, mocked_uptime, mocked_sleep, side_effect):
        """It should raise RemoteCheckError if unable to check the uptime on any host."""
        since = datetime.utcnow()
        mocked_uptime.side_effect = side_effect
        with pytest.raises(
            remote.RemoteCheckError,
            match=r"Unable to get uptime for host\[1-9\]",
        ):
            self.remote_hosts.wait_reboot_since(since)

        # wait_reboot_since() sets tries to 240 and dry_run is False.
        assert mocked_uptime.call_count == 240
        assert mocked_sleep.called

    @mock.patch("wmflib.decorators.time.sleep", return_value=None)
    @mock.patch("spicerack.remote.RemoteHosts.uptime")
    def test_wait_reboot_since_uptime_too_big(self, mocked_uptime, mocked_sleep):
        """It should raise RemoteCheckError if any host doesn't have a small-enough uptime."""
        since = datetime.utcnow()
        mocked_uptime.return_value = [(NodeSet("host[1-9]"), 30.0)]
        with pytest.raises(
            remote.RemoteCheckError,
            match=r"Uptime for host\[1-9\] higher than threshold",
        ):
            self.remote_hosts.wait_reboot_since(since)

        mocked_uptime.assert_called_with(print_progress_bars=True)
        assert mocked_sleep.called

    def test_uptime_ok(self):
        """It should gather the current uptime from the target hosts."""
        nodes_a = "host1"
        nodes_b = "host[2-9]"
        mock_cumin(
            self.mocked_transports,
            0,
            retvals=[[(nodes_a, b"1514768400"), (nodes_b, b"1514768401")]],
        )
        uptimes = self.remote_hosts.uptime()
        assert sorted(uptimes) == sorted([(NodeSet(nodes_a), 1514768400.0), (NodeSet(nodes_b), 1514768401.0)])

    def test_uptime_invalid(self):
        """It should raise RemoteError if unable to parse the output as uptime."""
        mock_cumin(self.mocked_transports, 0, retvals=[[("host1", b"invalid")]])
        with pytest.raises(remote.RemoteError, match="Unable to extract data with <lambda> for host1"):
            self.remote_hosts.uptime()

    def test_results_to_list_callback(self):
        """It should return the output string coverted by the callback."""
        results = (item for item in [(self.hosts, MsgTreeElem(b"test", parent=MsgTreeElem()))])

        extracted = remote.RemoteHosts.results_to_list(results, callback=lambda x: x.upper())
        assert sorted(extracted) == sorted([(self.hosts, "TEST")])

    def test_results_to_list_no_callback(self):
        """It should return the output string without any conversion."""
        results = (item for item in [(self.hosts, MsgTreeElem(b"test", parent=MsgTreeElem()))])
        extracted = remote.RemoteHosts.results_to_list(results)
        assert sorted(extracted) == sorted([(self.hosts, "test")])

    def test_results_to_list_callback_raise(self):
        """It should raise RemoteError if the callback call raises any exception."""
        results = (item for item in [(self.hosts, MsgTreeElem(b"test", parent=MsgTreeElem()))])
        with pytest.raises(
            remote.RemoteError,
            match=r"Unable to extract data with <lambda> for host\[1-9\] from: test",
        ):
            remote.RemoteHosts.results_to_list(results, callback=lambda x: 1 / 0)

    def test_split_simple(self):
        """It should correctly split a simple remote."""
        results = list(self.remote_hosts.split(2))
        assert len(results) == 2
        assert len(results[0]) == 5
        assert len(results[1]) == 4

    def test_split_too_high(self):
        """It should correctly split the remote even if the slices are too many."""
        results = list(self.remote_hosts.split(15))
        assert len(results) == 9
        for result in results:
            assert len(result) == 1
            assert result._dry_run is False  # pylint: disable=protected-access

    @mock.patch("spicerack.remote.transport.Transport.new")
    def test_using_sudo_prepends_when_command_is_string(self, mocked_transport_new):
        """Test that using sudo prepends when command is string."""
        nodes_a = "host1"
        mock_cumin(self.mocked_transports, 0, retvals=[[(nodes_a, b"")]])
        mocked_worker = mock.MagicMock()
        mocked_worker.execute.return_value = 0
        mocked_transport_new.return_value = mocked_worker

        remote.RemoteHosts(self.config, NodeSet(nodes_a), dry_run=False, use_sudo=True).run_sync("command")

        assert mocked_worker.commands == ["sudo -i command"]

    @mock.patch("spicerack.remote.transport.Transport.new")
    def test_using_sudo_prepends_when_command_is_commands(self, mocked_transport_new):
        """Test that using sudo prepends when command is commands."""
        expected_command = remote.Command("sudo -i command", ok_codes=[0])
        nodes_a = "host1"
        mock_cumin(self.mocked_transports, 0, retvals=[[(nodes_a, b"")]])
        mocked_worker = mock.MagicMock()
        mocked_worker.execute.return_value = 0
        mocked_transport_new.return_value = mocked_worker

        remote.RemoteHosts(self.config, NodeSet(nodes_a), dry_run=False, use_sudo=True).run_sync(
            remote.Command("command")
        )

        assert mocked_worker.commands == [expected_command]

    @mock.patch("spicerack.remote.transport.Transport.new")
    def test_using_sudo_prepends_when_command_is_commands_and_str(self, mocked_transport_new):
        """Test that using sudo prepends when command is commands and str."""
        expected_command = remote.Command("sudo -i command", ok_codes=[0])
        nodes_a = "host1"
        mock_cumin(self.mocked_transports, 0, retvals=[[(nodes_a, b"")]])
        mocked_worker = mock.MagicMock()
        mocked_worker.execute.return_value = 0
        mocked_transport_new.return_value = mocked_worker

        remote.RemoteHosts(self.config, NodeSet(nodes_a), dry_run=False, use_sudo=True).run_sync(
            remote.Command("command"), "command"
        )

        assert mocked_worker.commands == [expected_command, "sudo -i command"]
