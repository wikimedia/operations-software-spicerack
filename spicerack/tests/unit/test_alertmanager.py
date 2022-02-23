"""Alertmanager module tests."""

from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest
import requests
from cumin import NodeSet

from spicerack import alertmanager
from spicerack.administrative import Reason


class TestAlertmanager:
    """Tests for the Alertmanager class."""

    @pytest.fixture(autouse=True)
    def setup_method(self, requests_mock):
        """Initialize the test instance."""
        # pylint: disable=attribute-defined-outside-init
        self.am_hosts = alertmanager.AlertmanagerHosts(["host1", "host2"])
        self.requests_mock = requests_mock
        self.reason = Reason("test", "user", "host")

    def test_add_silence_basic(self):
        """It should issue a silence with all defaults."""
        self.requests_mock.post("/api/v2/silences", json={"silenceID": "foobar"})
        response = self.am_hosts.downtime(self.reason)
        assert response == "foobar"
        assert self.requests_mock.last_request.hostname == "alertmanager-eqiad.wikimedia.org"
        request_json = self.requests_mock.last_request.json()
        assert request_json["matchers"] == [
            {"name": "instance", "value": r"^host1(:[0-9]+)?$", "isRegex": True},
            {"name": "instance", "value": r"^host2(:[0-9]+)?$", "isRegex": True},
        ]
        assert request_json["comment"] == "test - user@host"
        assert request_json["createdBy"] == "user@host"

    def test_add_silence_duration(self):
        """It should issue a silence with a given duration."""
        self.requests_mock.post("/api/v2/silences", json={"silenceID": "foobar"})
        with mock.patch("spicerack.alertmanager.datetime") as dt_mock:
            dt_mock.utcnow.return_value = datetime(2022, 6, 6, 10, 00, 00, tzinfo=timezone.utc)
            self.am_hosts.downtime(self.reason, duration=timedelta(hours=6))
        request_json = self.requests_mock.last_request.json()
        assert request_json["startsAt"] == "2022-06-06T10:00:00+00:00"
        assert request_json["endsAt"] == "2022-06-06T16:00:00+00:00"

    def test_delete_silence_basic(self):
        """It should delete a downtime."""
        self.requests_mock.delete("/api/v2/silence/foobar")
        self.am_hosts.remove_downtime("foobar")
        assert self.requests_mock.call_count == 1

    def test_verbatim_hosts(self):
        """It should issue silences for verbatim hosts."""
        self.requests_mock.post("/api/v2/silences", json={"silenceID": "foobar"})
        am_hosts = alertmanager.AlertmanagerHosts(["host1.foo.bar", "host2.bar.baz"], verbatim_hosts=True)
        am_hosts.downtime(self.reason)
        request_json = self.requests_mock.last_request.json()
        assert request_json["matchers"] == [
            {"name": "instance", "value": r"^host2\.bar\.baz(:[0-9]+)?$", "isRegex": True},
            {"name": "instance", "value": r"^host1\.foo\.bar(:[0-9]+)?$", "isRegex": True},
        ]

    def test_nodeset_hosts(self):
        """It should expand NodeSet hosts."""
        self.requests_mock.post("/api/v2/silences", json={"silenceID": "foobar"})
        am_hosts = alertmanager.AlertmanagerHosts(NodeSet("host[1-2]"), verbatim_hosts=True)
        am_hosts.downtime(self.reason)
        request_json = self.requests_mock.last_request.json()
        assert request_json["matchers"] == [
            {"name": "instance", "value": r"^host1(:[0-9]+)?$", "isRegex": True},
            {"name": "instance", "value": r"^host2(:[0-9]+)?$", "isRegex": True},
        ]

    # pylint: disable=no-self-use
    def test_empty_target_hosts(self):
        """It should error with empty hosts."""
        with pytest.raises(alertmanager.AlertmanagerError):
            alertmanager.AlertmanagerHosts([""])

    def test_downtimed(self):
        """It should issue a silence and then delete it."""
        self.requests_mock.post("/api/v2/silences", json={"silenceID": "foobar"})
        self.requests_mock.delete("/api/v2/silence/foobar")
        with self.am_hosts.downtimed(self.reason):
            assert self.requests_mock.call_count == 1
        assert self.requests_mock.call_count == 2

    @pytest.mark.parametrize(
        "remove_on_error, total_call_count",
        (
            (True, 2),
            (False, 1),
        ),
    )
    def test_downtimed_remove_on_error(self, remove_on_error, total_call_count):
        """It should issue a silence and then delete it even with errors."""
        self.requests_mock.post("/api/v2/silences", json={"silenceID": "foobar"})
        self.requests_mock.delete("/api/v2/silence/foobar")
        with pytest.raises(ValueError):
            with self.am_hosts.downtimed(self.reason, remove_on_error=remove_on_error):
                assert self.requests_mock.call_count == 1
                raise ValueError()
        assert self.requests_mock.call_count == total_call_count

    def test_connection_errors(self):
        """It should raise AlertmanagerError when unable to contact the API."""
        self.requests_mock.post("/api/v2/silences", exc=requests.exceptions.ConnectionError)
        with pytest.raises(alertmanager.AlertmanagerError):
            self.am_hosts.downtime(self.reason)

    def test_fallback_on_error(self):
        """It should fallback to the next Alertmanager on error."""
        ams = alertmanager.ALERTMANAGER_URLS
        self.requests_mock.post(f"{ams[0]}/api/v2/silences", exc=requests.exceptions.ConnectionError)
        self.requests_mock.post(f"{ams[1]}/api/v2/silences", json={"silenceID": "foobar"})
        assert "foobar" == self.am_hosts.downtime(self.reason)
