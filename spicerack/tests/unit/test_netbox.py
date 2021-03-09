"""Netbox module tests."""

from unittest import mock

import pynetbox
import pytest

from spicerack.netbox import Netbox, NetboxAPIError, NetboxError, NetboxHostNotFoundError

NETBOX_URL = "https://example.com/"
NETBOX_TOKEN = "FAKETOKEN"  # nosec


def _request_error():
    """Return a Netbox RequestError."""
    fakestatus = mock.Mock()
    fakestatus.status_code = 404
    return pynetbox.RequestError(fakestatus)


@pytest.fixture(name="netbox_host")
def _netbox_host():
    """Return a mocked Netbox physical device."""
    host = mock.Mock()
    host.name = "test"
    host.status = "Active"
    host.serialize = mock.Mock(return_value={"name": "test"})
    host.save = mock.Mock(return_value=True)
    return host


@pytest.fixture(name="netbox_virtual_machine")
def _netbox_virtual_machine():
    """Return a mocked Netbox virtual machine."""
    host = mock.Mock()
    host.name = "test"
    host.status = "Active"
    host.cluster.name = "testcluster"
    host.serialize = mock.Mock(return_value={"name": "test"})
    host.save = mock.Mock(return_value=True)
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
            match="Failed to update Netbox status for host testhost Active -> planned",
        ):
            self.netbox.put_host_status("testhost", "Planned")

        assert netbox_host.save.called

    def test_put_host_status_dry_run_success(self, netbox_host):
        """Test dry run, which  should always work on save."""
        self.mocked_api().dcim.devices.get.return_value = netbox_host
        netbox_host.save.return_value = False
        self.netbox_dry_run.put_host_status("host", "Planned")
        assert not netbox_host.save.called

    def test_put_host_status_error(self, netbox_host):
        """Test exception during save."""
        self.mocked_api().dcim.devices.get.return_value = netbox_host
        self.mocked_api().virtualization.virtual_machines.get.return_value = None
        netbox_host.save.side_effect = _request_error()
        with pytest.raises(
            NetboxAPIError,
            match="Failed to save Netbox status for host testhost Active -> planned",
        ):
            self.netbox.put_host_status("testhost", "Planned")

        assert netbox_host.save.called

    def test_fetch_host_detail(self, netbox_host):
        """Test fetching host detail."""
        self.mocked_api().dcim.devices.get.return_value = netbox_host
        self.mocked_api().virtualization.virtual_machines.get.return_value = None
        detail = self.netbox.fetch_host_detail("test")
        assert netbox_host.serialize.called
        assert not detail["is_virtual"]

    def test_fetch_host_detail_vm(self, netbox_virtual_machine):
        """Virtual machines should have is_virtual == True and a cluster name."""
        self.mocked_api().dcim.devices.get.return_value = None
        self.mocked_api().virtualization.virtual_machines.get.return_value = netbox_virtual_machine
        detail = self.netbox.fetch_host_detail("test")
        assert netbox_virtual_machine.serialize.called
        assert detail["is_virtual"]
        assert detail["ganeti_cluster"] == "testcluster"

    def test_fetch_host_status_vm(self, netbox_virtual_machine):
        """Virtual machines should return status just like devices."""
        self.mocked_api().dcim.devices.get.return_value = None
        self.mocked_api().virtualization.virtual_machines.get.return_value = netbox_virtual_machine
        assert self.netbox.fetch_host_status("host") == "Active"

    def test_fetch_host_status_vm_error(self):
        """Virtual machines should raise an exception on an API error."""
        self.mocked_api().dcim.devices.get.return_value = None
        self.mocked_api().virtualization.virtual_machines.get = mock.Mock(side_effect=_request_error())
        with pytest.raises(NetboxAPIError, match="Error retrieving Netbox VM"):
            self.netbox.fetch_host_status("host")

    def test_set_host_status_vm(self, netbox_virtual_machine):
        """Virtual machines should raise an exception if you try to set the status."""
        self.mocked_api().dcim.devices.get.return_value = None
        self.mocked_api().virtualization.virtual_machines.get.return_value = netbox_virtual_machine

        with pytest.raises(NetboxHostNotFoundError):
            self.netbox.put_host_status("test", "Active")

        assert not netbox_virtual_machine.save.called
