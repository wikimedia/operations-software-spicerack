"""Netbox module."""

import logging
from ipaddress import IPv4Interface, IPv6Interface, ip_interface
from typing import Any, Optional, Union

import pynetbox
from requests.exceptions import RequestException
from wmflib.requests import http_session

from spicerack.decorators import retry
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


class NetboxScriptError(NetboxError):
    """Raised when a Netbox script doesn't run properly."""


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

    def run_script(self, name: str, *, commit: bool = False, params: dict[str, Any]) -> list:
        """Run a Netbox script and wait for its output.

        Arguments:
            name: Full name of the script to run (eg. import_server_facts.ImportPuppetDB).
            commit: save the script actions in the Netbox DB.
            params: script parameters (passed as POST data).

        Returns:
            The script execution logs in a list format.

        Raises:
            spicerack.netbox.NetboxScriptError: If the script coudn't be ran or its result fetched.

        """
        # Apparently pynetbox doesn't allow to execute a Netbox script
        url = self._api.extras.scripts.get(name).url
        headers = {"Authorization": f"Token {self._api.token}"}
        if self._dry_run and commit:
            logger.info("Forcing commit = False as running in DRY-RUN")
            commit = False
        data = {"data": params, "commit": int(commit)}

        script_http_session = http_session(".".join((self.__module__, self.__class__.__name__)), timeout=(5.0, 30.0))

        @retry(tries=30, backoff_mode="constant", exceptions=(ValueError, RequestException))
        def _poll_netbox_job(url: str) -> list:
            """Poll Netbox to get the result of the script run."""
            result = script_http_session.get(url, headers=headers)
            result.raise_for_status()
            data = result.json()["data"]
            if data is None:
                raise ValueError(f"No data from job result {url}")
            return data["log"]

        result = None
        try:
            result = script_http_session.post(url, headers=headers, json=data)
            result.raise_for_status()
            logger.debug("Started Netbox script %s, waiting for results.", name)
        except RequestException as e:
            raise NetboxScriptError(f"Failed to start Netbox script {name}") from e
        job_url = result.json()["result"]["url"]
        try:
            return _poll_netbox_job(job_url)
        except (ValueError, RequestException) as e:
            raise NetboxScriptError(f"Failed to get Netbox script results from {job_url}") from e


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

        role = server.role.slug
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
    def name(self) -> str:
        """Get the server name. Set the server name, primary IP DNS name, management IP DNS name.

        Modifying its value can be done only on physical devices.

        Arguments:
            new: the new name for the host.

        Raises:
            spicerack.netbox.NetboxError: if trying to set it on a virtual device or there is an issue renaming.

        """
        return self._server.name

    @name.setter
    def name(self, new: str) -> None:
        """Get and set the server name. See the getter docstring for info.

        Arguments:
            new: the new name for the host.

        Raises:
            spicerack.netbox.NetboxError: if trying to set it on a virtual device or there is an issue renaming.

        """
        if self.virtual:
            raise NetboxError(
                f"Server {self._server.name} is a virtual machine, changing the name is only for physical servers."
            )

        current = self._server.name
        if current == new:
            logger.debug("Current name is already %s", current)
            return
        if self._dry_run:
            logger.info("Skipping Netbox name change from %s to %s in DRY-RUN.", current, new)
            return

        self._server.name = new
        if self._server.save():
            logger.debug("Updated Netbox name from %s to %s", current, new)
        else:
            # See https://github.com/netbox-community/pynetbox/issues/586
            raise NetboxError(f"Name change for {current} didn't get applied by Netbox.")

        # Update the FQDNs
        self.fqdn = new + "." + self.fqdn.split(".", 1)[1]
        self.mgmt_fqdn = new + "." + self.mgmt_fqdn.split(".", 1)[1]

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

    def _set_primary_ip(self, value: Union[str, IPv4Interface, IPv6Interface], version: int) -> None:
        """Abstraction function to set a v4 or v6 IP on a host.

        Arguments:
            value: an IPv4 or IPv6 IP in CIDR notation.

        Raises:
            spicerack.netbox.NetboxError: if the provided IP is not valid.

        """
        try:
            ip = ip_interface(value)
        except ValueError as exc:
            raise NetboxError(f"{value} is not a valid IP in the CIDR notation.") from exc
        if ip.version != version:
            raise NetboxError(f"{value} is not an IPv{version}")
        primary_ip = getattr(self._server, f"primary_ip{ip.version}")
        if not primary_ip:
            raise NetboxError(f"No existing primary IPv{version} for {self._server.name}.")
        current = primary_ip.address
        if self._api.ipam.ip_addresses.count(address=str(ip)):
            raise NetboxError(f"{ip} is already in use.")
        if self._dry_run:
            logger.info(
                "Skipping Netbox primary IPv%d change from %s to %s for device %s in DRY-RUN.",
                ip.version,
                current,
                value,
                self._server.name,
            )
            return

        primary_ip.address = str(ip)
        primary_ip.save()
        logger.debug(
            "Updated Netbox primary IPv%d from %s to %s for device %s",
            ip.version,
            current,
            value,
            self._server.name,
        )

    @property
    def primary_ip4_address(self) -> Optional[IPv4Interface]:
        """Get and set the server primary IPv4 address.

        And not the Netbox ipam.IpAddresses object.

        Arguments:
            value: the new IPv4 (CIDR) to be set.

        """
        if self._server.primary_ip4:
            return IPv4Interface(self._server.primary_ip4.address)
        return None

    @primary_ip4_address.setter
    def primary_ip4_address(self, value: Union[str, IPv4Interface]) -> None:
        """Set the server primary IPv4 address. See the getter docstring for info.

        And not the Netbox ipam.IpAddresses object.

        Arguments:
            value: the new IPv4 (CIDR) to be set.

        """
        self._set_primary_ip(value, 4)

    @property
    def primary_ip6_address(self) -> Optional[IPv6Interface]:
        """Get and set the server primary IPv6 address.

        And not the Netbox ipam.IpAddresses object.

        Arguments:
            value: the new IPv6 (CIDR) to be set.

        """
        if self._server.primary_ip6:
            return IPv6Interface(self._server.primary_ip6.address)
        return None

    @primary_ip6_address.setter
    def primary_ip6_address(self, value: Union[str, IPv6Interface]) -> None:
        """Set the server primary IPv6 address. See the getter docstring for info.

        And not the Netbox ipam.IpAddresses object.

        Arguments:
            value: the new IPv6 (CIDR) to be set.

        """
        self._set_primary_ip(value, 6)

    @property
    def primary_mac_address(self) -> Optional[str]:
        """Get and set the server primary MAC address.

        Arguments:
            value: the new MAC address to be set.

        """
        # TODO : check if there is any risk of race condition,
        # Where we would need the MAC before the primary IP is set or assigned
        # The TODO from _find_primary_switch_iface is relevant here too
        try:
            return self._server.primary_ip.assigned_object.mac_address
        except AttributeError as exc:
            raise NetboxError(
                f"No primary IP or primary IP not assigned to an interface for {self._server.name}."
            ) from exc

    @primary_mac_address.setter
    def primary_mac_address(self, new_mac: Union[None, str]) -> None:
        """Get and set the server primary MAC address.

        Arguments:
            new_mac: the new MAC address to be set.

        """
        try:
            netbox_interface = self._server.primary_ip.assigned_object
            current_mac = netbox_interface.mac_address
        except AttributeError as exc:
            raise NetboxError(
                f"No primary IP or primary IP not assigned to an interface for {self._server.name}."
            ) from exc

        if self._dry_run:
            logger.info(
                "Skipping Netbox primary MAC change from %s to %s for device %s in DRY-RUN.",
                current_mac,
                new_mac,
                self._server.name,
            )
            return
        netbox_interface.mac_address = new_mac
        if not netbox_interface.save():
            raise NetboxError(f"Spicerack was not able to update the primary MAC for {self._server.name}.")
        logger.debug(
            "Updated Netbox primary MAC from %s to %s for device %s",
            current_mac,
            new_mac,
            self._server.name,
        )
        return

    def _find_primary_switch_iface(self) -> pynetbox.core.response.Record:
        """Returns the switch side interface connected to the device's primary interface.

        Returns:
            A Netbox interface object of the switch side connected to the device's primary interface.

        Raises:
            spicerack.netbox.NetboxError: if used on a virtual device,
              the device primary interface is not connected, or the primary IP is not linked to an interface.

        """
        # TODO: in the future find another way than requiring a primary IP to find the primary interface
        if self.virtual:
            raise NetboxError("Server is a virtual machine, can't return a switch interface.")
        primary_ip = self._server.primary_ip
        if not primary_ip:
            raise NetboxError("No primary IP, needed to find the primary interface.")
        netbox_iface = primary_ip.assigned_object
        if not netbox_iface:
            raise NetboxError("Primary IP not assigned to an interface.")
        # Ganeti hosts have their primary IP connected to a bridge device, so we need to find physical
        if netbox_iface.type.value == "bridge":
            netbox_iface = self._api.dcim.interfaces.get(
                device_id=self._server.id,
                bridge_id=netbox_iface.id,
                type__n=("virtual", "lag", "bridge"),
                mgmt_only=False,
            )
        netbox_iface_endpoints = netbox_iface.connected_endpoints
        if not netbox_iface_endpoints:
            raise NetboxError("Primary interface not connected.")
        # Using connected_endpoints[0] to mimic pre-Netbox 3.3 behavior, when a cable only had one termination
        # per side. To be revisited if we start using the multi-termination feature.
        return netbox_iface_endpoints[0]

    @property
    def access_vlan(self) -> str:
        """Get and set the server access vlan.

        Can be done only on physical devices, requires the device to have a primary IP.

        Arguments:
            value: the name of the vlan to be set.

        """
        netbox_switch_iface = self._find_primary_switch_iface()
        if netbox_switch_iface.untagged_vlan:
            return netbox_switch_iface.untagged_vlan.name
        return ""

    @access_vlan.setter
    def access_vlan(self, value: str) -> None:
        """Set the device access vlan. See the getter docstring for info.

        Arguments:
            value: the name of the access vlan to be set.

        Raises:
            spicerack.netbox.NetboxError: if used on a virtual device,
              the device primary interface is not connected or the vlan doesn't exist.

        """
        netbox_switch_iface = self._find_primary_switch_iface()
        new_vlan = self._api.ipam.vlans.get(name=value, status="active")
        if not new_vlan:
            raise NetboxError(f"Failed to find an active VLAN with name {value}")

        current = netbox_switch_iface.untagged_vlan.name if netbox_switch_iface.untagged_vlan else "NOT SET"
        if self._dry_run:
            logger.info(
                "Skipping Netbox update of switchport access vlan from %s to %s for device %s in DRY-RUN.",
                current,
                value,
                self._server.name,
            )
            return
        netbox_switch_iface.untagged_vlan = new_vlan
        netbox_switch_iface.save()
        logger.debug(
            "Updated Netbox switchport access vlan from %s to %s for device %s", current, value, self._server.name
        )

    @property
    def fqdn(self) -> str:
        """Get and set the device primary IPs FQDN if one is already set.

        Notes:
            If the FQDN for any of the primary IPs is not set it will not be updated.
            This is to prevent setting a IPv6 AAAA record by accident.

        Arguments:
            value: the new FQDN for the host.

        Raises:
            spicerack.netbox.NetboxError: if the server has no FQDN defined in Netbox.

        """
        # Until https://phabricator.wikimedia.org/T253173 is fixed we can't use the primary_ip attribute
        for attr_name in ("primary_ip4", "primary_ip6"):
            address = getattr(self._server, attr_name)
            if address is not None and address.dns_name:
                return address.dns_name

        raise NetboxError(f"Server {self._server.name} does not have any primary IP with a DNS name set.")

    @fqdn.setter
    def fqdn(self, value: str) -> None:
        """Get and set the device primary IPs FQDN if one is already set.

        Notes:
            If the FQDN for any of the primary IPs is not set it will not be updated.
            This is to prevent setting a IPv6 AAAA record by accident.

        Arguments:
            value: the new FQDN for the host.

        Raises:
            spicerack.netbox.NetboxError: if trying to set it on a virtual device
                                          or if the server has no FQDN defined in Netbox.

        """
        if self.virtual:
            raise NetboxError(
                f"Server {self._server.name} is a virtual machine, changing the FQDN is only for physical servers."
            )
        for attr_name in ("primary_ip4", "primary_ip6"):
            address = getattr(self._server, attr_name)
            if address is not None and address.dns_name:
                if address.dns_name == value:
                    logger.debug("Current dns_name is already %s", value)
                    continue
                address.dns_name = value
                if not address.save():
                    raise NetboxError(f"Spicerack was not able to update the {attr_name} FQDN for {self._server.name}.")
                logger.debug("Updated %s dns_name to %s", attr_name, value)

    @property
    def mgmt_fqdn(self) -> str:
        """Get and set the management FQDN of the device.

        Arguments:
            value: the new FQDN for the host.

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

    @mgmt_fqdn.setter
    def mgmt_fqdn(self, value: str) -> None:
        """Get and set the management FQDN of the device.

        Arguments:
            value: the new FQDN for the host.

        Raises:
            spicerack.netbox.NetboxError: if trying to set it on a virtual device or can't find the management IP.

        """
        if self.virtual:
            raise NetboxError(
                f"Server {self._server.name} is a virtual machine, "
                "changing the mgmt FQDN is only for physical servers."
            )
        address = self._api.ipam.ip_addresses.get(device=self._server.name, interface=MANAGEMENT_IFACE_NAME)
        # TODO: see the getter TODO
        if address is not None:
            if address.dns_name == value:
                self._cached_mgmt_fqdn = value
                logger.debug("Current dns_name is already %s", value)
                return
            address.dns_name = value
            if not address.save():
                raise NetboxError(f"Spicerack was not able to update the mgmt_fqdn for {self._server.name}.")
            self._cached_mgmt_fqdn = value
            logger.debug("Updated mgmt FQDN to %s", value)

    @property
    def asset_tag_fqdn(self) -> str:
        """Return the management FQDN for the asset tag of the device.

        Raises:
            spicerack.netbox.NetboxError: for virtual servers or the server has no management FQDN defined in Netbox.

        """
        parts = self.mgmt_fqdn.split(".")
        parts[0] = self._server.asset_tag.lower()
        return ".".join(parts)

    @property
    def switches(self) -> list[str]:
        """Return the name(s) of the production switch(es) the server is connected to.

        Raises:
            spicerack.netbox.NetboxError: for virtual servers.

        """
        if self.virtual:
            raise NetboxError(f"Server {self._server.name} is a virtual machine, not connected to a switch.")

        interfaces = self._api.dcim.interfaces.filter(
            device_id=self._server.id,
            mgmt_only=False,
            cabled=True,
            connected=True,
            connected_endpoints_type="dcim.interface",
        )
        return sorted(list({conn.device.name for interface in interfaces for conn in interface.connected_endpoints}))

    def as_dict(self) -> dict:
        """Return a dict containing details about the server."""
        ret = dict(self._server)
        ret["is_virtual"] = self.virtual

        return ret
