"""Icinga module tests."""
import logging
import re
import shlex
from datetime import timedelta
from typing import Sequence, Tuple
from unittest import mock

import pytest
from ClusterShell.MsgTree import MsgTreeElem
from cumin import NodeSet
from cumin.transports import Command

from spicerack import icinga
from spicerack.administrative import Reason
from spicerack.remote import RemoteHosts
from spicerack.tests import get_fixture_path


def set_mocked_icinga_host_output(mocked_icinga_host, output, n_hosts=1):
    """Setup the mocked icinga_host return value with the given output."""
    out = MsgTreeElem(output.encode(), parent=MsgTreeElem())
    mocked_icinga_host.run_sync.return_value = iter(n_hosts * [(NodeSet("icinga-host"), out)])


def set_mocked_icinga_host_outputs(mocked_icinga_host, outputs):
    """Setup the mocked icinga_host side effect to return the given outputs, one after another."""
    outs = [MsgTreeElem(output.encode(), parent=MsgTreeElem()) for output in outputs]
    mocked_icinga_host.run_sync.side_effect = [iter([(NodeSet("icinga-host"), out)]) for out in outs]


def get_default_downtime_outputs():
    """Return the outputs suitable for set_mocked_icinga_host_outputs()."""
    with open(get_fixture_path("icinga", "status_valid.json")) as f:
        before = f.read()
    with open(get_fixture_path("icinga", "status_downtimed.json")) as f:
        after = f.read()
    return [before, "", "", after, ""]


def assert_has_downtime_calls(
    mocked_icinga_host: mock.MagicMock,
    hosts: Sequence[str],
    reason: Reason,
    start: int = 1514764800,
    duration: int = 14400,
):
    """Assert that the mocked icinga_host was called correctly to downtime the given hosts."""
    end = start + duration
    args = f"{start};{end};1;0;{duration};{reason.owner};{reason.reason}"
    downtime_calls = [
        [
            "bash -c "
            + shlex.quote(f'echo -n "[{start}] SCHEDULE_HOST_DOWNTIME;{host};{args}" > /var/lib/icinga/rw/icinga.cmd ')
            for host in hosts
        ],
        [
            "bash -c "
            + shlex.quote(
                f'echo -n "[{start}] SCHEDULE_HOST_SVC_DOWNTIME;{host};{args}" > /var/lib/icinga/rw/icinga.cmd '
            )
            for host in hosts
        ],
    ]
    mocked_icinga_host.run_sync.assert_has_calls(
        [mock.call(*call, print_output=False, print_progress_bars=False) for call in downtime_calls]
    )


def assert_has_service_downtime_calls(
    mocked_icinga_host: mock.MagicMock,
    host_services: Sequence[Tuple[str, str]],
    reason: Reason,
    start: int = 1514764800,
    duration: int = 14400,
):
    """Assert that the mocked icinga_host was called correctly to downtime the given services."""
    end = start + duration
    args = f"{start};{end};1;0;{duration};{reason.owner};{reason.reason}"
    downtime_calls = [
        [
            f'bash -c \'echo -n "[{start}] SCHEDULE_SVC_DOWNTIME;{host};{service};{args}" '
            f"> /var/lib/icinga/rw/icinga.cmd '"
            for host, service in host_services
        ],
    ]
    mocked_icinga_host.run_sync.assert_has_calls(
        [mock.call(*call, print_output=False, print_progress_bars=False) for call in downtime_calls]
    )


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
            icinga.CommandFile(self.mocked_icinga_host)

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


def test_status_not_found_error_one_host():
    """Test initializing IcingaStatusNotFoundError with a single host."""
    e = icinga.IcingaStatusNotFoundError(["host1"])
    assert str(e) == "Host host1 was not found in Icinga status"


def test_status_not_found_error_multiple_hosts():
    """Test initializing IcingaStatusNotFoundError with multiple hosts."""
    e = icinga.IcingaStatusNotFoundError(["host1", "host2", "host3"])
    assert str(e) == "Hosts host1, host2, host3 were not found in Icinga status"


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
            f"bash -c 'echo -n \"[1514764800] TEST_COMMAND;{host};arg1;arg2\" > /var/lib/icinga/rw/icinga.cmd '"
            for host in effective_hosts
        ]

        self.mocked_icinga_host.run_sync.assert_called_once_with(*calls, print_output=False, print_progress_bars=False)
        assert mocked_time.called

    @mock.patch("spicerack.icinga.time.time", return_value=1514764800)
    def test_downtimed(self, mocked_time):
        """It should downtime the hosts on Icinga, yield and delete the downtime once done."""
        set_mocked_icinga_host_outputs(self.mocked_icinga_host, get_default_downtime_outputs())
        with self.icinga_hosts.downtimed(self.reason):
            assert_has_downtime_calls(self.mocked_icinga_host, ["host1"], self.reason)
            self.mocked_icinga_host.run_sync.reset_mock()

        self.mocked_icinga_host.run_sync.assert_has_calls(
            [
                mock.call(
                    'bash -c \'echo -n "[1514764800] DEL_DOWNTIME_BY_HOST_NAME;host1" > '
                    "/var/lib/icinga/rw/icinga.cmd '",
                    print_output=False,
                    print_progress_bars=False,
                )
            ]
        )
        assert mocked_time.called

    @mock.patch("spicerack.icinga.time.time", return_value=1514764800)
    def test_downtime_is_kept_when_exception_is_raised(self, _mocked_time):
        """Downtime should not be removed if an exception is raised."""
        set_mocked_icinga_host_outputs(self.mocked_icinga_host, get_default_downtime_outputs())
        with pytest.raises(ValueError):
            with self.icinga_hosts.downtimed(self.reason):
                assert_has_downtime_calls(self.mocked_icinga_host, ["host1"], self.reason)
                self.mocked_icinga_host.run_sync.reset_mock()
                raise ValueError()
        assert not self.mocked_icinga_host.run_sync.called

    @mock.patch("spicerack.icinga.time.time", return_value=1514764800)
    def test_downtime_is_removed_when_exception_is_raised(self, _mocked_time):
        """Downtime should be removed if an exception is raised."""
        set_mocked_icinga_host_outputs(self.mocked_icinga_host, get_default_downtime_outputs())
        with pytest.raises(ValueError):
            with self.icinga_hosts.downtimed(self.reason, remove_on_error=True):
                assert_has_downtime_calls(self.mocked_icinga_host, ["host1"], self.reason)
                self.mocked_icinga_host.run_sync.reset_mock()
                raise ValueError()
        assert self.mocked_icinga_host.run_sync.called

    @mock.patch("spicerack.icinga.time.time", return_value=1514764800)
    def test_downtime_default_params(self, _mocked_time):
        """It should downtime the hosts on the Icinga server with the default params."""
        set_mocked_icinga_host_outputs(self.mocked_icinga_host, get_default_downtime_outputs())
        self.icinga_hosts.downtime(self.reason)
        assert_has_downtime_calls(self.mocked_icinga_host, ["host1"], self.reason)

    @mock.patch("spicerack.icinga.time.time", return_value=1514764800)
    @mock.patch("spicerack.icinga.time.sleep", return_value=None)
    def test_downtime_default_params_failed_ensure(self, mocked_sleep, _mocked_time, caplog):
        """It should not raise and just log a warning if unable to verify if the downtime was applied."""
        with open(get_fixture_path("icinga", "status_valid.json")) as f:
            not_downtimed = f.read()
        set_mocked_icinga_host_outputs(self.mocked_icinga_host, [not_downtimed, "", ""] + [not_downtimed] * 13)
        with caplog.at_level(logging.INFO):
            self.icinga_hosts.downtime(self.reason)
        assert_has_downtime_calls(self.mocked_icinga_host, ["host1"], self.reason)
        assert "Some hosts are not yet downtimed: ['host1']" in caplog.text
        mocked_sleep.assert_called()

    @mock.patch("spicerack.icinga.time.time", return_value=1514764800)
    def test_downtime_with_apostrophe_in_reason(self, _mocked_time):
        """It should correctly quote the apostrophe in the reason string."""
        set_mocked_icinga_host_outputs(self.mocked_icinga_host, get_default_downtime_outputs())
        reason = Reason("An apostrophe's here", "user1", "orchestration-host", task_id="T12345")
        self.icinga_hosts.downtime(reason)
        assert_has_downtime_calls(self.mocked_icinga_host, ["host1"], reason)

    @mock.patch("spicerack.icinga.time.time", return_value=1514764800)
    def test_downtime_custom_duration(self, _mocked_time):
        """It should downtime the hosts for the given duration on the Icinga server."""
        set_mocked_icinga_host_outputs(self.mocked_icinga_host, get_default_downtime_outputs())
        self.icinga_hosts.downtime(self.reason, duration=timedelta(minutes=30))
        assert_has_downtime_calls(self.mocked_icinga_host, ["host1"], self.reason, duration=1800)

    def test_downtime_invalid_duration(self):
        """It should raise IcingaError if the duration is too short."""
        with pytest.raises(icinga.IcingaError, match="Downtime duration must be at least 1 minute"):
            self.icinga_hosts.downtime(self.reason, duration=timedelta(seconds=59))

    def test_downtime_unknown_host(self):
        """It should raise IcingaError if any host is not known to Icinga."""
        set_mocked_icinga_host_output(self.mocked_icinga_host, '{"host1": null}')
        with pytest.raises(
            icinga.IcingaError, match="Host host1 was not found in Icinga status - no hosts have been downtimed"
        ):
            self.icinga_hosts.downtime(self.reason)

    def test_wait_for_downtimed_already_downtimed(self):
        """It should return immediately if all hosts are already downtimed."""
        with open(get_fixture_path("icinga", "status_downtimed.json")) as f:
            set_mocked_icinga_host_output(self.mocked_icinga_host, f.read())

        self.icinga_hosts.wait_for_downtimed()
        self.mocked_icinga_host.run_sync.assert_called_once()

    @pytest.mark.parametrize("tries", range(1, 12))
    @mock.patch("spicerack.icinga.time.sleep", return_value=None)
    def test_wait_for_downtimed_retry(self, mocked_sleep, tries):
        """It should poll until the host gets downtimed."""
        with open(get_fixture_path("icinga", "status_valid.json")) as f:
            not_downtimed = f.read()
        with open(get_fixture_path("icinga", "status_downtimed.json")) as f:
            downtimed = f.read()

        set_mocked_icinga_host_outputs(self.mocked_icinga_host, [not_downtimed] * tries + [downtimed])

        self.icinga_hosts.wait_for_downtimed()
        assert self.mocked_icinga_host.run_sync.call_count == tries + 1
        assert mocked_sleep.call_count == tries

    @mock.patch("spicerack.icinga.time.sleep", return_value=None)
    def test_wait_for_downtimed_fail(self, mocked_sleep):
        """It should raise an IcingaCheckError if unable to verify it."""
        with open(get_fixture_path("icinga", "status_valid.json")) as f:
            not_downtimed = f.read()
        set_mocked_icinga_host_outputs(self.mocked_icinga_host, [not_downtimed] * 13)

        with pytest.raises(icinga.IcingaCheckError, match=re.escape("Some hosts are not yet downtimed: ['host1']")):
            self.icinga_hosts.wait_for_downtimed()

        assert self.mocked_icinga_host.run_sync.call_count == 12
        assert mocked_sleep.call_count == 11

    @mock.patch("spicerack.icinga.time.time", return_value=1514764800)
    def test_services_downtimed(self, mocked_time):
        """It should downtime the hosts on Icinga, yield and delete the downtime once done."""
        with open(get_fixture_path("icinga", "status_with_services.json")) as before:
            with open(get_fixture_path("icinga", "status_with_services_downtimed.json")) as after:
                set_mocked_icinga_host_outputs(self.mocked_icinga_host, [before.read(), "", after.read(), ""])
        with self.icinga_hosts.services_downtimed("service.*", self.reason):
            assert_has_service_downtime_calls(
                self.mocked_icinga_host, [("host1", "service1"), ("host1", "service2")], self.reason
            )
            self.mocked_icinga_host.run_sync.reset_mock()

        self.mocked_icinga_host.run_sync.assert_called_with(
            'bash -c \'echo -n "[1514764800] DEL_DOWNTIME_BY_HOST_NAME;host1;service1" > '
            "/var/lib/icinga/rw/icinga.cmd '",
            'bash -c \'echo -n "[1514764800] DEL_DOWNTIME_BY_HOST_NAME;host1;service2" > '
            "/var/lib/icinga/rw/icinga.cmd '",
            print_output=False,
            print_progress_bars=False,
        )
        assert mocked_time.called

    @mock.patch("spicerack.icinga.time.time", return_value=1514764800)
    def test_services_downtime_is_kept_when_exception_is_raised(self, _mocked_time):
        """Downtime should not be removed if an exception is raised."""
        with open(get_fixture_path("icinga", "status_with_services.json")) as f:
            set_mocked_icinga_host_outputs(self.mocked_icinga_host, [f.read(), "", "", ""])
        with pytest.raises(ValueError):
            with self.icinga_hosts.services_downtimed("service.*", self.reason):
                assert_has_service_downtime_calls(
                    self.mocked_icinga_host, [("host1", "service1"), ("host1", "service2")], self.reason
                )
                self.mocked_icinga_host.run_sync.reset_mock()
                raise ValueError()
        assert not self.mocked_icinga_host.run_sync.called

    @mock.patch("spicerack.icinga.time.time", return_value=1514764800)
    def test_services_downtime_is_removed_when_exception_is_raised(self, _mocked_time):
        """Downtime should not be removed if an exception is raised."""
        with open(get_fixture_path("icinga", "status_with_services.json")) as before:
            with open(get_fixture_path("icinga", "status_with_services_downtimed.json")) as after:
                set_mocked_icinga_host_outputs(self.mocked_icinga_host, [before.read(), "", after.read(), ""])
        with pytest.raises(ValueError):
            with self.icinga_hosts.services_downtimed("service.*", self.reason, remove_on_error=True):
                assert_has_service_downtime_calls(
                    self.mocked_icinga_host, [("host1", "service1"), ("host1", "service2")], self.reason
                )
                self.mocked_icinga_host.run_sync.reset_mock()
                raise ValueError()
        assert self.mocked_icinga_host.run_sync.called

    @mock.patch("spicerack.icinga.time.time", return_value=1514764800)
    def test_downtime_services_default_params(self, _mocked_time, caplog):
        """It should downtime the services on the Icinga server with the default params."""
        with open(get_fixture_path("icinga", "status_with_services.json")) as f:
            set_mocked_icinga_host_outputs(self.mocked_icinga_host, [f.read(), "", "", ""])
        with caplog.at_level(logging.INFO):
            self.icinga_hosts.downtime_services(r"service\d", self.reason)
        assert_has_service_downtime_calls(
            self.mocked_icinga_host, [("host1", "service1"), ("host1", "service2")], self.reason
        )
        assert r'for services "service\d" for host: host1 (matched 2 unique service names on 1 host)' in caplog.text

    @mock.patch("spicerack.icinga.time.time", return_value=1514764800)
    def test_downtime_services_custom_duration(self, _mocked_time):
        """It should downtime the services for the given duration on the Icinga server."""
        with open(get_fixture_path("icinga", "status_with_services.json")) as f:
            set_mocked_icinga_host_outputs(self.mocked_icinga_host, [f.read(), "", "", ""])
        self.icinga_hosts.downtime_services(r"service\d", self.reason, duration=timedelta(minutes=30))
        assert_has_service_downtime_calls(
            self.mocked_icinga_host, [("host1", "service1"), ("host1", "service2")], self.reason, duration=1800
        )

    def test_downtime_services_invalid_duration(self):
        """It should raise IcingaError if the duration is too short."""
        with pytest.raises(icinga.IcingaError, match="Downtime duration must be at least 1 minute"):
            self.icinga_hosts.downtime_services(r"service\d", self.reason, duration=timedelta(seconds=59))

    def test_downtime_services_unknown_host(self):
        """It should raise IcingaError if any host is not known to Icinga."""
        set_mocked_icinga_host_output(self.mocked_icinga_host, '{"host1": null}')
        with pytest.raises(
            icinga.IcingaError, match="Host host1 was not found in Icinga status - no hosts have been downtimed"
        ):
            self.icinga_hosts.downtime_services(r"service\d", self.reason)

    def test_downtime_services_unknown_service(self):
        """It should raise IcingaError if no services match the regex."""
        with open(get_fixture_path("icinga", "status_with_no_matching_services.json")) as f:
            set_mocked_icinga_host_outputs(self.mocked_icinga_host, [f.read(), "", "", ""])
        with pytest.raises(icinga.IcingaError, match=r'No services on host1 matched "service\\d"'):
            self.icinga_hosts.downtime_services(r"service\d", self.reason)

    @mock.patch("spicerack.icinga.time.time", return_value=1514764800)
    def test_run_icinga_command(self, mocked_time):
        """It should run the specified command for all the hosts on the Icinga server."""
        self.icinga_hosts.run_icinga_command("TEST_COMMAND", "arg1", "arg2")
        call = "bash -c 'echo -n \"[1514764800] TEST_COMMAND;host1;arg1;arg2\" > /var/lib/icinga/rw/icinga.cmd '"

        self.mocked_icinga_host.run_sync.assert_called_once_with(call, print_output=False, print_progress_bars=False)
        assert mocked_time.called

    @mock.patch("spicerack.icinga.time.time", return_value=1514764800)
    def test_recheck_all_services(self, mocked_time):
        """It should force a recheck of all services for the hosts on the Icinga server."""
        self.icinga_hosts.recheck_all_services()
        self.mocked_icinga_host.run_sync.assert_called_once_with(
            'bash -c \'echo -n "[1514764800] SCHEDULE_FORCED_HOST_SVC_CHECKS;host1;1514764800" > '
            "/var/lib/icinga/rw/icinga.cmd '",
            print_output=False,
            print_progress_bars=False,
        )
        assert mocked_time.called

    @mock.patch("spicerack.icinga.time.time", return_value=1514764800)
    def test_recheck_failed_services_failed(self, mocked_time):
        """It should force a recheck of all services for the hosts on the Icinga server."""
        with open(get_fixture_path("icinga", "status_with_failed_services.json")) as f:
            set_mocked_icinga_host_output(self.mocked_icinga_host, f.read())

        self.icinga_hosts.recheck_failed_services()
        self.mocked_icinga_host.run_sync.assert_called_with(
            'bash -c \'echo -n "[1514764800] SCHEDULE_FORCED_SVC_CHECK;host2;check_name1;1514764800" > '
            "/var/lib/icinga/rw/icinga.cmd '",
            'bash -c \'echo -n "[1514764800] SCHEDULE_FORCED_SVC_CHECK;host2;check_name2;1514764800" > '
            "/var/lib/icinga/rw/icinga.cmd '",
            print_output=False,
            print_progress_bars=False,
        )
        assert mocked_time.called

    def test_recheck_failed_services_optimal(self):
        """It should force a recheck of all services for the hosts on the Icinga server."""
        with open(get_fixture_path("icinga", "status_with_services.json")) as f:
            set_mocked_icinga_host_output(self.mocked_icinga_host, f.read())

        self.icinga_hosts.recheck_failed_services()
        # This also ensures that we are not making an additional call of run_sync in the recheck method
        self.mocked_icinga_host.run_sync.assert_called_with(
            Command('/usr/local/bin/icinga-status -j "host1"', ok_codes=[]),
            is_safe=True,
            print_output=False,
            print_progress_bars=False,
        )

    @mock.patch("spicerack.icinga.time.time", return_value=1514764800)
    def test_remove_downtime(self, mocked_time):
        """It should remove the downtime for the hosts on the Icinga server."""
        self.icinga_hosts.remove_downtime()
        self.mocked_icinga_host.run_sync.assert_called_once_with(
            "bash -c 'echo -n \"[1514764800] DEL_DOWNTIME_BY_HOST_NAME;host1\" > /var/lib/icinga/rw/icinga.cmd '",
            print_output=False,
            print_progress_bars=False,
        )
        assert mocked_time.called

    @mock.patch("spicerack.icinga.time.time", return_value=1514764800)
    def test_remove_service_downtimes(self, mocked_time):
        """It should remove the downtime for the hosts on the Icinga server."""
        with open(get_fixture_path("icinga", "status_with_services_downtimed.json")) as f:
            set_mocked_icinga_host_outputs(self.mocked_icinga_host, [f.read(), "", "", ""])
        self.icinga_hosts.remove_service_downtimes(r"service\d")
        self.mocked_icinga_host.run_sync.assert_called_with(
            *[
                f'bash -c \'echo -n "[1514764800] DEL_DOWNTIME_BY_HOST_NAME;host1;{service}" '
                f"> /var/lib/icinga/rw/icinga.cmd '"
                for service in ["service1", "service2"]
            ],
            print_output=False,
            print_progress_bars=False,
        )
        assert mocked_time.called

    def test_remove_service_downtimes_not_downtimed(self):
        """It should do nothing if the services exist but aren't downtimed."""
        with open(get_fixture_path("icinga", "status_with_services.json")) as f:
            set_mocked_icinga_host_outputs(self.mocked_icinga_host, [f.read(), "", "", ""])
        self.icinga_hosts.remove_service_downtimes(r"service\d")
        self.mocked_icinga_host.run_sync.assert_called_once()  # Only the icinga-status call, no downtimes.

    def test_remove_service_downtimes_unknown_service(self):
        """It should raise IcingaError if no services match the regex."""
        with open(get_fixture_path("icinga", "status_with_no_matching_services.json")) as f:
            set_mocked_icinga_host_outputs(self.mocked_icinga_host, [f.read(), "", "", ""])
        with pytest.raises(icinga.IcingaError, match=r'No services on host1 matched "service\\d"'):
            self.icinga_hosts.remove_service_downtimes(r"service\d")

    def test_get_status_ok(self):
        """It should parse the JSON payload and return an instance of HostsStatus."""
        with open(get_fixture_path("icinga", "status_with_failed_services.json")) as f:
            set_mocked_icinga_host_output(self.mocked_icinga_host, f.read())

        status = self.icinga_hosts.get_status()

        assert "--services" not in self.mocked_icinga_host.run_sync.call_args[0][0].command
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

    def test_get_status_with_services(self):
        """It should parse the JSON payload and return an instance of HostsStatus with service status."""
        with open(get_fixture_path("icinga", "status_with_services.json")) as f:
            set_mocked_icinga_host_output(self.mocked_icinga_host, f.read())

        status = self.icinga_hosts.get_status(service_re=r"service\d")

        assert r"--services 'service\d'" in self.mocked_icinga_host.run_sync.call_args[0][0].command
        assert status.optimal
        assert {service["name"] for service in status["host1"].services} == {"service1", "service2"}
        assert status.failed_hosts == []

    def test_get_status_with_invalid_services_re(self):
        """It should raise re.error if the services regex is invalid."""
        with pytest.raises(re.error, match="nothing to repeat at position 0"):
            self.icinga_hosts.get_status(service_re="+")

    @mock.patch("wmflib.decorators.time.sleep", return_value=None)
    def test_wait_for_optimal_ok(self, mocked_sleep):
        """It should return immediately if host is optimal."""
        with open(get_fixture_path("icinga", "status_valid.json")) as f:
            set_mocked_icinga_host_output(self.mocked_icinga_host, f.read(), 2)

        self.icinga_hosts.wait_for_optimal()
        assert not mocked_sleep.called

    @mock.patch("wmflib.decorators.time.sleep", return_value=None)
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
            hostname = f"host{i}"
            self.status["ok"][hostname] = _get_hoststatus(hostname)
            self.status["down"][hostname] = _get_hoststatus(hostname)
            self.status["failed"][hostname] = _get_hoststatus(hostname)
            self.status["down_failed"][hostname] = _get_hoststatus(hostname)

        for i in range(4, 6):
            hostname = f"host{i}"
            self.status["down"][hostname] = _get_hoststatus(hostname, down=True)
            self.status["down_failed"][hostname] = _get_hoststatus(hostname, down=True)

        for i in range(6, 8):
            hostname = f"host{i}"
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
