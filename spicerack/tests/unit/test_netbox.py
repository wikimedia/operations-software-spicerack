"""Netbox module tests."""

from unittest import mock

import pynetbox
import pytest
import yaml

from spicerack.netbox import Netbox, NetboxAPIError, NetboxError
from spicerack.tests import get_fixture_path


NETBOX_URL = 'https://example.com/'
NETBOX_TOKEN = 'FAKETOKEN123'


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
    fake_host.save = mock.Mock(return_value=True)
    return fake_host


def _get_choices_mock():
    """Return the possible Netbox device statuses."""
    with open(get_fixture_path('netbox', 'device_status.yaml')) as device_status_choices:
        choices_mock = mock.Mock(return_value=yaml.safe_load(device_status_choices))
    return choices_mock


@mock.patch('pynetbox.api')
def test_netbox_choices_api_error(mocked_pynetbox):
    """Test an API error retrieving the choices list."""
    mocked_pynetbox().dcim.choices = mock.Mock(side_effect=_request_error())
    with pytest.raises(NetboxAPIError, match=r'error fetching dcim choices'):
        Netbox(NETBOX_URL, NETBOX_TOKEN, dry_run=True)


@mock.patch('pynetbox.api')
def test_netbox_choices_api_devices_missing(mocked_pynetbox):
    """Test device status missing from choices API."""
    mocked_pynetbox().dcim.choices = mock.Mock(return_value={})
    nb = Netbox(NETBOX_URL, NETBOX_TOKEN, dry_run=True)
    with pytest.raises(NetboxError, match='device:status not present in DCIM choices returned by API'):
        nb.device_status_choices  # pylint: disable=pointless-statement


@mock.patch('pynetbox.api')
def test_fetch_host(mocked_pynetbox):
    """Test fetching a single host."""
    mocked_pynetbox.dcim.devices.get.return_value = _fake_host()
    netbox = Netbox(NETBOX_URL, NETBOX_TOKEN, dry_run=True)

    host = netbox.fetch_host('host')
    assert host == mocked_pynetbox().dcim.devices.get()


@mock.patch('pynetbox.api')
def test_fetch_host_error(mocked_pynetbox):
    """Test host fetch error handling plumbing."""
    mocked_pynetbox().dcim.devices.get.side_effect = _request_error()
    netbox = Netbox(NETBOX_URL, NETBOX_TOKEN, dry_run=True)
    with pytest.raises(NetboxAPIError, match='error retrieving host'):
        netbox.fetch_host('host')


@mock.patch('pynetbox.api')
def test_fetch_host_status(mocked_pynetbox):
    """Test fetching host status."""
    mocked_pynetbox().dcim.devices.get.return_value = _fake_host()
    mocked_pynetbox().dcim.choices = _get_choices_mock()
    netbox = Netbox(NETBOX_URL, NETBOX_TOKEN, dry_run=True)

    assert netbox.fetch_host_status('host') == 'Active'


@mock.patch('pynetbox.api')
def test_put_host_status_badstatus(mocked_pynetbox):
    """Test putting writing an incorrect status."""
    mocked_pynetbox().dcim.devices.get.return_value = _fake_host()
    mocked_pynetbox().dcim.choices = _get_choices_mock()
    netbox = Netbox(NETBOX_URL, NETBOX_TOKEN, dry_run=True)

    # Test setting an impossible status
    with pytest.raises(NetboxError, match='Fakestatus is not an available status'):
        netbox.put_host_status('host', 'FakeStatus')


@mock.patch('pynetbox.api')
def test_put_host_status_good_status(mocked_pynetbox):
    """Test setting a status and it working."""
    fake_host = _fake_host()
    mocked_pynetbox().dcim.devices.get.return_value = fake_host
    mocked_pynetbox().dcim.choices = _get_choices_mock()
    netbox = Netbox(NETBOX_URL, NETBOX_TOKEN, dry_run=False)

    netbox.put_host_status('host', 'Planned')
    assert fake_host.status == netbox.device_status_choices['Planned']
    assert fake_host.save.called


@mock.patch('pynetbox.api')
def test_put_host_status_save_failure(mocked_pynetbox):
    """Test save failure."""
    fake_host = _fake_host()
    mocked_pynetbox().dcim.devices.get.return_value = fake_host
    mocked_pynetbox().dcim.choices = _get_choices_mock()
    netbox = Netbox(NETBOX_URL, NETBOX_TOKEN, dry_run=False)
    fake_host.save.return_value = False
    with pytest.raises(NetboxAPIError, match='failed to save status for host Active -> Planned'):
        netbox.put_host_status('host', 'Planned')
    assert fake_host.save.called


@mock.patch('pynetbox.api')
def test_put_host_status_dryrun_success(mocked_pynetbox):
    """Test dry run, which  should always work on save."""
    fake_host = _fake_host()
    mocked_pynetbox().dcim.devices.get.return_value = fake_host
    mocked_pynetbox().dcim.choices = _get_choices_mock()
    netbox = Netbox(NETBOX_URL, NETBOX_TOKEN, dry_run=True)
    fake_host.save.return_value = False
    netbox.put_host_status('host', 'Planned')
    assert not fake_host.save.called


@mock.patch('pynetbox.api')
def test_put_host_status_error(mocked_pynetbox):
    """Test exception during save."""
    fake_host = _fake_host()
    mocked_pynetbox().dcim.devices.get.return_value = fake_host
    mocked_pynetbox().dcim.choices = _get_choices_mock()
    netbox = Netbox(NETBOX_URL, NETBOX_TOKEN, dry_run=False)
    fake_host.save.side_effect = _request_error()
    with pytest.raises(NetboxAPIError, match='failed to save host status'):
        netbox.put_host_status('host', 'Planned')
    assert fake_host.save.called
