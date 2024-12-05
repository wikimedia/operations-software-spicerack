"""Alertmanager module tests."""

import logging
from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest
import requests
from cumin import nodeset
from requests.auth import HTTPBasicAuth

from spicerack import alertmanager
from spicerack.administrative import Reason

ALERTMANAGER_URLS: tuple[str, str] = (
    "http://alertmanager-eqiad.wikimedia.example",
    "http://alertmanager-codfw.wikimedia.example",
)


class TestAlertmanager:
    """Tests for the Alertmanager class."""

    @pytest.fixture(autouse=True)
    def setup_method(self, requests_mock):
        """Initialize the test instance."""
        # pylint: disable=attribute-defined-outside-init
        self.matchers = [
            {"name": "site", "value": "dc1", "isRegex": False},
            {"name": "label1", "value": "value1", "isRegex": False},
        ]
        self.alertmanager = alertmanager.Alertmanager(alertmanager_urls=ALERTMANAGER_URLS, dry_run=False)
        self.am_dry_run = alertmanager.Alertmanager(alertmanager_urls=ALERTMANAGER_URLS, dry_run=True)
        self.am_authenticated = alertmanager.Alertmanager(
            alertmanager_urls=ALERTMANAGER_URLS,
            dry_run=False,
            http_authentication=HTTPBasicAuth("spicerack", "example2"),
        )
        self.requests_mock = requests_mock
        self.reason = Reason("test", "user", "host")

    def test_add_silence_basic(self):
        """It should issue a silence with all the matchers."""
        self.requests_mock.post("/api/v2/silences", json={"silenceID": "foobar"})
        response = self.alertmanager.downtime(self.reason, matchers=self.matchers)
        assert response == "foobar"
        assert self.requests_mock.last_request.hostname == "alertmanager-eqiad.wikimedia.example"
        request_json = self.requests_mock.last_request.json()
        assert request_json["matchers"] == self.matchers
        assert request_json["comment"] == "test - user@host"
        assert request_json["createdBy"] == "user@host"

    def test_add_silence_no_matchers(self):
        """It should raise an AlertmanagerError if there are no matchers specified."""
        with pytest.raises(alertmanager.AlertmanagerError, match="No matchers provided"):
            self.alertmanager.downtime(self.reason, matchers=[])

    def test_add_silence_duration(self):
        """It should issue a silence with a given duration."""
        self.requests_mock.post("/api/v2/silences", json={"silenceID": "foobar"})
        with mock.patch("spicerack.alertmanager.datetime") as dt_mock:
            dt_mock.now.return_value = datetime(2022, 6, 6, 10, 00, 00, tzinfo=timezone.utc)
            self.alertmanager.downtime(self.reason, matchers=self.matchers, duration=timedelta(hours=6))
        request_json = self.requests_mock.last_request.json()
        assert request_json["startsAt"] == "2022-06-06T10:00:00+00:00"
        assert request_json["endsAt"] == "2022-06-06T16:00:00+00:00"

    def test_add_silence_dry_run(self):
        """It should not create a silence because in dry-run mode."""
        self.requests_mock.post("/api/v2/silences", json={"silenceID": "foobar"})
        response = self.am_dry_run.downtime(self.reason, matchers=self.matchers)
        assert response == ""
        assert self.requests_mock.call_count == 0

    def test_delete_silence_dry_run(self):
        """It should delete a downtime."""
        self.requests_mock.delete("/api/v2/silence/foobar")
        self.am_dry_run.remove_downtime("nonexistent")
        assert self.requests_mock.call_count == 0

    def test_delete_silence_basic(self):
        """It should delete a downtime."""
        self.requests_mock.delete("/api/v2/silence/foobar")
        self.alertmanager.remove_downtime("foobar")
        assert self.requests_mock.call_count == 1

    def test_delete_silence_already_deleted(self, caplog):
        """It should not error if the downtime has been already deleted or is expired."""
        self.requests_mock.delete("/api/v2/silence/foobar", status_code=500, json="silence foobar already expired")
        with caplog.at_level(logging.WARNING):
            self.alertmanager.remove_downtime("foobar")

        assert "Silence ID foobar has been already deleted or is expired" in caplog.text
        assert self.requests_mock.call_count == 2

    def test_delete_silence_error(self, caplog):
        """It should raise an AlertmanagerError on any other error."""
        self.requests_mock.delete("/api/v2/silence/foobar", status_code=500, json="silence not found")
        with caplog.at_level(logging.WARNING):
            with pytest.raises(alertmanager.AlertmanagerError, match="Unable to DELETE to any Alertmanager"):
                self.alertmanager.remove_downtime("foobar")

        assert "already deleted" not in caplog.text
        assert self.requests_mock.call_count == 2

    def test_downtimed(self):
        """It should issue a silence and then delete it."""
        self.requests_mock.post("/api/v2/silences", json={"silenceID": "foobar"})
        self.requests_mock.delete("/api/v2/silence/foobar")
        with self.alertmanager.downtimed(self.reason, matchers=self.matchers):
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
            with self.alertmanager.downtimed(self.reason, matchers=self.matchers, remove_on_error=remove_on_error):
                assert self.requests_mock.call_count == 1
                raise ValueError()
        assert self.requests_mock.call_count == total_call_count

    def test_connection_errors(self):
        """It should raise AlertmanagerError when unable to contact the API."""
        self.requests_mock.post("/api/v2/silences", exc=requests.exceptions.ConnectionError)
        with pytest.raises(alertmanager.AlertmanagerError):
            self.alertmanager.downtime(self.reason, matchers=self.matchers)

    def test_fallback_on_error(self):
        """It should fallback to the next Alertmanager on error."""
        self.requests_mock.post(f"{ALERTMANAGER_URLS[0]}/api/v2/silences", exc=requests.exceptions.ConnectionError)
        self.requests_mock.post(f"{ALERTMANAGER_URLS[1]}/api/v2/silences", json={"silenceID": "foobar"})
        assert "foobar" == self.alertmanager.downtime(self.reason, matchers=self.matchers)
        assert self.requests_mock.last_request.hostname == "alertmanager-codfw.wikimedia.example"

    def test_uses_http_authentication(self):
        """It should use the given HTTP authentication configuration."""
        self.requests_mock.post("/api/v2/silences", json={"silenceID": "foobar"})
        assert "foobar" == self.am_authenticated.downtime(self.reason, matchers=self.matchers)
        # c3BpY2VyYWNrOmV4YW1wbGUy == base64(spicerack:example2)
        assert self.requests_mock.last_request.headers["Authorization"] == "Basic c3BpY2VyYWNrOmV4YW1wbGUy"


class TestAlertmanagerHosts:
    """Tests for the AlertmanagerHosts class."""

    @pytest.fixture(autouse=True)
    def setup_method(self, requests_mock):
        """Initialize the test instance."""
        # pylint: disable=attribute-defined-outside-init
        self.am_hosts = alertmanager.AlertmanagerHosts(
            ["host1", "host2"], alertmanager_urls=ALERTMANAGER_URLS, dry_run=False
        )
        self.am_hosts_dry_run = alertmanager.AlertmanagerHosts(
            ["host1", "host2"], alertmanager_urls=ALERTMANAGER_URLS, dry_run=True
        )
        self.requests_mock = requests_mock
        self.reason = Reason("test", "user", "host")

    @pytest.mark.parametrize(
        "hosts, regex",
        (
            (["host1", "host2"], r"^(host1|host2)(\..+)?(:[0-9]+)?$"),
            (["host1:1234", "host2"], r"^(host1:1234|host2(\..+)?(:[0-9]+)?)$"),
            (["host1.example.com:1234", "host2"], r"^(host1|host2)(\..+)?(:[0-9]+)?$"),
            (["host1:1234", "host2.example.com:5678"], r"^(host1:1234|host2(\..+)?(:[0-9]+)?)$"),
        ),
    )
    def test_add_silence_basic(self, hosts, regex):
        """It should issue a silence with all defaults."""
        self.requests_mock.post("/api/v2/silences", json={"silenceID": "foobar"})
        am_hosts = alertmanager.AlertmanagerHosts(hosts, alertmanager_urls=ALERTMANAGER_URLS, dry_run=False)
        response = am_hosts.downtime(self.reason)
        assert response == "foobar"
        assert self.requests_mock.last_request.hostname == "alertmanager-eqiad.wikimedia.example"
        request_json = self.requests_mock.last_request.json()
        assert request_json["matchers"] == [
            {"name": "instance", "value": regex, "isRegex": True},
        ]
        assert request_json["comment"] == "test - user@host"
        assert request_json["createdBy"] == "user@host"

    def test_add_silence_additional_matchers(self):
        """It should issue a silence with the provided additional matchers."""
        self.requests_mock.post("/api/v2/silences", json={"silenceID": "foobar"})
        self.am_hosts.downtime(self.reason, matchers=({"name": "severity", "value": "critical", "isRegex": False},))
        request_json = self.requests_mock.last_request.json()
        assert request_json["matchers"] == [
            {"name": "severity", "value": "critical", "isRegex": False},
            {"name": "instance", "value": r"^(host1|host2)(\..+)?(:[0-9]+)?$", "isRegex": True},
        ]

    def test_add_silence_additional_matchers_invalid(self):
        """It should raise an AlertmanagerError if any of the matchers target the instance property."""
        with pytest.raises(alertmanager.AlertmanagerError, match="Matchers cannot target the instance property"):
            self.am_hosts.downtime(self.reason, matchers=({"name": "instance", "value": "host1001", "isRegex": False},))

    def test_add_silence_port_included(self):
        """It should issue a silence with the specific port and not any port in the matcher."""
        self.requests_mock.post("/api/v2/silences", json={"silenceID": "foobar"})
        am_hosts = alertmanager.AlertmanagerHosts(
            ["host1:1234", "host2:5678"], alertmanager_urls=ALERTMANAGER_URLS, dry_run=False
        )
        am_hosts.downtime(self.reason)
        request_json = self.requests_mock.last_request.json()
        assert request_json["matchers"] == [
            {"name": "instance", "value": r"^(host1:1234|host2:5678)$", "isRegex": True},
        ]

    def test_add_silence_duration(self):
        """It should issue a silence with a given duration."""
        self.requests_mock.post("/api/v2/silences", json={"silenceID": "foobar"})
        with mock.patch("spicerack.alertmanager.datetime") as dt_mock:
            dt_mock.now.return_value = datetime(2022, 6, 6, 10, 00, 00, tzinfo=timezone.utc)
            self.am_hosts.downtime(self.reason, duration=timedelta(hours=6))
        request_json = self.requests_mock.last_request.json()
        assert request_json["startsAt"] == "2022-06-06T10:00:00+00:00"
        assert request_json["endsAt"] == "2022-06-06T16:00:00+00:00"

    def test_add_silence_duration_timezone(self):
        """It should issue a silence with a given duration when on a non-UTC timezone."""
        self.requests_mock.post("/api/v2/silences", json={"silenceID": "foobar"})
        with mock.patch("spicerack.alertmanager.datetime") as dt_mock:
            dt_mock.now.return_value = datetime(2022, 6, 6, 12, 00, 00, tzinfo=timezone(timedelta(hours=2)))
            self.am_hosts.downtime(self.reason, duration=timedelta(hours=6))
        request_json = self.requests_mock.last_request.json()
        assert request_json["startsAt"] == "2022-06-06T10:00:00+00:00"
        assert request_json["endsAt"] == "2022-06-06T16:00:00+00:00"

    def test_add_silence_dry_run(self):
        """It should not create a silence because in dry-run mode."""
        self.requests_mock.post("/api/v2/silences", json={"silenceID": "foobar"})
        response = self.am_hosts_dry_run.downtime(self.reason)
        assert response == ""
        assert self.requests_mock.call_count == 0

    def test_verbatim_hosts(self):
        """It should issue silences for verbatim hosts."""
        self.requests_mock.post("/api/v2/silences", json={"silenceID": "foobar"})
        am_hosts = alertmanager.AlertmanagerHosts(
            ["host1.foo.bar", "host2.bar.baz:1234"],
            verbatim_hosts=True,
            alertmanager_urls=ALERTMANAGER_URLS,
            dry_run=False,
        )
        am_hosts.downtime(self.reason)
        request_json = self.requests_mock.last_request.json()
        assert request_json["matchers"] == [
            {
                "name": "instance",
                "value": r"^(host1\.foo\.bar(\..+)?(:[0-9]+)?|host2\.bar\.baz:1234)$",
                "isRegex": True,
            },
        ]

    def test_nodeset_hosts(self):
        """It should expand NodeSet hosts."""
        self.requests_mock.post("/api/v2/silences", json={"silenceID": "foobar"})
        am_hosts = alertmanager.AlertmanagerHosts(
            nodeset("host[1-2]"), verbatim_hosts=True, alertmanager_urls=ALERTMANAGER_URLS, dry_run=False
        )
        am_hosts.downtime(self.reason)
        request_json = self.requests_mock.last_request.json()
        assert request_json["matchers"] == [
            {"name": "instance", "value": r"^(host1|host2)(\..+)?(:[0-9]+)?$", "isRegex": True},
        ]

    def test_empty_target_hosts(self):
        """It should error with empty hosts."""
        with pytest.raises(alertmanager.AlertmanagerError):
            alertmanager.AlertmanagerHosts([""], alertmanager_urls=ALERTMANAGER_URLS)

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
