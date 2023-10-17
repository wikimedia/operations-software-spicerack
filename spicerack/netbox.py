"""Netbox module."""
import logging
from typing import Union

import pynetbox
from wmflib.requests import http_session

from spicerack.exceptions import SpicerackError

MANAGEMENT_IFACE_NAME: str = "mgmt"
"""The interface name used in Netbox for the OOB network."""
SERVER_ROLE_SLUG: str = "server"
"""Netbox role to identify servers."""
logger = logging.getLogger(__name__)


class NetboxError(SpicerackError):
    """General errors raised by this module."""


class NetboxAPIError(NetboxError):
    """Usually a wrapper for pynetbox.RequestError, errors that occur when accessing the API."""


class NetboxHostNotFoundError(NetboxError):
    """Raised when a host is not found for an operation."""


class Netbox:
    """Class which wraps Netbox API operations."""

    def __init__(self, url: str, token: str, *, dry_run: bool = True):
        """Create Netbox instance.

        Arguments:
            url: The Netbox top level URL (with scheme and port if necessary).
            token: A Netbox API token.
            dry_run: set to False to cause writes to Netbox to occur.

        """
        self._api = pynetbox.api(url, token=token, threading=True)
        self._api.http_session = http_session(".".join((self.__module__, self.__class__.__name__)))
        self._dry_run = dry_run

    @property
    def api(self) -> pynetbox.api:
        """Get the pynetbox instance to interact directly with Netbox APIs.

        Caution:
            When feasible use higher level functionalities.

        """
        return self._api

    def _get_device(self, name: str) -> pynetbox.core.response.Record:
        """Get a device (dcim.devices) object.

        Arguments:
            name: the name of the device to get.

        Raises:
            spicerack.netbox.NetboxAPIError: on API error.
            spicerack.netbox.NetboxError: on parameter error.
            spicerack.netbox.NetboxHostNotFoundError: if the device is not found.

        """
        try:
            device = self._api.dcim.devices.get(name=name)
        except pynetbox.RequestError as ex:
            raise NetboxAPIError("Error retrieving Netbox device") from ex

        if device is None:
            raise NetboxHostNotFoundError(name)

        return device

    def _get_virtual_machine(self, hostname: str) -> pynetbox.core.response.Record:
        """Get a virtual machine (virtualization.virtual_machine) object.

        Arguments:
            hostname: the name of the host to get.

        Raises:
            spicerack.netbox.NetboxAPIError: on API error.
            spicerack.netbox.NetboxError: on parameter error.
            spicerack.netbox.NetboxHostNotFoundError: if the host is not found.

        """
        try:
            host = self._api.virtualization.virtual_machines.get(name=hostname)
        except pynetbox.RequestError as ex:
            raise NetboxAPIError("Error retrieving Netbox VM") from ex

        if host is None:
            raise NetboxHostNotFoundError

        return host

    def get_server(self, hostname: str) -> "NetboxServer":
        """Return a NetboxServer instance for the given hostname.

        Arguments:
            hostname: the device hostname.

        Raises:
            spicerack.netbox.NetboxHostNotFoundError: if the device can't be found among physical or virtual devices.
            spicerack.netbox.NetboxError: if the device is not a server.

        """
        try:
            server = self._get_device(hostname)
        except NetboxHostNotFoundError:
            server = self._get_virtual_machine(hostname)

        return NetboxServer(api=self._api, server=server, dry_run=self._dry_run)


class NetboxServer:
    """Represent a Netbox device of role server or a virtual machine."""

    allowed_status_transitions: dict[str, tuple[str, ...]] = {
        "spare": ("planned", "failed", "decommissioned"),
        "planned": ("active", "failed", "decommissioned"),
        "failed": ("spare", "planned", "active", "decommissioned"),
        "active": ("failed", "decommissioned"),
        "decommissioned": ("planned", "spare"),
    }
    """Allowed transition between Netbox statuses.
    See https://wikitech.wikimedia.org/wiki/Server_Lifecycle#/media/File:Server_Lifecycle_Statuses.png"""

    def __init__(
        self,
        *,
        api: pynetbox.api,
        server: Union[pynetbox.models.dcim.Devices, pynetbox.models.virtualization.VirtualMachines],
        dry_run: bool = True,
    ):
        """Initialize the instance.

        Arguments:
            api: the API instance to connect to Netbox.
            server: the server object.

        Raises:
            spicerack.netbox.NetboxError: if the device is not of type server.

        """
        self._server = server
        self._api = api
        self._dry_run = dry_run
        self._cached_mgmt_fqdn = ""  # Cache the management interface as it would require an API call each time

        role = server.role.slug if self.virtual else server.device_role.slug
        if role != SERVER_ROLE_SLUG:
            raise NetboxError(f"Object of type {type(server)} has invalid role {role}, only server is allowed")

    @property
    def virtual(self) -> bool:
        """Getter to check if the server is physical or virtual.

        Returns:
            :py:data:`True` if the server is virtual, :py:data:`False` if physical.

        """
        return not hasattr(self._server, "rack")

    @property
    def status(self) -> str:
        """Get and set the server status.

        Modifying its value can be done only on physical devices and only between allowed transitions.

        The allowed transitions are defined in :py:data:`spicerack.netbox.Netbox.allowed_status_transitions`.

        Arguments:
            value: the name of the status to be set. It will be lower cased automatically.

        Raises:
            spicerack.netbox.NetboxError: if trying to set it on a virtual device or the status transision is not
                allowed.

        """
        return self._server.status.value

    @status.setter
    def status(self, value: str) -> None:
        """Set the device status. See the getter docstring for info.

        Arguments:
            value: the name of the status to be set. It will be lower cased automatically.

        Raises:
            spicerack.netbox.NetboxError: if used on a virtual device or the status transision is not allowed.

        """
        if self.virtual:
            raise NetboxError(
                f"Server {self._server.name} is a virtual machine, its Netbox status is automatically synced from "
                f"Ganeti."
            )

        current = self._server.status.value
        new = value.lower()
        allowed_transitions = NetboxServer.allowed_status_transitions.get(current, ())
        if new not in allowed_transitions:
            raise NetboxError(
                f"Forbidden Netbox status transition between {current} and {new} for device {self._server.name}. "
                f"Possible values are: {allowed_transitions}"
            )

        if self._dry_run:
            logger.info(
                "Skipping Netbox status change from %s to %s for device %s in DRY-RUN.", current, new, self._server.name
            )
            return

        self._server.status = value
        self._server.save()
        logger.debug("Updated Netbox status from %s to %s for device %s", current, new, self._server.name)

    @property
    def fqdn(self) -> str:
        """Return the FQDN of the device.

        Raises:
            spicerack.netbox.NetboxError: if the server has no FQDN defined in Netbox.

        """
        # Until https://phabricator.wikimedia.org/T253173 is fixed we can't use the primary_ip attribute
        for attr_name in ("primary_ip4", "primary_ip6"):
            address = getattr(self._server, attr_name)
            if address is not None and address.dns_name:
                return address.dns_name

        raise NetboxError(f"Server {self._server.name} does not have any primary IP with a DNS name set.")

    @property
    def mgmt_fqdn(self) -> str:
        """Return the management FQDN of the device.

        Raises:
            spicerack.netbox.NetboxError: for virtual servers or the server has no management FQDN defined in Netbox.

        """
        if self.virtual:
            raise NetboxError(f"Server {self._server.name} is a virtual machine, does not have a management address.")

        if self._cached_mgmt_fqdn:
            return self._cached_mgmt_fqdn

        address = self._api.ipam.ip_addresses.get(device=self._server.name, interface=MANAGEMENT_IFACE_NAME)
        # TODO: check also that address.assigned_object.mgmt_only is True if it will not generate anymore an additional
        #       API call to Netbox or the Netbox API become more efficient.
        if address is not None and address.dns_name:
            self._cached_mgmt_fqdn = address.dns_name
            return self._cached_mgmt_fqdn

        raise NetboxError(f"Server {self._server.name} has no management interface with a DNS name set.")

    @property
    def asset_tag_fqdn(self) -> str:
        """Return the management FQDN for the asset tag of the device.

        Raises:
            spicerack.netbox.NetboxError: for virtual servers or the server has no management FQDN defined in Netbox.

        """
        parts = self.mgmt_fqdn.split(".")
        parts[0] = self._server.asset_tag.lower()
        return ".".join(parts)

    def as_dict(self) -> dict:
        """Return a dict containing details about the server."""
        ret = dict(self._server)
        ret["is_virtual"] = self.virtual

        return ret
