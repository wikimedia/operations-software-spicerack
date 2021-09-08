"""Debmonitor module tests."""
import pytest
import requests

from spicerack import debmonitor

DEBMONITOR_HOST = "debmonitor.example.com"
HOST1_URL = f"https://{DEBMONITOR_HOST}/hosts/host1.example.com"


class TestDebmonitor:
    """Debmonitor class tests."""

    def setup_method(self):
        """Initialize the test environment for Debmonitor."""
        # pylint: disable=attribute-defined-outside-init
        self.debmonitor = debmonitor.Debmonitor(DEBMONITOR_HOST, "cert.pem", "key.pem", dry_run=False)
        self.debmonitor_dry_run = debmonitor.Debmonitor(DEBMONITOR_HOST, "cert.pem", "key.pem")

    def test_host_delete_ok(self, requests_mock):
        """It should delete the host from Debmonitor."""
        requests_mock.delete(HOST1_URL, status_code=requests.codes["no_content"])
        self.debmonitor.host_delete("host1.example.com")
        assert requests_mock.call_count == 1
        assert requests_mock.request_history[0].method == "DELETE"
        assert requests_mock.request_history[0].url == HOST1_URL

    def test_host_delete_dry_run(self, requests_mock):
        """It should not delete the host from Debmonitor in DRY-RUN."""
        self.debmonitor_dry_run.host_delete("host1.example.com")
        assert not requests_mock.called

    def test_host_delete_not_found(self, requests_mock):
        """It should not raise if the host is already absent in Debmonitor."""
        requests_mock.delete(HOST1_URL, status_code=requests.codes["not_found"])
        self.debmonitor.host_delete("host1.example.com")
        assert requests_mock.call_count == 1

    def test_host_delete_fail(self, requests_mock):
        """It should raise DebmonitorError if failing to delete the host from Debmonitor."""
        requests_mock.delete(HOST1_URL, status_code=requests.codes["bad_request"])
        with pytest.raises(
            debmonitor.DebmonitorError,
            match="Unable to remove host host1.example.com from Debmonitor",
        ):
            self.debmonitor.host_delete("host1.example.com")

        assert requests_mock.call_count == 1
