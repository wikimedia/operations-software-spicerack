"""Icinga module tests."""
from datetime import timedelta
from unittest import mock

import pytest
from ClusterShell.MsgTree import MsgTreeElem
from cumin import NodeSet

from spicerack import icinga
from spicerack.administrative import Reason
from spicerack.remote import RemoteHosts
from spicerack.tests import get_fixture_path


def set_mocked_icinga_host_output(mocked_icinga_host, output, n_hosts=1):
    """Setup the mocked icinga_host return value with the given output."""
    out = MsgTreeElem(output.encode(), parent=MsgTreeElem())
    mocked_icinga_host.run_sync.return_value = iter(n_hosts * [(NodeSet("icinga-host"), out)])


class TestCommandFile:
    """Test class for the CommandFile class."""

    def setup_method(self):
        """Setup the test environment."""
        # pylint: disable=attribute-defined-outside-init
        self.mocked_icinga_host = mock.MagicMock(spec_set=RemoteHosts)
        self.mocked_icinga_host.__len__.return_value = 1
        set_mocked_icinga_host_output(self.mocked_icinga_host, "/var/lib/icinga/rw/icinga.cmd")

    @pytest.mark.parametrize("num_hosts", (0, 2))
    def test_wrong_hosts(self, num_hosts):
        """It should raise IcingaError if no or too many hosts match the RemoteHosts instance."""
        self.mocked_icinga_host.__len__.return_value = num_hosts
        with pytest.raises(icinga.IcingaError, match="Icinga host must match a single host"):
            icinga.CommandFile(self.mocked_icinga_host)

        self.mocked_icinga_host.run_sync.assert_not_called()

    def test_uncached(self):
        """It should return the command_file setting from the Icinga configuration on the Icinga host."""
        assert icinga.CommandFile(self.mocked_icinga_host) == "/var/lib/icinga/rw/icinga.cmd"
        self.mocked_icinga_host.run_sync.assert_called_once()

    @pytest.mark.parametrize(
        "output",
        (
            "",
            " ",
        ),
    )
    def test_no_config(self, output):
        """It should raise IcingaError if failing to get the configuration value."""
        set_mocked_icinga_host_output(self.mocked_icinga_host, output)
        with pytest.raises(icinga.IcingaError, match="Unable to read command_file configuration"):
            icinga.CommandFile(self.mocked_icinga_host)  # pylint: disable=pointless-statement

    def test_cached(self):
        """It should return the already cached value of the command_file if accessed again."""
        command_file = icinga.CommandFile(self.mocked_icinga_host)
        self.mocked_icinga_host.reset_mock()
        assert icinga.CommandFile(self.mocked_icinga_host) == command_file
        self.mocked_icinga_host.assert_not_called()

    def test_uncached_with_other_cached(self):
        """It should get the new command file if the host changes even if has another value already cached."""
        mocked_other_icinga_host = mock.MagicMock(spec_set=RemoteHosts)
        mocked_other_icinga_host.__len__.return_value = 1
        set_mocked_icinga_host_output(mocked_other_icinga_host, "/var/lib/icinga/rw/icinga_other.cmd")

        icinga.CommandFile(self.mocked_icinga_host)
        self.mocked_icinga_host.reset_mock()

        assert icinga.CommandFile(mocked_other_icinga_host) == "/var/lib/icinga/rw/icinga_other.cmd"
        self.mocked_icinga_host.run_sync.assert_not_called()
        mocked_other_icinga_host.run_sync.assert_called_once()


class TestIcinga:
    """Test class for the Icinga class."""

    def setup_method(self):
        """Setup the test environment."""
        # pylint: disable=attribute-defined-outside-init
        self.reason = Reason("Downtime reason", "user1", "orchestration-host", task_id="T12345")
        self.mocked_icinga_host = mock.MagicMock(spec_set=RemoteHosts)
        self.mocked_icinga_host.__len__.return_value = 1
        set_mocked_icinga_host_output(self.mocked_icinga_host, "/var/lib/icinga/rw/icinga.cmd")
        self.icinga = icinga.Icinga(self.mocked_icinga_host)

    def test_command_file_ok(self):
        """It should return the command_file setting from the Icinga configuration."""
        assert self.icinga.command_file == "/var/lib/icinga/rw/icinga.cmd"

    @mock.patch("spicerack.icinga.time.time", return_value=1514764800)
    def test_hosts_downtimed(self, mocked_time):
        """It should downtime the hosts on Icinga, yield and delete the downtime once done."""
        hosts = ["host1"]
        call = 'icinga-downtime -h "host1" -d 14400 -r {reason}'.format(reason=self.reason.quoted())

        with self.icinga.hosts_downtimed(hosts, self.reason):
            self.mocked_icinga_host.run_sync.assert_called_once_with(call)
            self.mocked_icinga_host.run_sync.reset_mock()

        self.mocked_icinga_host.run_sync.assert_has_calls(
            [
                mock.call(
                    'bash -c \'echo -n "[1514764800] DEL_DOWNTIME_BY_HOST_NAME;host1" > '
                    "/var/lib/icinga/rw/icinga.cmd '"
                )
            ]
        )
        assert mocked_time.called

    def test_downtime_is_kept_when_exception_is_raised(self):
        """Downtime should not be removed if an exception is raised."""
        hosts = ["host1"]
        call = 'icinga-downtime -h "host1" -d 14400 -r {reason}'.format(reason=self.reason.quoted())

        with pytest.raises(ValueError):
            with self.icinga.hosts_downtimed(hosts, self.reason):
                self.mocked_icinga_host.run_sync.assert_called_once_with(call)
                self.mocked_icinga_host.run_sync.reset_mock()
                raise ValueError()
        assert not self.mocked_icinga_host.run_sync.called

    def test_downtime_is_removed_when_exception_is_raised(self):
        """Downtime should not be removed if an exception is raised."""
        hosts = ["host1"]
        call = 'icinga-downtime -h "host1" -d 14400 -r {reason}'.format(reason=self.reason.quoted())

        with pytest.raises(ValueError):
            with self.icinga.hosts_downtimed(hosts, self.reason, remove_on_error=True):
                self.mocked_icinga_host.run_sync.assert_called_once_with(call)
                self.mocked_icinga_host.run_sync.reset_mock()
                raise ValueError()
        assert self.mocked_icinga_host.run_sync.called

    @pytest.mark.parametrize(
        "hosts",
        (
            ["host1"],
            ["host1", "host2"],
            NodeSet("host1"),
            NodeSet("host[1-9]"),
        ),
    )
    def test_downtime_hosts_default_params(self, hosts):
        """It should downtime the hosts on the Icinga server with the default params."""
        self.icinga.downtime_hosts(hosts, self.reason)
        calls = [
            ('icinga-downtime -h "{host}" -d 14400 -r {reason}').format(host=host, reason=self.reason.quoted())
            for host in hosts
        ]
        self.mocked_icinga_host.run_sync.assert_called_once_with(*calls)

    def test_downtime_hosts_custom_duration(self):
        """It should downtime the hosts for the given duration on the Icinga server."""
        self.icinga.downtime_hosts(["host1"], self.reason, duration=timedelta(minutes=30))
        self.mocked_icinga_host.run_sync.assert_called_once_with(
            ('icinga-downtime -h "host1" -d 1800 -r {reason}'.format(reason=self.reason.quoted()))
        )

    def test_downtime_hosts_invalid_duration(self):
        """It should raise IcingaError if the duration is too short."""
        with pytest.raises(icinga.IcingaError, match="Downtime duration must be at least 1 minute"):
            self.icinga.downtime_hosts(["host1"], self.reason, duration=timedelta(seconds=59))

    def test_downtime_hosts_no_hosts(self):
        """It should raise IcingaError if there are no hosts to downtime."""
        with pytest.raises(icinga.IcingaError, match="Got empty hosts list to downtime"):
            self.icinga.downtime_hosts([], self.reason)

    @pytest.mark.parametrize(
        "hosts",
        (
            ["host1"],
            ["host1", "host2"],
            NodeSet("host1"),
            NodeSet("host[1-9]"),
        ),
    )
    @mock.patch("spicerack.icinga.time.time", return_value=1514764800)
    def test_host_command(self, mocked_time, hosts):
        """It should run the specified command for all the hosts on the Icinga server."""
        self.icinga.host_command("TEST_COMMAND", hosts, "arg1", "arg2")
        calls = [
            "bash -c 'echo -n \"[1514764800] TEST_COMMAND;{host};arg1;arg2\" > /var/lib/icinga/rw/icinga.cmd '".format(
                host=host
            )
            for host in hosts
        ]

        self.mocked_icinga_host.run_sync.assert_called_with(*calls)
        assert mocked_time.called

    @mock.patch("spicerack.icinga.time.time", return_value=1514764800)
    def test_recheck_all_services(self, mocked_time):
        """It should force a recheck of all services for the hosts on the Icinga server."""
        self.icinga.recheck_all_services(NodeSet("host1"))
        self.mocked_icinga_host.run_sync.assert_called_with(
            'bash -c \'echo -n "[1514764800] SCHEDULE_FORCED_HOST_SVC_CHECKS;host1;1514764800" > '
            "/var/lib/icinga/rw/icinga.cmd '"
        )
        assert mocked_time.called

    @mock.patch("spicerack.icinga.time.time", return_value=1514764800)
    def test_remove_downtime(self, mocked_time):
        """It should remove the downtime for the hosts on the Icinga server."""
        self.icinga.remove_downtime(NodeSet("host1"))
        self.mocked_icinga_host.run_sync.assert_called_with(
            "bash -c 'echo -n \"[1514764800] DEL_DOWNTIME_BY_HOST_NAME;host1\" > /var/lib/icinga/rw/icinga.cmd '"
        )
        assert mocked_time.called

    def test_get_status_ok(self):
        """It should parse the JSON payload and return an instance of HostsStatus."""
        with open(get_fixture_path("icinga", "status_with_failed_services.json")) as f:
            set_mocked_icinga_host_output(self.mocked_icinga_host, f.read())

        status = self.icinga.get_status("host[1-2]")

        assert not status.optimal
        assert status.non_optimal_hosts == ["host2"]
        assert status.failed_services == {"host2": ["check_name1", "check_name2"]}
        assert status.failed_hosts == []

    def test_get_status_parse_fail(self):
        """It should raise IcingaStatusParseError if unable to parse the JSON payload."""
        with open(get_fixture_path("icinga", "status_invalid.json")) as f:
            set_mocked_icinga_host_output(self.mocked_icinga_host, f.read())

        with pytest.raises(icinga.IcingaStatusParseError, match="Unable to parse Icinga status"):
            self.icinga.get_status("host[1-2]")

    def test_get_status_missing_hosts(self):
        """It should raise IcingaStatusNotFoundError if any host is missing its status."""
        with open(get_fixture_path("icinga", "status_missing.json")) as f:
            set_mocked_icinga_host_output(self.mocked_icinga_host, f.read())
        with pytest.raises(
            icinga.IcingaStatusNotFoundError,
            match="Host host2 was not found in Icinga status",
        ):
            self.icinga.get_status("host[1-2]")

    def test_get_status_no_output(self):
        """It should raise IcingaError if there is no output from the icinga-status command."""
        self.mocked_icinga_host.run_sync.return_value = iter(())
        with pytest.raises(icinga.IcingaError, match="no output from icinga-status"):
            self.icinga.get_status("host[1-2]")

    @mock.patch("spicerack.decorators.time.sleep", return_value=None)
    def test_wait_for_optimal_ok(self, mocked_sleep):
        """It should return immediately if host is optimal."""
        with open(get_fixture_path("icinga", "status_valid.json")) as f:
            set_mocked_icinga_host_output(self.mocked_icinga_host, f.read())

        self.icinga.wait_for_optimal("host1")
        assert not mocked_sleep.called

    @mock.patch("spicerack.decorators.time.sleep", return_value=None)
    def test_wait_for_optimal_timeout(self, mocked_sleep):
        """It should raise icinga.IcingaError if host is optimal in the required time."""
        with open(get_fixture_path("icinga", "status_with_failed_services.json")) as f:
            set_mocked_icinga_host_output(self.mocked_icinga_host, f.read(), 20)

        with pytest.raises(icinga.IcingaError, match="Not all services are recovered"):
            self.icinga.wait_for_optimal("host1")

        assert mocked_sleep.called


class TestIcingaHosts:
    """Test class for the IcingaHosts class."""

    def setup_method(self):
        """Setup the test environment."""
        # pylint: disable=attribute-defined-outside-init
        self.reason = Reason("Downtime reason", "user1", "orchestration-host", task_id="T12345")
        self.mocked_icinga_host = mock.MagicMock(spec_set=RemoteHosts)
        self.mocked_icinga_host.__len__.return_value = 1
        self.hosts = ["host1.example.com"]
        set_mocked_icinga_host_output(self.mocked_icinga_host, "/var/lib/icinga/rw/icinga.cmd")
        self.icinga_hosts = icinga.IcingaHosts(self.mocked_icinga_host, self.hosts)
        self.mocked_icinga_host.reset_mock()

    def test_init_no_hosts(self):
        """It should raise IcingaError if there are no target hosts."""
        with pytest.raises(icinga.IcingaError, match="Got empty target hosts list"):
            icinga.IcingaHosts(self.mocked_icinga_host, [])

    @pytest.mark.parametrize(
        "target_hosts, verbatim_hosts, effective_hosts",
        (
            (["host1.example.com", "host2.example.com"], False, NodeSet("host[1-2]")),
            (["host1.example.com", "host2.example.com"], True, NodeSet("host[1-2].example.com")),
            (NodeSet("host1.example.com"), False, NodeSet("host1")),
            (NodeSet("host1.example.com"), True, NodeSet("host1.example.com")),
        ),
    )
    @mock.patch("spicerack.icinga.time.time", return_value=1514764800)
    def test_init_hosts(self, mocked_time, target_hosts, verbatim_hosts, effective_hosts):
        """It should init the target hosts according to the input and verbatim option."""
        instance = icinga.IcingaHosts(self.mocked_icinga_host, target_hosts, verbatim_hosts=verbatim_hosts)
        instance.run_icinga_command("TEST_COMMAND", "arg1", "arg2")
        calls = [
            (
                "bash -c 'echo -n \"[1514764800] TEST_COMMAND;{host};arg1;arg2\" > /var/lib/icinga/rw/icinga.cmd '"
            ).format(host=host)
            for host in effective_hosts
        ]

        self.mocked_icinga_host.run_sync.assert_called_once_with(*calls)
        assert mocked_time.called

    @mock.patch("spicerack.icinga.time.time", return_value=1514764800)
    def test_downtimed(self, mocked_time):
        """It should downtime the hosts on Icinga, yield and delete the downtime once done."""
        call = 'icinga-downtime -h "host1" -d 14400 -r {reason}'.format(reason=self.reason.quoted())

        with self.icinga_hosts.downtimed(self.reason):
            self.mocked_icinga_host.run_sync.assert_called_once_with(call)
            self.mocked_icinga_host.run_sync.reset_mock()

        self.mocked_icinga_host.run_sync.assert_has_calls(
            [
                mock.call(
                    'bash -c \'echo -n "[1514764800] DEL_DOWNTIME_BY_HOST_NAME;host1" > '
                    "/var/lib/icinga/rw/icinga.cmd '"
                )
            ]
        )
        assert mocked_time.called

    def test_downtime_is_kept_when_exception_is_raised(self):
        """Downtime should not be removed if an exception is raised."""
        call = 'icinga-downtime -h "host1" -d 14400 -r {reason}'.format(reason=self.reason.quoted())

        with pytest.raises(ValueError):
            with self.icinga_hosts.downtimed(self.reason):
                self.mocked_icinga_host.run_sync.assert_called_once_with(call)
                self.mocked_icinga_host.run_sync.reset_mock()
                raise ValueError()
        assert not self.mocked_icinga_host.run_sync.called

    def test_downtime_is_removed_when_exception_is_raised(self):
        """Downtime should not be removed if an exception is raised."""
        call = 'icinga-downtime -h "host1" -d 14400 -r {reason}'.format(reason=self.reason.quoted())

        with pytest.raises(ValueError):
            with self.icinga_hosts.downtimed(self.reason, remove_on_error=True):
                self.mocked_icinga_host.run_sync.assert_called_once_with(call)
                self.mocked_icinga_host.run_sync.reset_mock()
                raise ValueError()
        assert self.mocked_icinga_host.run_sync.called

    def test_downtime_default_params(self):
        """It should downtime the hosts on the Icinga server with the default params."""
        self.icinga_hosts.downtime(self.reason)
        call = 'icinga-downtime -h "host1" -d 14400 -r {reason}'.format(reason=self.reason.quoted())
        self.mocked_icinga_host.run_sync.assert_called_once_with(call)

    def test_downtime_custom_duration(self):
        """It should downtime the hosts for the given duration on the Icinga server."""
        self.icinga_hosts.downtime(self.reason, duration=timedelta(minutes=30))
        self.mocked_icinga_host.run_sync.assert_called_once_with(
            ('icinga-downtime -h "host1" -d 1800 -r {reason}'.format(reason=self.reason.quoted()))
        )

    def test_downtime_invalid_duration(self):
        """It should raise IcingaError if the duration is too short."""
        with pytest.raises(icinga.IcingaError, match="Downtime duration must be at least 1 minute"):
            self.icinga_hosts.downtime(self.reason, duration=timedelta(seconds=59))

    @mock.patch("spicerack.icinga.time.time", return_value=1514764800)
    def test_run_icinga_command(self, mocked_time):
        """It should run the specified command for all the hosts on the Icinga server."""
        self.icinga_hosts.run_icinga_command("TEST_COMMAND", "arg1", "arg2")
        call = "bash -c 'echo -n \"[1514764800] TEST_COMMAND;host1;arg1;arg2\" > /var/lib/icinga/rw/icinga.cmd '"

        self.mocked_icinga_host.run_sync.assert_called_once_with(call)
        assert mocked_time.called

    @mock.patch("spicerack.icinga.time.time", return_value=1514764800)
    def test_recheck_all_services(self, mocked_time):
        """It should force a recheck of all services for the hosts on the Icinga server."""
        self.icinga_hosts.recheck_all_services()
        self.mocked_icinga_host.run_sync.assert_called_once_with(
            'bash -c \'echo -n "[1514764800] SCHEDULE_FORCED_HOST_SVC_CHECKS;host1;1514764800" > '
            "/var/lib/icinga/rw/icinga.cmd '"
        )
        assert mocked_time.called

    @mock.patch("spicerack.icinga.time.time", return_value=1514764800)
    def test_remove_downtime(self, mocked_time):
        """It should remove the downtime for the hosts on the Icinga server."""
        self.icinga_hosts.remove_downtime()
        self.mocked_icinga_host.run_sync.assert_called_once_with(
            "bash -c 'echo -n \"[1514764800] DEL_DOWNTIME_BY_HOST_NAME;host1\" > /var/lib/icinga/rw/icinga.cmd '"
        )
        assert mocked_time.called

    def test_get_status_ok(self):
        """It should parse the JSON payload and return an instance of HostsStatus."""
        with open(get_fixture_path("icinga", "status_with_failed_services.json")) as f:
            set_mocked_icinga_host_output(self.mocked_icinga_host, f.read())

        status = self.icinga_hosts.get_status()

        assert not status.optimal
        assert status.non_optimal_hosts == ["host2"]
        assert status.failed_services == {"host2": ["check_name1", "check_name2"]}
        assert status.failed_hosts == []

    def test_get_status_parse_fail(self):
        """It should raise IcingaStatusParseError if unable to parse the JSON payload."""
        with open(get_fixture_path("icinga", "status_invalid.json")) as f:
            set_mocked_icinga_host_output(self.mocked_icinga_host, f.read())

        with pytest.raises(icinga.IcingaStatusParseError, match="Unable to parse Icinga status"):
            self.icinga_hosts.get_status()

    def test_get_status_missing_hosts(self):
        """It should raise IcingaStatusNotFoundError if any host is missing its status."""
        with open(get_fixture_path("icinga", "status_missing.json")) as f:
            set_mocked_icinga_host_output(self.mocked_icinga_host, f.read())
        with pytest.raises(
            icinga.IcingaStatusNotFoundError,
            match="Host host2 was not found in Icinga status",
        ):
            self.icinga_hosts.get_status()

    def test_get_status_no_output(self):
        """It should raise IcingaError if there is no output from the icinga-status command."""
        self.mocked_icinga_host.run_sync.return_value = iter(())
        with pytest.raises(icinga.IcingaError, match="no output from icinga-status"):
            self.icinga_hosts.get_status()

    @mock.patch("spicerack.decorators.time.sleep", return_value=None)
    def test_wait_for_optimal_ok(self, mocked_sleep):
        """It should return immediately if host is optimal."""
        with open(get_fixture_path("icinga", "status_valid.json")) as f:
            set_mocked_icinga_host_output(self.mocked_icinga_host, f.read())

        self.icinga_hosts.wait_for_optimal()
        assert not mocked_sleep.called

    @mock.patch("spicerack.decorators.time.sleep", return_value=None)
    def test_wait_for_optimal_timeout(self, mocked_sleep):
        """It should raise icinga.IcingaError if host is optimal in the required time."""
        with open(get_fixture_path("icinga", "status_with_failed_services.json")) as f:
            set_mocked_icinga_host_output(self.mocked_icinga_host, f.read(), 20)

        with pytest.raises(icinga.IcingaError, match="Not all services are recovered"):
            self.icinga_hosts.wait_for_optimal()

        assert mocked_sleep.called


def _get_hoststatus(hostname, down=False, failed=False):
    """Return an instance of HostStatus suitable for testing based on the parameters.

    Arguments:
        hostname: the name to use for the host.
        down: whether the reported state should be UP or DOWN.
        failed: whether if should have some failed services or not.

    """
    params = {
        "name": hostname,
        "state": "UP",
        "optimal": True,
        "failed_services": [],
        "downtimed": False,
        "notifications_enabled": True,
    }

    failed_services = [
        {"host": hostname, "name": "check_name1", "status": {}},
        {"host": hostname, "name": "check_name2", "status": {}},
    ]

    if down:
        params["state"] = "DOWN"
        params["optimal"] = False

    if failed:
        params["failed_services"] = failed_services
        params["optimal"] = False

    return icinga.HostStatus(**params)


def test_hoststatus_failed_services():
    """It should return the list of check names that are failed."""
    status = _get_hoststatus("hostname", failed=True)
    assert status.failed_services == ["check_name1", "check_name2"]


class TestHostsStatus:
    """Tests for the HostsStatus class."""

    def setup_method(self):
        """Setup the test environment."""
        # pylint: disable=attribute-defined-outside-init
        self.status = {
            "ok": icinga.HostsStatus(),  # All optimal hosts
            "down": icinga.HostsStatus(),  # Some hosts are down, no hosts have failed services
            "failed": icinga.HostsStatus(),  # All hosts up, but some have failed services
            "down_failed": icinga.HostsStatus(),  # Some hosts are donw, some have failed services
        }

        for i in range(1, 4):
            hostname = "host{i}".format(i=i)
            self.status["ok"][hostname] = _get_hoststatus(hostname)
            self.status["down"][hostname] = _get_hoststatus(hostname)
            self.status["failed"][hostname] = _get_hoststatus(hostname)
            self.status["down_failed"][hostname] = _get_hoststatus(hostname)

        for i in range(4, 6):
            hostname = "host{i}".format(i=i)
            self.status["down"][hostname] = _get_hoststatus(hostname, down=True)
            self.status["down_failed"][hostname] = _get_hoststatus(hostname, down=True)

        for i in range(6, 8):
            hostname = "host{i}".format(i=i)
            self.status["failed"][hostname] = _get_hoststatus(hostname, failed=True)
            self.status["down_failed"][hostname] = _get_hoststatus(hostname, failed=True)

    def test_optimal_ok(self):
        """It should return True if all hosts are optimal."""
        assert self.status["ok"].optimal

    @pytest.mark.parametrize("key", ("down", "failed", "down_failed"))
    def test_optimal_ko(self, key):
        """If should return False if any host is not optimal."""
        assert not self.status[key].optimal

    @pytest.mark.parametrize(
        "key, expected",
        (
            ("ok", []),
            ("down", ["host4", "host5"]),
            ("failed", ["host6", "host7"]),
            ("down_failed", ["host4", "host5", "host6", "host7"]),
        ),
    )
    def test_non_optimal_hosts(self, key, expected):
        """It should return the list of hostnames with non optimal status."""
        assert sorted(self.status[key].non_optimal_hosts) == expected

    @pytest.mark.parametrize(
        "key, expected",
        (
            ("ok", {}),
            ("down", {"host4": [], "host5": []}),
            (
                "failed",
                {
                    "host6": ["check_name1", "check_name2"],
                    "host7": ["check_name1", "check_name2"],
                },
            ),
            (
                "down_failed",
                {
                    "host4": [],
                    "host5": [],
                    "host6": ["check_name1", "check_name2"],
                    "host7": ["check_name1", "check_name2"],
                },
            ),
        ),
    )
    def test_failed_services(self, key, expected):
        """It should return the dictionary with the hostnames as key and the list of failed services as values."""
        assert self.status[key].failed_services == expected

    @pytest.mark.parametrize(
        "key, expected",
        (
            ("ok", []),
            ("down", ["host4", "host5"]),
            ("failed", []),
            ("down_failed", ["host4", "host5"]),
        ),
    )
    def test_failed_hosts(self, key, expected):
        """It should return the list of hostnames with non optimal status."""
        assert sorted(self.status[key].failed_hosts) == expected
