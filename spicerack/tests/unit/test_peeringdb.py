"""Peeringdb module tests."""

import json
from unittest import mock

import pytest
import requests

from spicerack import peeringdb
from spicerack.tests import get_fixture_path


def test_pdb_proxies():
    """Test thet the proxies are set correctly."""
    proxies = {"http": "http://proxy:8080"}
    pdb = peeringdb.PeeringDB(proxies=proxies)
    assert pdb.session.proxies == proxies


class TestPeeringdb:
    """Tests for the Peeringdb class."""

    @pytest.fixture(autouse=True)
    def setup_method(self, tmp_path):
        """Setup test environment."""
        # pylint: disable=attribute-defined-outside-init
        self.base_url = peeringdb.PeeringDB.baseurl
        self.pdb = peeringdb.PeeringDB(token="foo")
        self.pdb_cached = peeringdb.PeeringDB(token="foo", cachedir=tmp_path / "cache")
        self.pdb_cached_low_ttl = peeringdb.PeeringDB(token="foo", cachedir=tmp_path / "cache", ttl=1)
        # load test fixtures
        self.asn = json.loads(get_fixture_path("peeringdb", "asn.json").read_text())
        self.ixlan = json.loads(get_fixture_path("peeringdb", "ixlan.json").read_text())

    def test_pdb_fetch_net(self, requests_mock):
        """Test fetching net resource."""
        requests_mock.get(f"{self.base_url}net/1", json=self.asn)
        assert self.pdb_cached.fetch("net", 1) == self.asn["data"]
        # Trigger the caching
        assert self.pdb_cached.fetch("net", 1) == self.asn["data"]
        # Ensure we only made one request
        assert len(requests_mock.request_history) == 1

    def test_pdb_fetch_asn_cache(self, requests_mock):
        """PeringDB.fetch() should return a dict."""
        requests_mock.get(f"{self.base_url}net", json=self.asn)
        assert self.pdb_cached.fetch_asn(14907) == self.asn["data"]
        # Trigger the caching
        assert self.pdb_cached.fetch_asn(14907) == self.asn["data"]
        assert len(requests_mock.request_history) == 1

    def test_pdb_fetch_asn_no_cache(self, requests_mock):
        """PeringDB.fetch() should return a dict."""
        requests_mock.get(f"{self.base_url}net", json=self.asn)
        assert self.pdb.fetch_asn(14907) == self.asn["data"]
        assert self.pdb.fetch_asn(14907) == self.asn["data"]
        assert len(requests_mock.request_history) == 2

    def test_pdb_fetch_no_resource_id_no_cache(self, requests_mock):
        """PeringDB.fetch() should return a dict."""
        requests_mock.get(self.base_url + "ixlan", json=self.ixlan)
        assert self.pdb.fetch("ixlan") == self.ixlan["data"]
        assert self.pdb.fetch("ixlan") == self.ixlan["data"]
        assert len(requests_mock.request_history) == 2

    def test_pdb_fetch_no_resource_id_cache(self, requests_mock):
        """PeringDB.fetch() should return a dict."""
        # Trigger the caching
        requests_mock.get(self.base_url + "ixlan", json=self.ixlan)
        assert self.pdb_cached.fetch("ixlan") == self.ixlan["data"]
        assert self.pdb_cached.fetch("ixlan") == self.ixlan["data"]
        assert len(requests_mock.request_history) == 1

    @mock.patch("spicerack.peeringdb.time.time")
    def test_pdb_fetch_cache_age(self, mock_time, requests_mock):
        """PeringDB.fetch() should return a dict."""
        mock_time.return_value = 2147483647  # epoch end date ensures the cache is expired
        requests_mock.get(self.base_url + "ixlan", json=self.ixlan)
        assert self.pdb_cached_low_ttl.fetch("ixlan") == self.ixlan["data"]
        assert self.pdb_cached_low_ttl.fetch("ixlan") == self.ixlan["data"]
        assert len(requests_mock.request_history) == 2

    def test_pdb_fetch_not_found(self, requests_mock):
        """PeringDB.fetch() should return a dict."""
        pdb = peeringdb.PeeringDB()
        requests_mock.get(self.base_url + "ixlan", text="", status_code=requests.codes["not_found"])

        with pytest.raises(peeringdb.PeeringDBError, match=r"Server response with status.*"):
            pdb.fetch("ixlan")
        assert len(requests_mock.request_history) == 1

    def test_pdb_cache_key(self):
        """Peeringdb get_cache_key should return the correct key."""
        # pylint: disable=protected-access
        # useful to test this function even though its private
        assert self.pdb._get_cache_key("net") == "net/index"
        assert self.pdb._get_cache_key("net", resource_id=1) == "net/1"
        assert self.pdb._get_cache_key("net", filters={"asn": 42, "depth": 2}) == "net/asn/42/depth/2"
        assert self.pdb._get_cache_key("net", resource_id=1, filters={"asn": 42, "depth": 2}) == "net/1/asn/42/depth/2"
