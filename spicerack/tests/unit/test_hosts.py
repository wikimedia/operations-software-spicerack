"""Hosts module tests."""

import re
from unittest import mock

import pytest

from spicerack import Spicerack, hosts
from spicerack.alerting import AlertingHosts
from spicerack.alertmanager import AlertmanagerHosts
from spicerack.apt import AptGetHosts
from spicerack.exceptions import SpicerackError
from spicerack.icinga import IcingaHosts
from spicerack.ipmi import Ipmi
from spicerack.mysql import MysqlRemoteHosts
from spicerack.netbox import NetboxServer
from spicerack.puppet import PuppetHosts
from spicerack.redfish import Redfish
from spicerack.remote import RemoteHosts
from spicerack.tests import SPICERACK_TEST_PARAMS


class TestHost:
    """Test class for the Host class."""

    def _setup(self, name, monkeypatch, netbox_host):
        """Initiliaze the fixtures."""
        monkeypatch.setenv("SUDO_USER", "user1")
        monkeypatch.setenv("MGMT_PASSWORD", "env_password")
        proxy = "http://proxy.example.com:8080"
        self.mocked_pynetbox.return_value.dcim.devices.get.return_value = netbox_host
        mgmt_address = mock.MagicMock()
        mgmt_address.address = "10.0.0.1/16"
        mgmt_address.dns_name = f"{name}.mgmt.example.com"
        self.mocked_pynetbox.return_value.ipam.ip_addresses.get.return_value = mgmt_address
        return Spicerack(verbose=True, dry_run=False, http_proxy=proxy, **SPICERACK_TEST_PARAMS)

    def setup_method(self):
        """Initialize the test for each method."""
        # pylint: disable=attribute-defined-outside-init
        self.mocked_pynetbox = mock.patch("pynetbox.api").start()

    def teardown_method(self):
        """Cleanup any leftover patching."""
        self.mocked_pynetbox.stop()

    def test_host_from_remote_ok(self, monkeypatch, netbox_host):
        """It should return a Host instance from a RemoteHosts instance with just one host."""
        spicerack = self._setup("physical", monkeypatch, netbox_host)
        remote = spicerack.remote().query("D{physical.example.com}")
        host = hosts.Host.from_remote(remote, spicerack)
        assert isinstance(host, hosts.Host)
        assert host.hostname == "physical"

    def test_host_from_remote_fail(self, monkeypatch, netbox_host):
        """It should raise a HostError exception if the remote instance has multiple hosts."""
        spicerack = self._setup("physical", monkeypatch, netbox_host)
        remote = spicerack.remote().query("D{host[1-5].example.com}")
        with pytest.raises(
            hosts.HostError,
            match=re.escape(
                "Unable to create Host instance from RemoteHosts host[1-5].example.com, expected 1 host, got 5."
            ),
        ):
            hosts.Host.from_remote(remote, spicerack)

    def test_accessors_physical(self, monkeypatch, netbox_host):
        """An Host instance for a physical server should allow to access library features for a specific host."""
        name = "physical"
        spicerack = self._setup(name, monkeypatch, netbox_host)
        host = hosts.Host(name, spicerack)
        assert host.hostname == name
        assert host.fqdn == f"{name}.example.com"
        assert host.mgmt_fqdn == f"{name}.mgmt.example.com"
        assert isinstance(host.remote(), RemoteHosts)
        assert str(host.remote()) == f"{name}.example.com"
        assert isinstance(host.netbox(), NetboxServer)
        assert isinstance(host.puppet(), PuppetHosts)
        assert isinstance(host.mysql(), MysqlRemoteHosts)
        assert isinstance(host.apt_get(), AptGetHosts)
        assert isinstance(host.alertmanager(), AlertmanagerHosts)
        assert isinstance(host.redfish(), Redfish)
        assert isinstance(host.ipmi(), Ipmi)

    def test_accessors_virtual(self, monkeypatch, netbox_virtual_machine):
        """An Host instance for a virtual machine should allow to access library features for a specific host."""
        name = "virtual"
        spicerack = self._setup(name, monkeypatch, netbox_virtual_machine)
        host = hosts.Host(name, spicerack)
        assert host.hostname == name
        assert host.fqdn == f"{name}.example.com"
        assert isinstance(host.remote(), RemoteHosts)
        assert str(host.remote()) == f"{name}.example.com"
        assert isinstance(host.netbox(), NetboxServer)
        assert isinstance(host.puppet(), PuppetHosts)
        assert isinstance(host.mysql(), MysqlRemoteHosts)
        assert isinstance(host.apt_get(), AptGetHosts)
        assert isinstance(host.alertmanager(), AlertmanagerHosts)
        # No mgmt_fqdn, ipmi or redfish, they should raise an exception

    @mock.patch("spicerack.Dns", autospec=True)
    @mock.patch("spicerack.remote.Remote.query", autospec=True)
    @mock.patch("spicerack.icinga.CommandFile", autospec=True)
    def test_alerting_icinga(self, mocked_command_file, mocked_remote_query, mocked_dns, monkeypatch, netbox_host):
        """When accessing the alerting or icinga accessors should return an instance of the respecive classes."""
        spicerack = self._setup("physical", monkeypatch, netbox_host)
        host = hosts.Host("physical", spicerack)
        mocked_command_file.return_value = "/var/lib/icinga/rw/icinga.cmd"
        icinga_server = mock.MagicMock(spec_set=RemoteHosts)
        icinga_server.hosts = "icinga-server.example.com"
        icinga_server.__len__.return_value = 1
        mocked_remote_query.return_value = icinga_server
        mocked_dns.return_value.resolve_cname.return_value = "icinga-server.example.com"
        assert isinstance(host.alerting(), AlertingHosts)
        assert isinstance(host.icinga(), IcingaHosts)

    def test_init_not_found(self, monkeypatch, netbox_host):
        """It should raise HostError if unable to find the host in Netbox."""
        spicerack = self._setup("nonexistent", monkeypatch, netbox_host)
        self.mocked_pynetbox.return_value.dcim.devices.get.return_value = None
        self.mocked_pynetbox.return_value.virtualization.virtual_machines.get.return_value = None

        with pytest.raises(hosts.HostError, match="Unable to find host nonexistent in Netbox"):
            hosts.Host("nonexistent", spicerack)

    @pytest.mark.parametrize(
        "attribute, error",
        (
            ("mgmt_fqdn", "Server virtual is a virtual machine, does not have a management address."),
            ("redfish", "Host virtual is not a Physical server, Redfish is not supported."),
            ("ipmi", "Host 'virtual' is a Virtual Machine, IPMI not supported."),
        ),
    )
    def test_ipmi_redfish_virtual(self, attribute, error, monkeypatch, netbox_virtual_machine):
        """For virtual machines accessing ipmi or redfish should raise an exception."""
        spicerack = self._setup("virtual", monkeypatch, netbox_virtual_machine)
        host = hosts.Host("virtual", spicerack)

        with pytest.raises(SpicerackError, match=re.escape(error)):
            attr = getattr(host, attribute)
            if callable(attr):
                attr()
