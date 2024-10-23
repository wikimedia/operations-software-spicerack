"""Orchestrator module tests."""

import re

import pytest
from wmflib.requests import http_session

from spicerack import orchestrator


class TestOrchestrator:
    """Tests for the Orchestrator class."""

    @pytest.fixture(autouse=True)
    def setup_method(self, requests_mock):
        """Initialize the test instance."""
        # pylint: disable=attribute-defined-outside-init
        self.requests_mock = requests_mock
        self.base_url = "https://orchestrator.example.org/api"
        self.endpoint = f"{self.base_url}/endpoint"
        self.http_session = http_session("Orchestrator Tests")
        self.http_session.headers.update({"Accept": "application/json"})
        self.orchestrator = orchestrator.Orchestrator(self.base_url, self.http_session, dry_run=False)

    def test_request_ok(self):
        """It should perform the provided request and return it."""
        self.requests_mock.get(self.endpoint, json={"key": "value"})
        response = self.orchestrator.request("get", "/endpoint")
        assert response.json() == {"key": "value"}
        assert response.status_code == 200

    @pytest.mark.parametrize("details", (None, "Additional details"))
    def test_request_response_wrong_status_code(self, details):
        """It should raise an OrchestratorError if the request returns an error status code parsing the message."""
        response = {"Code": "ERROR", "Message": "Cannot read instance: db.example.org:3307", "Details": details}
        self.requests_mock.get(self.endpoint, json=response, status_code=500)
        expected = "[ERROR] Cannot read instance: db.example.org:3307"
        if details:
            expected += f" {details}"
        with pytest.raises(orchestrator.OrchestratorError, match=re.escape(expected)):
            self.orchestrator.request("get", "/endpoint")

    def test_request_response_wrong_status_code_failed_json(self):
        """It should raise an OrchestratorError if the request fails and it's unable to parse the message."""
        self.requests_mock.get(self.endpoint, text="404 page not found", status_code=404)
        with pytest.raises(orchestrator.OrchestratorError, match="404 page not found"):
            self.orchestrator.request("get", "/endpoint")

    def test_clusters(self):
        """It should return the clusters known to orchestrator with their metadata."""
        response = [{"ClusterAlias": "section1", "other": "info1"}, {"ClusterAlias": "section2", "other": "info2"}]
        self.requests_mock.get(self.base_url + "/clusters-info", json=response)
        clusters = self.orchestrator.clusters()
        assert list(clusters.keys()) == ["section1", "section2"]
        assert clusters["section2"]["other"] == "info2"

    def test_instance_default_port(self):
        """It should return the instance metadata appending the default port."""
        response = {"Key": {"Hostname": "db.example.org", "Port": 3306}, "Uptime": 123456}
        self.requests_mock.get(f"{self.base_url}/instance/db.example.org/3306", json=response)
        instance = self.orchestrator.instance("db.example.org")
        assert instance["Uptime"] == 123456

    def test_instance_custom_port(self):
        """It should return the instance metadata."""
        response = {"Key": {"Hostname": "db.example.org", "Port": 3333}, "Uptime": 123456}
        self.requests_mock.get(f"{self.base_url}/instance/db.example.org/3333", json=response)
        instance = self.orchestrator.instance("db.example.org:3333")
        assert instance["Uptime"] == 123456
