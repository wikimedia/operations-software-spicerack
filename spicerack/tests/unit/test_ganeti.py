"""Ganeti Module test."""

import json
from unittest import mock

import pytest
import requests
from ClusterShell.MsgTree import MsgTreeElem
from cumin import NodeSet

from spicerack.exceptions import SpicerackError
from spicerack.ganeti import CLUSTERS_AND_ROWS, RAPI_URL_FORMAT, Ganeti, GanetiError, GanetiRAPI, GntInstance
from spicerack.remote import Remote
from spicerack.tests import get_fixture_path


class TestGaneti:
    """Ganeti tests class."""

    def setup_method(self):
        """Setup test environment."""
        # pylint: disable=attribute-defined-outside-init
        self.remote = mock.MagicMock(spec_set=Remote)
        self.ganeti = Ganeti(username="user", password="pass", timeout=10, remote=self.remote)  # nosec

        self.cluster = "ganeti01.svc.eqiad.wmnet"
        self.instance = "test.example.com"
        self.cluster_base_url = {
            cluster: RAPI_URL_FORMAT.format(cluster=cluster) + "/2" for cluster in CLUSTERS_AND_ROWS
        }
        self.base_url = self.cluster_base_url[self.cluster]
        self.instance_url = f"{self.base_url}/instances/{self.instance}"

        # load test fixtures
        with open(get_fixture_path("ganeti", "info.json"), encoding="utf-8") as info_json:
            self.info = info_json.read()
        with open(get_fixture_path("ganeti", "404.json"), encoding="utf-8") as fourohfour_json:
            self.fourohfour = fourohfour_json.read()
        with open(get_fixture_path("ganeti", "instance.json"), encoding="utf-8") as instance_json:
            self.instance_info = instance_json.read()
        with open(get_fixture_path("ganeti", "bogus.json"), encoding="utf-8") as bogus_json:
            self.bogus_data = bogus_json.read()

    def _set_requests_mock_for_instance(self, requests_mock, missing_active=False):
        """Set request mock to be 404 on all other clusters."""
        for cluster in CLUSTERS_AND_ROWS:
            if cluster == self.cluster and not missing_active:
                requests_mock.get(self.instance_url, text=self.instance_info)
            else:
                requests_mock.get(
                    f"{self.cluster_base_url[cluster]}/instances/{self.instance}",
                    text=self.fourohfour,
                    status_code=requests.codes["not_found"],
                )

    @pytest.mark.parametrize("cluster", CLUSTERS_AND_ROWS.keys())
    def test_rapi_clusters_ok(self, cluster):
        """Ganeti.rapi() should return a GanetiRAPI object."""
        assert isinstance(self.ganeti.rapi(cluster), GanetiRAPI)

    def test_rapi_clusters_missing(self):
        """If a cluster that doesn't exist is passed to Ganeti.rapi(), it should except with a SpicerackError."""
        with pytest.raises(SpicerackError, match=r"Cannot find cluster bogus cluster \(expected .*"):
            self.ganeti.rapi("bogus cluster")

    def test_rapi_master_ok(self, requests_mock):
        """The master property of a RAPI should be the hostname for the master of this cluster."""
        requests_mock.get(self.base_url + "/info", text=self.info)

        master = json.loads(self.info)["master"]
        rapi = self.ganeti.rapi(self.cluster)
        assert rapi.master == master

    def test_rapi_master_missing(self, requests_mock):
        """If a master is not specified by the uptsream API, the value of master on a RAPI should be None."""
        requests_mock.get(self.base_url + "/info", text=self.bogus_data)
        rapi = self.ganeti.rapi(self.cluster)
        assert rapi.master is None

    def test_rapi_instance_missing(self, requests_mock):
        """A RAPI object should raise a GanetiError if a requested host does not exist."""
        requests_mock.get(
            self.instance_url,
            text=self.fourohfour,
            status_code=requests.codes["not_found"],
        )
        rapi = self.ganeti.rapi(self.cluster)
        with pytest.raises(GanetiError, match=r"Non-200 from API: 404:.*"):
            rapi.fetch_instance(self.instance)

    def test_rapi_instance_request_fail(self, requests_mock):
        """A RAPI object should raise a GanetiError if a request fails."""
        rapi = self.ganeti.rapi(self.cluster)
        requests_mock.get(self.instance_url, exc=requests.exceptions.ConnectTimeout)
        with pytest.raises(GanetiError, match="Error while performing request to RAPI"):
            rapi.fetch_instance(self.instance)

    def test_rapi_instance_invalid(self, requests_mock):
        """If no mac is present in host data, fetch_instance_mac should raise a GanetiError."""
        rapi = self.ganeti.rapi(self.cluster)
        requests_mock.get(self.instance_url, text=self.bogus_data)
        with pytest.raises(GanetiError, match=""):
            rapi.fetch_instance_mac(self.instance)

    def test_rapi_instance_valid(self, requests_mock):
        """The MAC returned by RAPI.fetch_instance_mac should match the data returned by the API."""
        rapi = self.ganeti.rapi(self.cluster)
        requests_mock.get(self.instance_url, text=self.instance_info)
        mac = json.loads(self.instance_info)["nic.macs"][0]
        assert mac == rapi.fetch_instance_mac(self.instance)

    def test_fetch_cluster_for_instance_ok(self, requests_mock):
        """We should get a cluster name that the host exists for."""
        self._set_requests_mock_for_instance(requests_mock)
        assert self.ganeti.fetch_cluster_for_instance(self.instance) == self.cluster

    def test_fetch_cluster_for_instance_missing(self, requests_mock):
        """We should get an exception if the host is not found in Ganeti."""
        self._set_requests_mock_for_instance(requests_mock, missing_active=True)
        with pytest.raises(GanetiError, match="Cannot find test.example.com in any configured cluster."):
            self.ganeti.fetch_cluster_for_instance(self.instance)

    @pytest.mark.parametrize("cluster", ("", "ganeti01.svc.eqiad.wmnet"))
    def test_instance_ok(self, cluster, requests_mock):
        """It should return an instance of GntInstance for a properly configured cluster."""
        self._set_requests_mock_for_instance(requests_mock)
        requests_mock.get(self.base_url + "/info", text=self.info)
        instance = self.ganeti.instance(self.instance, cluster=cluster)
        assert isinstance(instance, GntInstance)
        assert instance.cluster == "ganeti01.svc.eqiad.wmnet"
        self.remote.query.assert_called_once_with("ganeti1.example.com")

    def test_instance_missing_master(self, requests_mock):
        """It should raise a GanetiError exception if unable to determin the instance's master to manage it."""
        self._set_requests_mock_for_instance(requests_mock)
        requests_mock.get(self.base_url + "/info", text=self.bogus_data)
        with pytest.raises(GanetiError, match="Master for cluster ganeti01.svc.eqiad.wmnet is None"):
            self.ganeti.instance(self.instance)

    @pytest.mark.parametrize("kwargs", ({}, {"timeout": 0}))
    def test_instance_shutdown(self, requests_mock, kwargs):
        """It should issue the shutdown command on the master host."""
        self._set_requests_mock_for_instance(requests_mock)
        requests_mock.get(self.base_url + "/info", text=self.info)
        instance = self.ganeti.instance(self.instance)
        instance.shutdown(**kwargs)
        timeout = kwargs["timeout"] if "timeout" in kwargs else 2
        self.remote.query.return_value.run_sync.assert_called_once_with(
            f"gnt-instance shutdown --timeout={timeout} test.example.com"
        )

    @pytest.mark.parametrize("kwargs", ({}, {"shutdown_timeout": 0}))
    def test_instance_remove(self, requests_mock, kwargs):
        """It should issue the remove command on the master host."""
        self._set_requests_mock_for_instance(requests_mock)
        requests_mock.get(self.base_url + "/info", text=self.info)
        instance = self.ganeti.instance(self.instance)
        instance.remove(**kwargs)
        timeout = kwargs["shutdown_timeout"] if "shutdown_timeout" in kwargs else 2
        self.remote.query.return_value.run_sync.assert_called_once_with(
            f"gnt-instance remove --shutdown-timeout={timeout} --force test.example.com"
        )

    def test_instance_add_ok(self, requests_mock):
        """It should issue the remove command on the master host."""
        self._set_requests_mock_for_instance(requests_mock)
        requests_mock.get(self.base_url + "/info", text=self.info)
        instance = self.ganeti.instance(self.instance)
        results = [
            (
                NodeSet("ganeti-master.example.com"),
                MsgTreeElem(b"creation logs", parent=MsgTreeElem()),
            )
        ]
        self.remote.query.return_value.run_sync.return_value = iter(results)

        instance.add(row="A", vcpus=2, memory=3, disk=4, link="private")

        self.remote.query.return_value.run_sync.assert_called_once_with(
            "gnt-instance add -t drbd -I hail --net 0:link=private --hypervisor-parameters=kvm:boot_order=network "
            "-o debootstrap+default --no-install -g row_A -B vcpus=2,memory=3g --disk 0:size=4g test.example.com"
        )

    @pytest.mark.parametrize(
        "kwargs, exc_message",
        (
            (
                {"row": "A", "vcpus": 1, "memory": 1, "disk": 1, "link": "invalid"},
                r"Invalid link 'invalid', expected one of: \('public', 'private', 'analytics'\)",
            ),
            (
                {
                    "row": "invalid",
                    "vcpus": 1,
                    "memory": 1,
                    "disk": 1,
                    "link": "private",
                },
                r"Invalid row 'invalid' for cluster ganeti01.svc.eqiad.wmnet, expected one of: \('A', 'B', 'C', 'D'\)",
            ),
            (
                {"row": "A", "vcpus": -1, "memory": 1, "disk": 1, "link": "private"},
                r"Invalid value '-1' for vcpus, expected positive integer.",
            ),
            (
                {"row": "A", "vcpus": 1, "memory": -1, "disk": 1, "link": "private"},
                r"Invalid value '-1' for memory, expected positive integer.",
            ),
            (
                {"row": "A", "vcpus": 1, "memory": 1, "disk": -1, "link": "private"},
                r"Invalid value '-1' for disk, expected positive integer.",
            ),
        ),
    )
    def test_instance_add_fail(self, requests_mock, kwargs, exc_message):
        """It should raise GanetiError on invalid parameters."""
        self._set_requests_mock_for_instance(requests_mock)
        requests_mock.get(self.base_url + "/info", text=self.info)
        instance = self.ganeti.instance(self.instance)
        with pytest.raises(GanetiError, match=exc_message):
            instance.add(**kwargs)

        assert not self.remote.query.return_value.run_sync.called
