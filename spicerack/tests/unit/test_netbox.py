"""Netbox module tests."""

from unittest import mock

import pynetbox
import pytest

from spicerack.netbox import Netbox, NetboxAPIError, NetboxError, NetboxHostNotFoundError, NetboxServer

NETBOX_URL = "https://example.com/"
NETBOX_TOKEN = "secret_token"


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
    host.primary_ip6.dns_name = f"{name}.example.com"

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
            "address": "2620:0:861:103:10:0:0:1/64",
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

    def test_netbox_fetch_host_status_nohost(self):
        """Test the error scenario where the host is not found."""
        self.mocked_api().dcim.devices.get.return_value = None
        self.mocked_api().virtualization.virtual_machines.get.return_value = None
        with pytest.raises(NetboxHostNotFoundError):
            self.netbox.fetch_host_status("host")

    def test_netbox_fetch_host_status_error(self):
        """Test the error scenario where the host is not found."""
        self.mocked_api().dcim.devices.get = mock.Mock(side_effect=_request_error())
        self.mocked_api().virtualization.virtual_machines.get = mock.Mock(side_effect=_request_error())
        with pytest.raises(NetboxError, match="Error retrieving Netbox host"):
            self.netbox.fetch_host_status("host")

    def test_fetch_host_status(self, netbox_host):
        """Test fetching host status."""
        self.mocked_api().dcim.devices.get.return_value = netbox_host
        self.mocked_api().virtualization.virtual_machines.get.return_value = None

        assert self.netbox.fetch_host_status("host") == "Active"

    def test_put_host_status_good_status(self, netbox_host):
        """Test setting a status and it working."""
        self.mocked_api().dcim.devices.get.return_value = netbox_host
        self.mocked_api().virtualization.virtual_machines.get.return_value = None

        self.netbox.put_host_status("host", "Planned")
        assert str(netbox_host.status) == "planned"
        assert netbox_host.save.called

    def test_put_host_status_save_failure(self, netbox_host):
        """Test save failure."""
        self.mocked_api().dcim.devices.get.return_value = netbox_host
        self.mocked_api().virtualization.virtual_machines.get.return_value = None
        netbox_host.save.return_value = False
        with pytest.raises(
            NetboxAPIError,
            match="Failed to update Netbox status for host physical Active -> planned",
        ):
            self.netbox.put_host_status("physical", "Planned")

        assert netbox_host.save.called

    def test_put_host_status_dry_run_success(self, netbox_host):
        """Test dry run, which  should always work on save."""
        self.mocked_api().dcim.devices.get.return_value = netbox_host
        netbox_host.save.return_value = False
        self.netbox_dry_run.put_host_status("physical", "Planned")
        netbox_host.save.assert_not_called()

    def test_put_host_status_error(self, netbox_host):
        """Test exception during save."""
        self.mocked_api().dcim.devices.get.return_value = netbox_host
        self.mocked_api().virtualization.virtual_machines.get.return_value = None
        netbox_host.save.side_effect = _request_error()
        with pytest.raises(
            NetboxAPIError,
            match="Failed to save Netbox status for host physical Active -> planned",
        ):
            self.netbox.put_host_status("physical", "Planned")

        assert netbox_host.save.called

    def test_fetch_host_detail(self, netbox_host):
        """Test fetching host detail."""
        self.mocked_api().dcim.devices.get.return_value = netbox_host
        self.mocked_api().virtualization.virtual_machines.get.return_value = None
        detail = self.netbox.fetch_host_detail("physical")
        assert netbox_host.serialize.called
        assert not detail["is_virtual"]

    def test_fetch_host_detail_vm(self, netbox_virtual_machine):
        """Virtual machines should have is_virtual == True and a cluster name."""
        self.mocked_api().dcim.devices.get.return_value = None
        self.mocked_api().virtualization.virtual_machines.get.return_value = netbox_virtual_machine
        detail = self.netbox.fetch_host_detail("virtual")
        assert netbox_virtual_machine.serialize.called
        assert detail["is_virtual"]
        assert detail["ganeti_cluster"] == "testcluster"

    def test_fetch_host_status_vm(self, netbox_virtual_machine):
        """Virtual machines should return status just like devices."""
        self.mocked_api().dcim.devices.get.return_value = None
        self.mocked_api().virtualization.virtual_machines.get.return_value = netbox_virtual_machine
        assert self.netbox.fetch_host_status("virtual") == "Active"

    def test_fetch_host_status_vm_error(self):
        """Virtual machines should raise an exception on an API error."""
        self.mocked_api().dcim.devices.get.return_value = None
        self.mocked_api().virtualization.virtual_machines.get = mock.Mock(side_effect=_request_error())
        with pytest.raises(NetboxAPIError, match="Error retrieving Netbox VM"):
            self.netbox.fetch_host_status("virtual")

    def test_set_host_status_vm(self, netbox_virtual_machine):
        """Virtual machines should raise an exception if you try to set the status."""
        self.mocked_api().dcim.devices.get.return_value = None
        self.mocked_api().virtualization.virtual_machines.get.return_value = netbox_virtual_machine

        with pytest.raises(NetboxHostNotFoundError):
            self.netbox.put_host_status("virtual", "Active")

        netbox_virtual_machine.save.assert_not_called()

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
        self.physical_server.status = "staged"
        assert self.netbox_host.save.called_once_with()

    def test_status_setter_virtual(self):
        """It should raise a NetboxError if trying to set the status on a virtual machine."""
        with pytest.raises(
            NetboxError,
            match="Server virtual is a virtual machine, its Netbox status is automatically synced from Ganeti",
        ):
            self.virtual_server.status = "staged"

    def test_status_setter_invalid_transition(self):
        """It should raise a NetboxError if trying to make an invalid status transition."""
        with pytest.raises(
            NetboxError, match="Forbidden Netbox status transition between active and planned for device physical"
        ):
            self.physical_server.status = "planned"

    def test_status_setter_dry_run(self):
        """It should skip setting the status of the server to its new value in dry-run mode."""
        physical_server = NetboxServer(api=self.mocked_api, server=self.netbox_host, dry_run=True)
        physical_server.status = "staged"
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
