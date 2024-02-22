"""Netbox module tests."""

from ipaddress import IPv4Interface, IPv6Interface
from unittest import mock

import pynetbox
import pytest
import requests

from spicerack.netbox import (
    Netbox,
    NetboxAPIError,
    NetboxError,
    NetboxHostNotFoundError,
    NetboxScriptError,
    NetboxServer,
)

NETBOX_URL = "https://example.com/"
NETBOX_TOKEN = "secret_token"
SCRIPT_URL = f"{NETBOX_URL}api/script/"


def _request_error():
    """Return a Netbox RequestError."""
    fakestatus = mock.Mock()
    fakestatus.status_code = 404
    return pynetbox.RequestError(fakestatus)


def _base_netbox_host(name):
    host = mock.MagicMock()
    del host.keys  # Allow to call dict() on this object
    host.name = name
    host.__str__.return_value = name
    host.asset_tag = "ASSET1234"
    host.status.__str__.return_value = "Active"
    host.status.value = "active"
    host.serialize.return_value = {"name": name}
    host.save.return_value = True
    host.primary_ip4.dns_name = f"{name}.example.com"
    host.primary_ip4.address = "10.0.0.1/22"
    host.primary_ip6.dns_name = f"{name}.example.com"
    host.primary_ip6.address = "2620:0:861:103:10::1/64"
    host.primary_ip.assigned_object.connected_endpoint.untagged_vlan.name = "test_vlan"

    dict_repr = {
        "name": name,
        "asset_tag": "ASSET1234",
        "status": {"value": host.status.value, "label": str(host.status)},
        "role": {"id": 1, "name": host.role.name, "slug": host.role.slug},
        "primary_ip4": {
            "id": 1,
            "family": 4,
            "address": "10.0.0.1/22",
            "dns_name": host.primary_ip4.dns_name,
        },
        "primary_ip6": {
            "id": 1,
            "family": 6,
            "address": "2620:0:861:103:10::1/64",
            "dns_name": host.primary_ip6.dns_name,
        },
        "cluster": host.cluster,
    }

    return host, dict_repr


@pytest.fixture(name="netbox_host")
def _netbox_host():
    """Return a mocked Netbox physical device."""
    host, dict_repr = _base_netbox_host("physical")
    host.cluster = None  # A physical server does not belong to a VM cluster
    host.device_role.slug = "server"
    host.device_role.name = "Server"
    dict_repr["cluster"] = None
    host.__iter__.return_value = dict_repr.items()
    return host


@pytest.fixture(name="netbox_virtual_machine")
def _netbox_virtual_machine():
    """Return a mocked Netbox virtual machine."""
    host, dict_repr = _base_netbox_host("virtual")
    host.cluster.name = "testcluster"
    host.role.slug = "server"
    host.role.name = "Server"
    dict_repr["cluster"] = {"id": 1, "name": host.cluster.name}
    del host.rack  # A virtual machine doesn't have a rack property
    host.__iter__.return_value = dict_repr.items()

    return host


class TestNetbox:
    """Tests for the Netbox class."""

    @mock.patch("pynetbox.api")
    def setup_method(self, _, mocked_api):
        """Initialize the test instance."""
        # pylint: disable=attribute-defined-outside-init
        self.mocked_api = mocked_api
        self.netbox = Netbox(NETBOX_URL, NETBOX_TOKEN, dry_run=False)
        self.netbox_dry_run = Netbox(NETBOX_URL, NETBOX_TOKEN, dry_run=True)

    def test_netbox_api(self):
        """An instance of Netbox should instantiate the Netbox API and expose it via the api property."""
        self.mocked_api.called_once_with(NETBOX_URL, token=NETBOX_TOKEN)
        assert self.netbox.api == self.mocked_api()

    def test_get_server_fail_device(self):
        """It should raise a NetboxAPIError if unable to get the device data from Netbox."""
        self.mocked_api().dcim.devices.get.side_effect = _request_error()
        with pytest.raises(NetboxAPIError, match="Error retrieving Netbox device"):
            self.netbox.get_server("physical")

    def test_get_server_fail_vm(self):
        """It should raise a NetboxAPIError if unable to get the VM data from Netbox."""
        self.mocked_api().dcim.devices.get.return_value = None
        self.mocked_api().virtualization.virtual_machines.get.side_effect = _request_error()
        with pytest.raises(NetboxAPIError, match="Error retrieving Netbox VM"):
            self.netbox_dry_run.get_server("virtual")

    def test_get_server_physical(self, netbox_host):
        """It should return the NetboxServer instance of a physical server."""
        self.mocked_api().dcim.devices.get.return_value = netbox_host
        self.mocked_api().virtualization.virtual_machines.get.return_value = None
        assert isinstance(self.netbox.get_server("physical"), NetboxServer)

    def test_get_server_virtual(self, netbox_virtual_machine):
        """It should return the NetboxServer instance of a virtual machine."""
        self.mocked_api().dcim.devices.get.return_value = None
        self.mocked_api().virtualization.virtual_machines.get.return_value = netbox_virtual_machine
        assert isinstance(self.netbox.get_server("virtual"), NetboxServer)

    def test_get_server_not_found(self):
        """It should raise a NetboxHostNotFoundError if unable to find the host in devices or VMs."""
        self.mocked_api().dcim.devices.get.return_value = None
        self.mocked_api().virtualization.virtual_machines.get.return_value = None
        with pytest.raises(NetboxHostNotFoundError):
            self.netbox.get_server("inexistent")

    def test_run_script_ok(self, requests_mock):
        """It should returns the script logs exposed by the server."""
        data = {"data": {"log": ["log1", "log2"]}}
        self.mocked_api().extras.scripts.get.return_value.url = SCRIPT_URL
        requests_mock.post(SCRIPT_URL, json={"result": {"url": SCRIPT_URL}})
        requests_mock.get(SCRIPT_URL, json=data)
        run_script = self.netbox_dry_run.run_script(name="test_script", commit=True, params={})
        assert run_script == ["log1", "log2"]
        assert requests_mock.request_history[0].json() == {"commit": 0, "data": {}}

    @mock.patch("wmflib.decorators.time.sleep", return_value=None)
    def test_run_script_no_result_data(self, mocked_sleep, requests_mock):
        """It should raise a Netbox script error if can't get the script output."""
        self.mocked_api().extras.scripts.get.return_value.url = SCRIPT_URL
        requests_mock.post(SCRIPT_URL, json={"result": {"url": SCRIPT_URL}})
        requests_mock.get(SCRIPT_URL, json={"data": None})
        with pytest.raises(NetboxScriptError, match="Failed to get Netbox script results from "):
            self.netbox.run_script(name="test_script", commit=True, params={})
        assert mocked_sleep.called

    def test_run_script_post_timeout(self, requests_mock):
        """It should raise a Netbox script error if can't start the script."""
        self.mocked_api().extras.scripts.get.return_value.url = SCRIPT_URL
        requests_mock.post(SCRIPT_URL, exc=requests.exceptions.HTTPError)
        with pytest.raises(NetboxScriptError, match="Failed to start Netbox script test_script"):
            self.netbox.run_script(name="test_script", commit=True, params={})


class TestNetboxServer:
    """Test class for the NetboxServer class."""

    @mock.patch("pynetbox.api")
    def setup_method(self, _, mocked_api):
        """Instantiate the test instance mock."""
        # pylint: disable=attribute-defined-outside-init
        self.mocked_api = mocked_api
        self.mgmt_ip = mock.Mock()
        self.mgmt_ip.dns_name = "physical.mgmt.local"
        self.mocked_api.ipam.ip_addresses.get.return_value = self.mgmt_ip

    @pytest.fixture(autouse=True)
    def setup_method_fixture(self, netbox_host, netbox_virtual_machine):
        """Instantiate the test instance with fixtures."""
        # pylint: disable=attribute-defined-outside-init
        self.netbox_host = netbox_host
        self.netbox_virtual_machine = netbox_virtual_machine
        self.physical_server = NetboxServer(api=self.mocked_api, server=self.netbox_host, dry_run=False)
        self.virtual_server = NetboxServer(api=self.mocked_api, server=self.netbox_virtual_machine, dry_run=False)

    def test_init_not_a_server(self):
        """It should raise a NetboxError if the device doesn't have a server role."""
        self.netbox_host.device_role.slug = "not-server"
        with pytest.raises(NetboxError, match="has invalid role not-server"):
            NetboxServer(api=self.mocked_api, server=self.netbox_host)

    def test_virtual_getter(self):
        """It should return a boolean if the device is a virtual machine or a physical host."""
        assert not self.physical_server.virtual
        assert self.virtual_server.virtual

    def test_status_getter(self):
        """It should return the value of the current status of the server, as a string."""
        assert isinstance(self.physical_server.status, str)
        assert self.physical_server.status == "active"

    def test_status_setter_ok(self):
        """It should set the status of the server to its new value, if it's an allowed transition."""
        self.physical_server.status = "failed"
        assert self.netbox_host.save.called_once_with()

    def test_status_setter_virtual(self):
        """It should raise a NetboxError if trying to set the status on a virtual machine."""
        with pytest.raises(
            NetboxError,
            match="Server virtual is a virtual machine, its Netbox status is automatically synced from Ganeti",
        ):
            self.virtual_server.status = "failed"

    def test_status_setter_invalid_transition(self):
        """It should raise a NetboxError if trying to make an invalid status transition."""
        with pytest.raises(
            NetboxError, match="Forbidden Netbox status transition between active and planned for device physical"
        ):
            self.physical_server.status = "planned"

    def test_status_setter_dry_run(self):
        """It should skip setting the status of the server to its new value in dry-run mode."""
        physical_server = NetboxServer(api=self.mocked_api, server=self.netbox_host, dry_run=True)
        physical_server.status = "failed"
        self.netbox_host.save.assert_not_called()
        assert self.physical_server.status == "active"

    def test_fqdn_getter_ok(self):
        """It should return the FQDN of the device from its primary IP."""
        assert self.physical_server.fqdn == "physical.example.com"

    def test_fqdn_getter_v6_only(self):
        """It should return the FQDN of the device from its primary IPv6 if the IPv4 doesn't have a DNS name."""
        self.netbox_host.primary_ip4.dns_name = ""
        assert self.physical_server.fqdn == "physical.example.com"

    def test_fqdn_getter_no_dns(self):
        """It should raise a NetboxError if there is no DNS name defined for any primary IP of the device."""
        self.netbox_host.primary_ip4 = None
        self.netbox_host.primary_ip6.dns_name = None
        with pytest.raises(NetboxError, match="Server physical does not have any primary IP with a DNS name set"):
            self.physical_server.fqdn  # pylint: disable=pointless-statement

    def test_mgmt_fqdn_getter(self):
        """It should return the management FQDN of the device and cache it."""
        assert self.physical_server.mgmt_fqdn == "physical.mgmt.local"
        assert self.physical_server.mgmt_fqdn == "physical.mgmt.local"
        self.mocked_api.ipam.ip_addresses.get.assert_called_once_with(device="physical", interface="mgmt")

    def test_mgmt_fqdn_getter_no_mgmt(self):
        """It should raise a NetboxError if the management FQDN is not set."""
        self.mgmt_ip.dns_name = ""
        with pytest.raises(NetboxError, match="Server physical has no management interface with a DNS name set"):
            self.physical_server.mgmt_fqdn  # pylint: disable=pointless-statement

    def test_mgmt_fqdn_getter_virtual(self):
        """It should raise a NetboxError if trying to get the management FQDN on a virtual machine."""
        with pytest.raises(
            NetboxError, match="Server virtual is a virtual machine, does not have a management address"
        ):
            self.virtual_server.mgmt_fqdn  # pylint: disable=pointless-statement

    def test_asset_tag_fqdn_getter(self):
        """It should return the management FQDN of the asset tag of the device."""
        assert self.physical_server.asset_tag_fqdn == "asset1234.mgmt.local"

    def test_as_dict_physical(self):
        """It should return the dictionary representation of the physical server."""
        as_dict = self.physical_server.as_dict()
        assert as_dict["cluster"] is None
        assert not as_dict["is_virtual"]
        assert as_dict["name"] == "physical"

    def test_as_dict_virtual(self):
        """It should return the dictionary representation of the virtual machine."""
        as_dict = self.virtual_server.as_dict()
        assert as_dict["cluster"] == {"id": 1, "name": "testcluster"}
        assert as_dict["is_virtual"]
        assert as_dict["name"] == "virtual"

    def test_access_vlan_getter_ok(self):
        """It should return the access vlan of the device."""
        assert self.physical_server.access_vlan == "test_vlan"

    def test_access_vlan_getter_no_primary_ip(self):
        """It should raise a NetboxError if no primary IP is set."""
        self.netbox_host.primary_ip = None
        with pytest.raises(NetboxError, match="No primary IP, needed to find the primary interface."):
            self.physical_server.access_vlan  # pylint: disable=pointless-statement

    def test_access_vlan_getter_primary_ip_not_assigned(self):
        """It should raise a NetboxError if the primary IP is not assigned to an interface."""
        self.netbox_host.primary_ip.assigned_object = None
        with pytest.raises(NetboxError, match="Primary IP not assigned to an interface."):
            self.physical_server.access_vlan  # pylint: disable=pointless-statement

    def test_access_vlan_getter_primary_interface_not_connected(self):
        """It should raise a NetboxError if the primary interface not connected."""
        self.netbox_host.primary_ip.assigned_object.connected_endpoint = None
        with pytest.raises(NetboxError, match="Primary interface not connected."):
            self.physical_server.access_vlan  # pylint: disable=pointless-statement

    def test_access_vlan_getter_switch_interface_no_vlan(self):
        """It should return an empty string."""
        self.netbox_host.primary_ip.assigned_object.connected_endpoint.untagged_vlan = None
        assert self.physical_server.access_vlan == ""

    def test_access_vlan_getter_virtual(self):
        """It should raise a NetboxError if trying to get the access vlan on a virtual machine."""
        with pytest.raises(NetboxError, match="Server is a virtual machine, can't return a switch interface."):
            self.virtual_server.access_vlan  # pylint: disable=pointless-statement

    def test_access_vlan_setter_ok(self):
        """It should set the access vlan."""
        self.physical_server.access_vlan = "set_test_vlan"
        assert self.netbox_host.save.called_once_with()

    def test_access_vlan_setter_not_found(self):
        """It should raise a NetboxError if trying to set an non active vlan."""
        self.mocked_api.ipam.vlans.get.return_value = None
        with pytest.raises(NetboxError, match="Failed to find an active VLAN with name set_test_vlan"):
            self.physical_server.access_vlan = "set_test_vlan"

    def test_access_vlan_setter_dry_run(self):
        """It should skip setting the access vlan of the server to its new value in dry-run mode."""
        physical_server = NetboxServer(api=self.mocked_api, server=self.netbox_host, dry_run=True)
        physical_server.access_vlan = "set_test_vlan"
        self.netbox_host.save.assert_not_called()
        assert self.physical_server.access_vlan == "test_vlan"

    def test_primary_ip4_address_getter_ok(self):
        """It should return the primary IPv4 address of the device."""
        assert self.physical_server.primary_ip4_address == IPv4Interface("10.0.0.1/22")

    def test_primary_ip4_address_getter_none_ok(self):
        """It should return None."""
        self.netbox_host.primary_ip4 = None
        assert self.physical_server.primary_ip4_address is None

    def test_primary_ip4_address_setter_ok(self):
        """It should set the primary IPv4 address (and no CIDR means /32)."""
        self.mocked_api.ipam.ip_addresses.count.return_value = 0
        self.physical_server.primary_ip4_address = "192.0.2.1"
        assert self.netbox_host.save.called_once_with()
        assert self.physical_server.primary_ip4_address == IPv4Interface("192.0.2.1/32")

    def test_primary_ip4_address_setter_not_valid(self):
        """It should raise a NetboxError if trying to set the v4 IP to an invalid value."""
        with pytest.raises(NetboxError, match="foo is not a valid IP in the CIDR notation."):
            self.physical_server.primary_ip4_address = "foo"

    def test_set_primary_ip_wrong_version(self):
        """It should raise a NetboxError if trying to set the v4 IP to an invalid value."""
        with pytest.raises(NetboxError, match="192.0.2.1/32 is not an IPv6"):
            self.physical_server.primary_ip6_address = "192.0.2.1/32"

    def test_primary_ip4_address_setter_existing(self):
        """It should raise a NetboxError if trying to set a v4 IP already in use."""
        self.mocked_api.ipam.ip_addresses.count.return_value = 1
        with pytest.raises(NetboxError, match="192.0.2.1/32 is already in use."):
            self.physical_server.primary_ip4_address = "192.0.2.1/32"

    def test_primary_ip6_address_getter_ok(self):
        """It should return the primary IPv6 address of the device."""
        assert self.physical_server.primary_ip6_address == IPv6Interface("2620:0:861:103:10::1/64")

    def test_primary_ip6_address_getter_none_ok(self):
        """It should return None."""
        self.netbox_host.primary_ip6 = None
        assert self.physical_server.primary_ip6_address is None

    def test_primary_ip6_address_setter_ok(self):
        """It should set the primary IPv6 address."""
        self.mocked_api.ipam.ip_addresses.count.return_value = 0
        self.physical_server.primary_ip6_address = "2001:db8::1/32"
        assert self.netbox_host.save.called_once_with()

    def test_primary_ip6_address_setter_dry_run(self):
        """It should skip setting the primary IPv6 address."""
        self.mocked_api.ipam.ip_addresses.count.return_value = 0
        physical_server = NetboxServer(api=self.mocked_api, server=self.netbox_host, dry_run=True)
        physical_server.primary_ip6_address = "2001:db8::1/32"
        assert self.physical_server.primary_ip6_address == IPv6Interface("2620:0:861:103:10::1/64")
        self.netbox_host.save.assert_not_called()

    def test_primary_ip4_address_getter_no_primary_ip(self):
        """It should raise a NetboxError if it tries to set the address to a device without primary IP."""
        self.netbox_host.primary_ip4 = None
        with pytest.raises(NetboxError, match="No existing primary IPv4 for physical."):
            self.physical_server.primary_ip4_address = "192.0.2.1/32"
