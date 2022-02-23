"""Alertmanager module tests."""

from unittest import mock

import pytest

from spicerack import alerting, alertmanager, icinga
from spicerack.administrative import Reason
from spicerack.remote import RemoteHosts
from spicerack.tests.unit.test_icinga import set_mocked_icinga_host_output


class TestAlerting:
    """Tests for the Alerting class."""

    @pytest.fixture(autouse=True)
    def setup_method(self, requests_mock):
        """Initialize the test instance."""
        # pylint: disable=attribute-defined-outside-init
        self.hosts = ["host1.example.com"]
        self.reason = Reason("test", "user", "host")

        self.mocked_icinga_host = mock.MagicMock(spec_set=RemoteHosts)
        self.mocked_icinga_host.__len__.return_value = 1
        set_mocked_icinga_host_output(self.mocked_icinga_host, "/var/lib/icinga/rw/icinga.cmd")
        self.icinga_hosts = icinga.IcingaHosts(self.mocked_icinga_host, self.hosts)

        self.am_hosts = alertmanager.AlertmanagerHosts(self.hosts)
        self.requests_mock = requests_mock

        self.alerting_hosts = alerting.AlertingHosts(self.am_hosts, self.icinga_hosts)

    @mock.patch("spicerack.icinga.IcingaHosts.downtime")
    @mock.patch("spicerack.alertmanager.AlertmanagerHosts.downtime", return_value="foo")
    def test_downtime(self, am_dt, icinga_dt):
        """It should call both Alertmanager and Icinga."""
        assert "foo" == self.alerting_hosts.downtime(self.reason)
        assert am_dt.called
        assert icinga_dt.called

    @mock.patch("spicerack.icinga.IcingaHosts.remove_downtime")
    @mock.patch("spicerack.alertmanager.AlertmanagerHosts.remove_downtime")
    def test_remove_downtime(self, am_rmdt, icinga_rmdt):
        """It should call both Alertmanager and Icinga."""
        self.alerting_hosts.remove_downtime("foo")
        assert am_rmdt.called
        assert icinga_rmdt.called

    @mock.patch("spicerack.icinga.IcingaHosts.downtime")
    @mock.patch("spicerack.alertmanager.AlertmanagerHosts.downtime")
    @mock.patch("spicerack.icinga.IcingaHosts.remove_downtime")
    @mock.patch("spicerack.alertmanager.AlertmanagerHosts.remove_downtime")
    def test_downtimed(self, am_rmdt, icinga_rmdt, am_dt, icinga_dt):
        """It should issue a silence and then delete it."""
        with self.alerting_hosts.downtimed(self.reason):
            assert am_dt.called
            assert icinga_dt.called
        assert am_rmdt.called
        assert icinga_rmdt.called

    @pytest.mark.parametrize(
        "remove_on_error, remove_downtime_calls",
        (
            (True, 1),
            (False, 0),
        ),
    )
    @mock.patch("spicerack.icinga.IcingaHosts.downtime")
    @mock.patch("spicerack.alertmanager.AlertmanagerHosts.downtime")
    @mock.patch("spicerack.icinga.IcingaHosts.remove_downtime")
    @mock.patch("spicerack.alertmanager.AlertmanagerHosts.remove_downtime")
    def test_downtimed_on_error(
        self, am_rmdt, icinga_rmdt, am_dt, icinga_dt, remove_on_error, remove_downtime_calls
    ):  # pylint: disable=too-many-arguments
        """It should issue a silence and then delete it even with errors."""
        with pytest.raises(ValueError):
            with self.alerting_hosts.downtimed(self.reason, remove_on_error=remove_on_error):
                assert am_dt.called
                assert icinga_dt.called
                raise ValueError()
        assert am_rmdt.call_count == remove_downtime_calls
        assert icinga_rmdt.call_count == remove_downtime_calls
