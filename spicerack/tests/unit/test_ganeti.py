"""Ganeti Module test."""

import json
from unittest import mock

import pytest
import requests
from ClusterShell.MsgTree import MsgTreeElem
from cumin import NodeSet

from spicerack import ganeti
from spicerack.netbox import Netbox
from spicerack.remote import Remote
from spicerack.tests import get_fixture_path

TEST_CLUSTERS = {
    "sitea": "ganeti01.svc.sitea.example.com",
    "siteb01": "ganeti01.svc.siteb.example.com",
    "siteb02": "ganeti02.svc.siteb.example.com",
    "sitea_test": "ganeti-test01.svc.sitea.example.com",
}


class TestGaneti:
    """Ganeti tests class."""

    def setup_method(self):
        """Setup test environment."""
        # pylint: disable=attribute-defined-outside-init
        self.remote = mock.MagicMock(spec_set=Remote)
        self.netbox = mock.MagicMock(spec_set=Netbox)
        self.ganeti = ganeti.Ganeti(
            username="user", password="pass", timeout=10, remote=self.remote, netbox=self.netbox
        )

        self.cluster = "sitea"
        self.instance = "test.example.com"
        self.cluster_base_urls = {
            cluster: ganeti.RAPI_URL_FORMAT.format(cluster=url) + "/2" for cluster, url in TEST_CLUSTERS.items()
        }
        self.base_url = self.cluster_base_urls[self.cluster]
        self.instance_url = f"{self.base_url}/instances/{self.instance}"

        # Populate mock with default values
        self.netbox.api.virtualization.cluster_groups.get.return_value.custom_fields = {
            "ip_address": {"address": "10.0.0.1/24"}
        }
        self.netbox.api.ipam.ip_addresses.get.return_value.dns_name = TEST_CLUSTERS[self.cluster]
        self.netbox.api.virtualization.virtual_machines.get.return_value.cluster.group.name = self.cluster
        self.netbox.api.virtualization.clusters.get.return_value.site.slug = self.cluster

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
        for cluster in TEST_CLUSTERS:
            if cluster == self.cluster and not missing_active:
                requests_mock.get(self.instance_url, text=self.instance_info)
            else:
                requests_mock.get(
                    f"{self.cluster_base_urls[cluster]}/instances/{self.instance}",
                    text=self.fourohfour,
                    status_code=requests.codes["not_found"],
                )

    @pytest.mark.parametrize("cluster", TEST_CLUSTERS)
    def test_rapi_clusters_ok(self, cluster):
        """Ganeti.rapi() should return a GanetiRAPI object."""
        self.netbox.api.virtualization.cluster_groups.get.return_value.custom_fields = {
            "ip_address": {"address": "10.0.0.1/24"}
        }
        self.netbox.api.ipam.ip_addresses.get.return_value.dns_name = TEST_CLUSTERS[cluster]
        assert isinstance(self.ganeti.rapi(cluster), ganeti.GanetiRAPI)

    def test_rapi_clusters_missing_cluster(self):
        """If unable to find the cluster in Netbox it should raise a GanetiError."""
        self.netbox.api.virtualization.cluster_groups.get.return_value = None
        with pytest.raises(ganeti.GanetiError, match="Unable to find virtualization cluster group invalid on Netbox"):
            self.ganeti.rapi("invalid")

    def test_rapi_clusters_no_ip_address(self):
        """If the cluster has no IP address in Netbox it should raise a GanetiError."""
        self.netbox.api.virtualization.cluster_groups.get.return_value.custom_fields = {"ip_addresses": None}
        with pytest.raises(ganeti.GanetiError, match="Virtualization cluster group sitea has no IP address"):
            self.ganeti.rapi("sitea")

    @pytest.mark.parametrize(
        "address",
        (
            {"ip_address": {}},
            {"ip_address": {"address": None}},
            {"ip_address": {"address": ""}},
        ),
    )
    def test_rapi_clusters_no_address(self, address):
        """If the cluster IP address has no address in Netbox it should raise a GanetiError."""
        self.netbox.api.virtualization.cluster_groups.get.return_value.custom_fields = address
        with pytest.raises(ganeti.GanetiError, match="Virtualization cluster group sitea IP address has no address"):
            self.ganeti.rapi("sitea")

    def test_rapi_clusters_address_not_found(self):
        """If the IP address of the cluster group cannot be found in Netbox it should raise a GanetiError."""
        self.netbox.api.virtualization.cluster_groups.get.return_value.custom_fields = {
            "ip_address": {"address": "10.0.0.1/24"}
        }
        self.netbox.api.ipam.ip_addresses.get.return_value = None
        with pytest.raises(
            ganeti.GanetiError, match="Unable to find the IP address for the virtualization cluster group sitea"
        ):
            self.ganeti.rapi("sitea")

    @pytest.mark.parametrize("dns_name", (None, ""))
    def test_rapi_clusters_address_no_dns_name(self, dns_name):
        """If the IP address of the cluster group doesn't have a DNS name it should raise a GanetiError."""
        self.netbox.api.virtualization.cluster_groups.get.return_value.custom_fields = {
            "ip_address": {"address": "10.0.0.1/24"}
        }
        self.netbox.api.ipam.ip_addresses.get.return_value.dns_name = dns_name
        with pytest.raises(
            ganeti.GanetiError, match="Virtualization cluster group sitea's IP address 10.0.0.1/24 has no DNS name"
        ):
            self.ganeti.rapi("sitea")

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
        with pytest.raises(ganeti.GanetiError, match=r"Non-200 from API: 404:.*"):
            rapi.fetch_instance(self.instance)

    def test_rapi_instance_request_fail(self, requests_mock):
        """A RAPI object should raise a GanetiError if a request fails."""
        rapi = self.ganeti.rapi(self.cluster)
        requests_mock.get(self.instance_url, exc=requests.exceptions.ConnectTimeout)
        with pytest.raises(ganeti.GanetiError, match="Error while performing request to RAPI"):
            rapi.fetch_instance(self.instance)

    def test_rapi_instance_invalid(self, requests_mock):
        """If no mac is present in host data, fetch_instance_mac should raise a GanetiError."""
        rapi = self.ganeti.rapi(self.cluster)
        requests_mock.get(self.instance_url, text=self.bogus_data)
        with pytest.raises(ganeti.GanetiError, match=""):
            rapi.fetch_instance_mac(self.instance)

    def test_rapi_instance_valid(self, requests_mock):
        """The MAC returned by RAPI.fetch_instance_mac should match the data returned by the API."""
        rapi = self.ganeti.rapi(self.cluster)
        requests_mock.get(self.instance_url, text=self.instance_info)
        mac = json.loads(self.instance_info)["nic.macs"][0]
        assert mac == rapi.fetch_instance_mac(self.instance)

    @pytest.mark.parametrize("cluster", ("", "sitea"))
    def test_instance_ok(self, cluster, requests_mock):
        """It should return an instance of GntInstance for a properly configured cluster."""
        self._set_requests_mock_for_instance(requests_mock)
        requests_mock.get(self.base_url + "/info", text=self.info)
        instance = self.ganeti.instance(self.instance, cluster=cluster)
        assert isinstance(instance, ganeti.GntInstance)
        assert instance.cluster == "sitea"
        self.remote.query.assert_called_once_with("ganeti1.example.com")

    def test_instance_missing_vm_no_cluster(self):
        """It should raise a GanetiError if the VM does not exist in Netbox and no cluster is provided."""
        self.netbox.api.virtualization.virtual_machines.get.return_value = None
        with pytest.raises(
            ganeti.GanetiError, match="Ganeti Virtual Machine test.example.com does not exist on Netbox and"
        ):
            self.ganeti.instance(self.instance)

        self.remote.query.assert_not_called()

    def test_instance_missing_master(self, requests_mock):
        """It should raise a GanetiError exception if unable to determin the instance's master to manage it."""
        self._set_requests_mock_for_instance(requests_mock)
        requests_mock.get(self.base_url + "/info", text=self.bogus_data)
        with pytest.raises(ganeti.GanetiError, match="Master for cluster sitea is None"):
            self.ganeti.instance(self.instance)

    def test_instance_startup(self, requests_mock):
        """It should issue the startup command on the master host."""
        self._set_requests_mock_for_instance(requests_mock)
        requests_mock.get(self.base_url + "/info", text=self.info)
        instance = self.ganeti.instance(self.instance)
        instance.startup()
        self.remote.query.return_value.run_sync.assert_called_once_with("gnt-instance startup --force test.example.com")

    def test_instance_set_boot_media(self, requests_mock):
        """It should set the boot media to the one provided."""
        self._set_requests_mock_for_instance(requests_mock)
        requests_mock.get(self.base_url + "/info", text=self.info)
        instance = self.ganeti.instance(self.instance)
        instance.set_boot_media("disk")
        self.remote.query.return_value.run_sync.assert_called_once_with(
            "gnt-instance modify --hypervisor-parameters=boot_order=disk test.example.com"
        )

    @pytest.mark.parametrize("kwargs", ({}, {"timeout": 0}))
    def test_instance_shutdown(self, requests_mock, kwargs):
        """It should issue the shutdown command on the master host."""
        self._set_requests_mock_for_instance(requests_mock)
        requests_mock.get(self.base_url + "/info", text=self.info)
        instance = self.ganeti.instance(self.instance)
        instance.shutdown(**kwargs)
        timeout = kwargs["timeout"] if "timeout" in kwargs else 2
        self.remote.query.return_value.run_sync.assert_called_once_with(
            f"gnt-instance shutdown --force --timeout={timeout} test.example.com"
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

        instance.add(group="row_A", vcpus=2, memory=3, disk=4, link="private")

        self.remote.query.return_value.run_sync.assert_called_once_with(
            "gnt-instance add -t drbd -I hail --net 0:link=private --hypervisor-parameters=kvm:boot_order=network "
            "-o debootstrap+default --no-install -g row_A -B vcpus=2,memory=3g --disk 0:size=4g test.example.com",
            print_output=True,
        )

    @pytest.mark.parametrize(
        "kwargs, exc_message",
        (
            (
                {"group": "row_A", "vcpus": 1, "memory": 1, "disk": 1, "link": "invalid"},
                r"Invalid link 'invalid', expected one of: \('public', 'private', 'analytics'\)",
            ),
            (
                {"group": "row_A", "vcpus": -1, "memory": 1, "disk": 1, "link": "private"},
                r"Invalid value '-1' for vcpus, expected positive integer.",
            ),
            (
                {"group": "row_A", "vcpus": 1, "memory": -1, "disk": 1, "link": "private"},
                r"Invalid value '-1' for memory, expected positive integer.",
            ),
            (
                {"group": "row_A", "vcpus": 1, "memory": 1, "disk": -1, "link": "private"},
                r"Invalid value '-1' for disk, expected positive integer.",
            ),
        ),
    )
    def test_instance_add_fail(self, requests_mock, kwargs, exc_message):
        """It should raise GanetiError on invalid parameters."""
        self._set_requests_mock_for_instance(requests_mock)
        requests_mock.get(self.base_url + "/info", text=self.info)
        instance = self.ganeti.instance(self.instance)
        with pytest.raises(ganeti.GanetiError, match=exc_message):
            instance.add(**kwargs)

        assert not self.remote.query.return_value.run_sync.called

    def test_get_group_ok(self):
        """It should return a GanetiGroup instance."""
        group = self.ganeti.get_group("group1", cluster=self.cluster)
        assert isinstance(group, ganeti.GanetiGroup)
        assert isinstance(group.cluster, ganeti.GanetiCluster)
        assert group.name == "group1"
        assert group.site == self.cluster
        assert group.cluster.name == self.cluster
        assert group.cluster.fqdn == TEST_CLUSTERS[self.cluster]
        assert group.cluster.rapi == f"https://{TEST_CLUSTERS[self.cluster]}:5080"

    def test_get_group_fail(self):
        """It should raise a GanetiError if the group doesn't exists."""
        self.netbox.api.virtualization.clusters.get.return_value = None
        with pytest.raises(
            ganeti.GanetiError, match="Unable to find virtualization cluster group1 in cluster group sitea on Netbox"
        ):
            self.ganeti.get_group("group1", cluster=self.cluster)
