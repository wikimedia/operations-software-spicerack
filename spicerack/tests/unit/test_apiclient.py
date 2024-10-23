"""Apiclient module tests."""

import logging
import re

import pytest
from requests.exceptions import ConnectTimeout
from requests_mock.adapter import ANY
from wmflib.requests import http_session

from spicerack import apiclient


class TestAPIClient:
    """Tests for the APIClient class."""

    @pytest.fixture(autouse=True)
    def setup_method(self, requests_mock):
        """Initialize the test instance."""
        # pylint: disable=attribute-defined-outside-init
        self.requests_mock = requests_mock
        self.base_url = "https://api.example.org/v1"
        self.endpoint = f"{self.base_url}/endpoint"
        self.http_session = http_session("APIClient Tests")
        self.apiclient = apiclient.APIClient(self.base_url, self.http_session, dry_run=False)
        self.apiclient_dry_run = apiclient.APIClient(self.base_url, self.http_session)

    def test_http_session(self):
        """It should return the current HTTP session object to allow the user to fine-tune it."""
        assert self.apiclient.http_session is self.http_session
        self.apiclient.http_session.headers.update({"Accept": "application/json"})
        self.requests_mock.get(self.endpoint, json={"key": "value"})
        response = self.apiclient.request("get", "/endpoint")
        assert response.request.headers["Accept"] == "application/json"

    @pytest.mark.parametrize("method", ("get", "head", "options"))
    def test_request_dry_run_ro(self, method):
        """It should perform any RO request and return the actual response also in dry_run mode."""
        kwargs = {}
        if method == "get":
            kwargs["json"] = {"key": "value"}

        self.requests_mock.request(method, self.endpoint, **kwargs)
        response = self.apiclient_dry_run.request(method, "/endpoint")
        assert response.status_code == 200
        if method == "get":
            assert response.json() == {"key": "value"}

    @pytest.mark.parametrize("method", ("connect", "delete", "patch", "post", "put", "trace"))
    def test_request_dry_run_rw(self, method):
        """It should not perform any RW request and return a dummy successful response in dry-run mode."""
        self.requests_mock.request(ANY, ANY, status_code=500)
        response = self.apiclient_dry_run.request(method, "/endpoint")
        assert response.status_code == 200
        assert not response.text

    def test_request_dry_run_fail(self, caplog):
        """If the request fails in dry-run mode, it should return a dummy successful response."""
        self.requests_mock.get(self.endpoint, exc=ConnectTimeout)
        with caplog.at_level(logging.ERROR):
            response = self.apiclient_dry_run.request("get", "/endpoint")

        assert response.status_code == 200
        assert f"Failed to perform GET request to {self.endpoint}" in caplog.text

    def test_request_ok(self):
        """It should perform the provided request and return it."""
        self.requests_mock.get(self.endpoint, json={"key": "value"})
        response = self.apiclient.request("get", "/endpoint")
        assert response.json() == {"key": "value"}
        assert response.status_code == 200

    def test_request_response_wrong_status_code(self):
        """It should raise an APIClientResponseError if the request returns an error status code."""
        self.requests_mock.post(self.endpoint, json={"error_code": "01", "message": "error"}, status_code=405)
        with pytest.raises(
            apiclient.APIClientResponseError, match=re.escape(f"POST {self.endpoint} returned HTTP 405")
        ) as e:
            self.apiclient.request("post", "/endpoint", json={"key": "value"})
            assert e.response.status_code == 405
            assert e.response.json()["error_code"] == "01"

    def test_request_response_raises(self):
        """It should raise an APIClientError if the request failes to be performed."""
        self.requests_mock.get(self.endpoint, exc=ConnectTimeout)
        with pytest.raises(
            apiclient.APIClientError, match=re.escape(f"Failed to perform GET request to {self.endpoint}")
        ):
            self.apiclient.request("get", "/endpoint")

    def test_request_invalid_uri(self):
        """It should raise an TestAPIClient if the URI is invalid."""
        with pytest.raises(apiclient.APIClientError, match=re.escape("Invalid uri 'endpoint', it must start with a /")):
            self.apiclient.request("get", "endpoint")
