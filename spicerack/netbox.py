"""Netbox module."""
import logging
import warnings
from typing import Dict, Union

import pynetbox
from wmflib.requests import http_session

from spicerack.exceptions import SpicerackError

MANAGEMENT_IFACE_NAME: str = "mgmt"
SERVER_ROLE_SLUG: str = "server"
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
            url (str): The Netbox top level URL (with scheme and port if necessary)
            token (str): A Netbox API token
            dry_run (bool, optional): set to False to cause writes to Netbox to occur

        """
        self._api = pynetbox.api(url, token=token)
        self._api.http_session = http_session(".".join((self.__module__, self.__class__.__name__)))
        self._dry_run = dry_run

    @property
    def api(self) -> pynetbox.api:
        """Getter for the Netbox API property.

        Todo:
            When feasible expose instead higher level functionalities.

        Returns:
            pynetbox.api: the Netbox API instance.

        """
        return self._api

    def _fetch_host(self, hostname: str) -> pynetbox.core.response.Record:
        """Fetch a host (dcim.devices) object.

        Arguments:
            hostname (str): the name of the host to fetch

        Returns:
            pynetbox.core.response.Record: the host object from the API

        Raises:
            NetboxAPIError: on API error
            NetboxError: on parameter error
            NetboxHostNotFoundError: if the host is not found

        """
        try:
            host = self._api.dcim.devices.get(name=hostname)
        except pynetbox.RequestError as ex:
            # excepts on other errors
            raise NetboxAPIError("Error retrieving Netbox host") from ex

        if host is None:
            raise NetboxHostNotFoundError
        return host

    def _fetch_virtual_machine(self, hostname: str) -> pynetbox.core.response.Record:
        """Fetch a virrtual machine (virtualization.virtual_machine) object.

        Arguments:
            hostname (str): the name of the host to fetch

        Returns:
            pynetbox.core.response.Record: the host object from the API

        Raises:
            NetboxAPIError: on API error
            NetboxError: on parameter error
            NetboxHostNotFoundError: if the host is not found

        """
        try:
            host = self._api.virtualization.virtual_machines.get(name=hostname)
        except pynetbox.RequestError as ex:
            # excepts on other errors
            raise NetboxAPIError("Error retrieving Netbox VM") from ex

        if host is None:
            raise NetboxHostNotFoundError

        return host

    def put_host_status(self, hostname: str, status: str) -> None:
        """Set the device status.

        . deprecated:: v0.0.50
            use :py:class:`spicerack.netbox.NetboxServer` instead.

        Note:
           This method does not operate on virtual machines since they are
           updated automatically from Ganeti into Netbox.

        Arguments:
            hostname (str): the name of the host to operate on
            status (str): A status label or name

        Raises:
            NetboxAPIError: on API error.
            NetboxError: on parameter error.

        """
        warnings.warn("Deprecated method, use spicearack.netbox_server() instead", DeprecationWarning)
        status = status.lower()
        host = self._fetch_host(hostname)
        oldstatus = host.status

        if self._dry_run:
            logger.info(
                "Skipping Netbox status update in DRY-RUN mode for host %s %s -> %s",
                hostname,
                oldstatus,
                status,
            )
            return

        host.status = status
        try:
            save_result = host.save()
        except pynetbox.RequestError as ex:
            raise NetboxAPIError(f"Failed to save Netbox status for host {hostname} {oldstatus} -> {status}") from ex

        if save_result:
            logger.info(
                "Netbox status updated for host %s %s -> %s",
                hostname,
                oldstatus,
                status,
            )
        else:
            raise NetboxAPIError(f"Failed to update Netbox status for host {hostname} {oldstatus} -> {status}")

    def fetch_host_status(self, hostname: str) -> str:
        """Return the current status of a host as a string.

        . deprecated:: v0.0.50
            use :py:class:`spicerack.netbox.NetboxServer` instead.

        Arguments:
            hostname (str): the name of the host status

        Returns:
            str: the normalized status name

        Raises:
            NetboxAPIError: on API error
            NetboxError: on parameter error
            NetboxHostNotFoundError: if the host is not found

        """
        warnings.warn("Deprecated method, use spicearack.netbox_server() instead", DeprecationWarning)
        try:
            return str(self._fetch_host(hostname).status)
        except NetboxHostNotFoundError:
            return str(self._fetch_virtual_machine(hostname).status)

    def fetch_host_detail(self, hostname: str) -> Dict:
        """Return a dict containing details about the host.

        . deprecated:: v0.0.50
            use :py:class:`spicerack.netbox.NetboxServer` instead.

        Arguments:
            hostname (str): the name of the host to retrieve.

        Returns:
            dict: data about the host

        Raises:
            NetboxAPIError: on API error
            NetboxError: on parameter error
            NetboxHostNotFoundError: if the host is not found

        """
        warnings.warn("Deprecated method, use spicearack.netbox_server() instead", DeprecationWarning)
        is_virtual = False
        vm_cluster = "N/A"
        try:
            host = self._fetch_host(hostname)
        except NetboxHostNotFoundError:
            host = self._fetch_virtual_machine(hostname)
            is_virtual = True
            vm_cluster = host.cluster.name

        ret = host.serialize()
        ret["is_virtual"] = is_virtual
        ret["ganeti_cluster"] = vm_cluster
        return ret

    def get_server(self, hostname: str) -> "NetboxServer":
        """Return a NetboxServer instance for the given hostname.

        Arguments:
            hostname (str): the device hostname.

        Raises:
            spicerack.netbox.NetboxHostNotFoundError: if the device can't be found among physical or virtual devices.
            spicerack.netbox.NetboxError: if the device is not a server.

        Return:
            spicerack.netbox.NetboxServer: the server instance.

        """
        try:
            server = self._fetch_host(hostname)
        except NetboxHostNotFoundError:
            server = self._fetch_virtual_machine(hostname)

        return NetboxServer(api=self._api, server=server, dry_run=self._dry_run)


class NetboxServer:
    """Represent a Netbox device of role server or a virtual machine."""

    allowed_status_transitions = {
        "spare": ("planned", "failed", "decommissioned"),
        "planned": ("staged", "failed"),
        "failed": ("spare", "planned", "staged", "decommissioned"),
        "staged": ("failed", "active", "decommissioned"),
        "active": ("staged", "decommissioned"),
        "decommissioned": ("staged", "spare"),
    }
    """dict: See https://wikitech.wikimedia.org/wiki/Server_Lifecycle#/media/File:Server_Lifecycle_Statuses.png"""

    def __init__(
        self,
        *,
        api: pynetbox.api,
        server: Union[pynetbox.models.dcim.Devices, pynetbox.models.virtualization.VirtualMachines],
        dry_run: bool = True,
    ):
        """Initialize the instance.

        Arguments:
            api (pynetbox.api): the API instance to connect to Netbox.
            server (pynetbox.models.dcim.Devices, pynetbox.models.virtualization.VirtualMachines): the server object.

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
            bool: :py:data:`True` if the server is virtual, :py:data:`False` if physical.

        """
        return not hasattr(self._server, "rack")

    @property
    def status(self) -> str:
        """Getter for the server status property.

        Returns:
            str: the status name.

        """
        return self._server.status.value

    @status.setter
    def status(self, value: str) -> None:
        """Set the device status. Can be used only on physical devices and only between allowed transitions.

        The allowed transitions are defined in :py:data:`spicerack.netbox.Netbox.allowed_status_transitions`.

        Arguments:
            value (str): the name of the status to be set. It will be lower cased automatically.

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

        Returns:
            str: the FQDN.

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

        Returns:
            str: the management FQDN.

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

        Return:
            str: the asset tag management FQDN.

        Raises:
            spicerack.netbox.NetboxError: for virtual servers or the server has no management FQDN defined in Netbox.

        """
        parts = self.mgmt_fqdn.split(".")
        parts[0] = self._server.asset_tag.lower()
        return ".".join(parts)

    def as_dict(self) -> Dict:
        """Return a dict containing details about the server.

        Returns:
            dict: with the whole data about the server.

        """
        ret = dict(self._server)
        ret["is_virtual"] = self.virtual

        return ret
