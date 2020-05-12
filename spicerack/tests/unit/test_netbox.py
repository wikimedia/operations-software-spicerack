"""Netbox module tests."""

from unittest import mock

import pynetbox
import pytest

from spicerack.netbox import Netbox, NetboxAPIError, NetboxError, NetboxHostNotFoundError


NETBOX_URL = 'https://example.com/'
NETBOX_TOKEN = 'FAKETOKEN'  # nosec


def _request_error():
    """Return a Netbox RequestError."""
    fakestatus = mock.Mock()
    fakestatus.status_code = 404
    return pynetbox.RequestError(fakestatus)


def _fake_host():
    """Return a mocked Netbox host."""
    fake_host = mock.Mock()
    fake_host.name = 'test'
    fake_host.status = 'Active'
    fake_host.serialize = mock.Mock(return_value={'name': 'test'})
    fake_host.save = mock.Mock(return_value=True)
    return fake_host


def _fake_virtual_host():
    """Return a mocked Netbox host."""
    fake_host = mock.Mock()
    fake_host.name = 'test'
    fake_host.status = 'Active'
    fake_host.cluster.name = 'testcluster'
    fake_host.serialize = mock.Mock(return_value={'name': 'test'})
    fake_host.save = mock.Mock(return_value=True)
    return fake_host


@mock.patch('pynetbox.api')
def test_netbox_api(mocked_api):
    """An instance of Netbox should instantiate the Netbox API and expose it via the api property."""
    netbox = Netbox(NETBOX_URL, NETBOX_TOKEN, dry_run=True)
    mocked_api.called_once_with(NETBOX_URL, token=NETBOX_TOKEN)
    assert netbox.api == mocked_api()


@mock.patch('pynetbox.api')
def test_netbox_fetch_host_status_nohost(mocked_pynetbox):
    """Test the error scenario where the host is not found."""
    mocked_pynetbox().dcim.devices.get.return_value = None
    mocked_pynetbox().virtualization.virtual_machines.get.return_value = None
    netbox = Netbox(NETBOX_URL, NETBOX_TOKEN, dry_run=True)
    with pytest.raises(NetboxHostNotFoundError):
        netbox.fetch_host_status('host')


@mock.patch('pynetbox.api')
def test_netbox_fetch_host_status_error(mocked_pynetbox):
    """Test the error scenario where the host is not found."""
    mocked_pynetbox().dcim.devices.get = mock.Mock(side_effect=_request_error())
    mocked_pynetbox().virtualization.virtual_machines.get = mock.Mock(side_effect=_request_error())
    netbox = Netbox(NETBOX_URL, NETBOX_TOKEN, dry_run=True)
    with pytest.raises(NetboxError, match='Error retrieving Netbox host'):
        netbox.fetch_host_status('host')


@mock.patch('pynetbox.api')
def test_fetch_host_status(mocked_pynetbox):
    """Test fetching host status."""
    mocked_pynetbox().dcim.devices.get.return_value = _fake_host()
    mocked_pynetbox().virtualization.virtual_machines.get.return_value = None
    netbox = Netbox(NETBOX_URL, NETBOX_TOKEN, dry_run=True)

    assert netbox.fetch_host_status('host') == 'Active'


@mock.patch('pynetbox.api')
def test_put_host_status_good_status(mocked_pynetbox):
    """Test setting a status and it working."""
    fake_host = _fake_host()
    mocked_pynetbox().dcim.devices.get.return_value = fake_host
    mocked_pynetbox().virtualization.virtual_machines.get.return_value = None
    netbox = Netbox(NETBOX_URL, NETBOX_TOKEN, dry_run=False)

    netbox.put_host_status('host', 'Planned')
    assert str(fake_host.status) == 'planned'
    assert fake_host.save.called


@mock.patch('pynetbox.api')
def test_put_host_status_save_failure(mocked_pynetbox):
    """Test save failure."""
    fake_host = _fake_host()
    mocked_pynetbox().dcim.devices.get.return_value = fake_host
    mocked_pynetbox().virtualization.virtual_machines.get.return_value = None
    netbox = Netbox(NETBOX_URL, NETBOX_TOKEN, dry_run=False)
    fake_host.save.return_value = False
    with pytest.raises(NetboxAPIError, match='Failed to update Netbox status for host testhost Active -> planned'):
        netbox.put_host_status('testhost', 'Planned')
    assert fake_host.save.called


@mock.patch('pynetbox.api')
def test_put_host_status_dryrun_success(mocked_pynetbox):
    """Test dry run, which  should always work on save."""
    fake_host = _fake_host()
    mocked_pynetbox().dcim.devices.get.return_value = fake_host
    netbox = Netbox(NETBOX_URL, NETBOX_TOKEN, dry_run=True)
    fake_host.save.return_value = False
    netbox.put_host_status('host', 'Planned')
    assert not fake_host.save.called


@mock.patch('pynetbox.api')
def test_put_host_status_error(mocked_pynetbox):
    """Test exception during save."""
    fake_host = _fake_host()
    mocked_pynetbox().dcim.devices.get.return_value = fake_host
    mocked_pynetbox().virtualization.virtual_machines.get.return_value = None
    netbox = Netbox(NETBOX_URL, NETBOX_TOKEN, dry_run=False)
    fake_host.save.side_effect = _request_error()
    with pytest.raises(NetboxAPIError, match='Failed to save Netbox status for host testhost Active -> planned'):
        netbox.put_host_status('testhost', 'Planned')
    assert fake_host.save.called


@mock.patch('pynetbox.api')
def test_fetch_host_detail(mocked_pynetbox):
    """Test fetching host detail."""
    fake_host = _fake_host()
    mocked_pynetbox().dcim.devices.get.return_value = fake_host
    mocked_pynetbox().virtualization.virtual_machines.get.return_value = None
    netbox = Netbox(NETBOX_URL, NETBOX_TOKEN, dry_run=True)
    detail = netbox.fetch_host_detail('test')
    assert fake_host.serialize.called
    assert not detail['is_virtual']


@mock.patch('pynetbox.api')
def test_fetch_host_detail_vm(mocked_pynetbox):
    """Virtual machines should have is_virtual == True and a cluster name."""
    fake_host = _fake_virtual_host()
    mocked_pynetbox().dcim.devices.get.return_value = None
    mocked_pynetbox().virtualization.virtual_machines.get.return_value = fake_host
    netbox = Netbox(NETBOX_URL, NETBOX_TOKEN, dry_run=True)
    detail = netbox.fetch_host_detail('test')
    assert fake_host.serialize.called
    assert detail['is_virtual']
    assert detail['ganeti_cluster'] == 'testcluster'


@mock.patch('pynetbox.api')
def test_fetch_host_status_vm(mocked_pynetbox):
    """Virtual machines should return status just like devices."""
    mocked_pynetbox().dcim.devices.get.return_value = None
    mocked_pynetbox().virtualization.virtual_machines.get.return_value = _fake_virtual_host()
    netbox = Netbox(NETBOX_URL, NETBOX_TOKEN, dry_run=True)

    assert netbox.fetch_host_status('host') == 'Active'


@mock.patch('pynetbox.api')
def test_fetch_host_status_vm_error(mocked_pynetbox):
    """Virtual machines should raise an exception on an API error."""
    mocked_pynetbox().dcim.devices.get.return_value = None
    mocked_pynetbox().virtualization.virtual_machines.get = mock.Mock(side_effect=_request_error())
    netbox = Netbox(NETBOX_URL, NETBOX_TOKEN, dry_run=True)

    with pytest.raises(NetboxAPIError, match="Error retrieving Netbox VM"):
        netbox.fetch_host_status('host')


@mock.patch('pynetbox.api')
def test_set_host_status_vm(mocked_pynetbox):
    """Virtual machines should raise an exception if you try to set the status."""
    fake_vm = _fake_virtual_host()
    mocked_pynetbox().dcim.devices.get.return_value = None
    mocked_pynetbox().virtualization.virtual_machines.get.return_value = fake_vm
    netbox = Netbox(NETBOX_URL, NETBOX_TOKEN, dry_run=True)

    with pytest.raises(NetboxHostNotFoundError):
        netbox.put_host_status('test', 'Active')

    assert not fake_vm.save.called
