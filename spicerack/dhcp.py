"""Provide an interface for manipulating DHCP configuration snippets for our dynamic/temporary DHCP system."""

import base64
import logging
import re
import textwrap
from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from ipaddress import IPv4Address

from wmflib.constants import ALL_DATACENTERS

from spicerack.exceptions import SpicerackError
from spicerack.remote import RemoteExecutionError, RemoteHosts

logger = logging.getLogger(__name__)
DHCP_TARGET_PATH: str = "/etc/dhcp/automation"
"""The path to the top of the DHCPd automation directory."""
MGMT_HOSTNAME_RE: str = r"\.mgmt\.{dc}\.wmnet"
"""A regular expression when formatted with a `dc` parameter will match a management hostname."""


class DHCPError(SpicerackError):
    """Base class for DHCP object errors."""


class DHCPRestartError(DHCPError):
    """Raised when the includes generator on target machine returns non-zero."""


class DHCPConfiguration(ABC):
    """An abstract class which defines the interface for the DHCP configuration generators."""

    def __str__(self) -> str:
        """Return the rendered DHCP configuration snippet."""
        return textwrap.dedent(self._template.format(s=self))

    # TODO: remove the chaining of decorators
    @property  # type: ignore
    @classmethod
    @abstractmethod
    def _template(cls) -> str:
        """Define a string template to be formatted by the instance properties.

        The default implementation of the string representation of the instance will format this template string with
        ``s=self``.
        """

    @property
    @abstractmethod
    def filename(self) -> str:
        """Return a string of the proposed filename for this configuration, from the automation directory."""


@dataclass(frozen=True)
class DHCPConfOpt82(DHCPConfiguration):
    """A configuration generator for host installation DHCP entries via DHCP Option 82.

    Arguments:
        hostname: the hostname to generate the DHCP matching block for.
        ipv4: the IPv4 to be assigned to the host.
        switch_hostname: the hostname of the switch the host is connected to.
        switch_iface: the name of the switch interface the host is connected to.
        vlan: the name of the VLAN the host is configured for.
        ttys: which ttyS to use for this host, accepted values are 0 and 1.
        distro: the codename of the Debian distribution to use for the PXE installer.
        media_type: The media type to use e.g. ``installer``, ``installer-11.0``, ``rescue``.

    """

    hostname: str
    ipv4: IPv4Address
    switch_hostname: str
    switch_iface: str
    vlan: str
    ttys: int
    distro: str
    media_type: str = "installer"

    _template: str = """
    host {s.hostname} {{
        host-identifier option agent.circuit-id "{s.switch_hostname}:{s.switch_iface}:{s.vlan}";
        fixed-address {s.ipv4};
        option pxelinux.pathprefix "http://apt.wikimedia.org/tftpboot/{s.distro}-{s.media_type}/";
    }}
    """

    @property
    def filename(self) -> str:
        """Return the proposed filename based on this configuration."""
        return f"ttyS{self.ttys}-115200/{self.hostname}.conf"


@dataclass(frozen=True)
class DHCPConfMac(DHCPConfiguration):
    """A configuration generator for host installation DHCP entries via MAC address.

    Arguments:
        hostname: the hostname to generate the DHCP matching block for.
        ipv4: the IPv4 to be assigned to the host.
        mac: the MAC address of the host's interface.
        ttys: which ttyS to use for this host, accepted values are 0 and 1.
        distro: the codename of the Debian distribution to use for the PXE installer.
        media_type: The media type to use e.g. installer, installer-11.0, rescue

    """

    hostname: str
    ipv4: IPv4Address
    mac: str
    ttys: int
    distro: str
    media_type: str = "installer"

    _template: str = """
    host {s.hostname} {{
        hardware ethernet {s.mac};
        fixed-address {s.ipv4};
        option pxelinux.pathprefix "http://apt.wikimedia.org/tftpboot/{s.distro}-{s.media_type}/";
    }}
    """

    def __post_init__(self) -> None:
        """According to Python's dataclass API to validate the arguments.

        See Also:
            https://docs.python.org/3/library/dataclasses.html#post-init-processing

        """
        mac_pattern = r"[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}"
        if re.fullmatch(mac_pattern, self.mac) is None:
            raise DHCPError(f"Invalid MAC address {self.mac}, must match pattern {mac_pattern}.")

    @property
    def filename(self) -> str:
        """Return the proposed filename based on this configuration."""
        return f"ttyS{self.ttys}-115200/{self.hostname}.conf"


@dataclass(frozen=True)
class DHCPConfMgmt(DHCPConfiguration):
    """A configuration for management network DHCP entries.

    Arguments:
        datacenter: the name of the Datacenter the host is.
        serial: the vendor serial of the host.
        manufacturer: the name of the manufacturer.
        fqdn: the management console FQDN to use for this host.
        ipv4: the IP address to give the management interface.

    """

    datacenter: str
    serial: str
    manufacturer: str
    fqdn: str
    ipv4: IPv4Address

    _template: str = """
    class "{s.fqdn}" {{
        match if (lcase(option host-name) = "{s.hostname}");
    }}
    pool {{
        allow members of "{s.fqdn}";
        range {s.ipv4} {s.ipv4};
    }}
    """

    def __post_init__(self) -> None:
        """Validate parameters."""
        if self.datacenter not in ALL_DATACENTERS:
            raise DHCPError(f"Invalid datacenter {self.datacenter}, must be one of {ALL_DATACENTERS}.")
        pattern = MGMT_HOSTNAME_RE.format(dc=self.datacenter)
        if not re.search(pattern, self.fqdn):
            raise DHCPError(f"Invalid management FQDN {self.fqdn}, must match {pattern}.")

    @property
    def filename(self) -> str:
        """Return the filename that corresponds to this configuration."""
        return f"""mgmt-{self.datacenter}/{self.fqdn}.conf"""

    @property
    def hostname(self) -> str:
        """Return the hostname based on manufacturer and serial."""
        serial = self.serial.lower()
        if self.manufacturer.lower() == "dell":
            return f"idrac-{serial}"

        return serial


class DHCP:
    """A class which provides tools for manipulating DHCP configuration snippets by data center."""

    def __init__(self, hosts: RemoteHosts, *, dry_run: bool = True):
        """Create a DHCP instance.

        Arguments:
            hosts: The target datacenter's install servers.
            dry_run: whether this is a DRY-RUN.

        """
        self._dry_run = dry_run
        if len(hosts) < 1:
            raise DHCPError("No target hosts provided.")
        self._hosts = hosts

    def refresh_dhcp(self) -> None:
        """Regenerate includes on target data center and restart DHCP, or raise if failure at any stage."""
        try:
            self._hosts.run_sync("/usr/local/sbin/dhcpincludes -r commit", print_progress_bars=False)
        except RemoteExecutionError as exc:
            raise DHCPRestartError("Failed to refresh the DHCP server when running dhcpincludes.") from exc

    def push_configuration(self, configuration: DHCPConfiguration) -> None:
        """Push a specified file with specified content to DHCP server and call refresh_dhcp.

        Arguments:
            configuration: An instance which provides content and filename for a configuration.

        """
        filename = f"{DHCP_TARGET_PATH}/{configuration.filename}"
        try:
            self._hosts.run_sync(
                f"/usr/bin/test '!' '-e' {filename}", is_safe=True, print_output=False, print_progress_bars=False
            )
        except RemoteExecutionError as exc:
            raise DHCPError(
                f"Snippet {filename} already exists, is there another operation in progress for the same device? "
                "If not you delete it and retry."
            ) from exc

        b64encoded = base64.b64encode(str(configuration).encode()).decode()
        try:
            self._hosts.run_sync(
                f"/bin/echo '{b64encoded}' | /usr/bin/base64 -d > {filename}", print_progress_bars=False
            )
        except RemoteExecutionError as exc:
            raise DHCPError(f"Failed to create snippet {filename}.") from exc

        try:
            self.refresh_dhcp()
        except DHCPRestartError:
            logger.error("Failed to refresh DHCPd, removing snippet {filename} and refreshing again.")
            self._hosts.run_sync(f"/bin/rm -v {filename}", print_output=False, print_progress_bars=False)
            self.refresh_dhcp()
            raise

    def remove_configuration(self, configuration: DHCPConfiguration, force: bool = False) -> None:
        """Remove configuration from target DHCP server then call refresh_dhcp.

        This will fail if contents do not match unless force is True.

        Arguments:
            configuration: An instance which provides content and filename for a configuration.
            force: If set to True, will remove filename regardless.

        """
        filename = f"{DHCP_TARGET_PATH}/{configuration.filename}"
        if not force:
            confsha256 = sha256(str(configuration).encode()).hexdigest()
            try:
                results = self._hosts.run_sync(
                    f"sha256sum {filename}", is_safe=True, print_output=False, print_progress_bars=False
                )
            except RemoteExecutionError as exc:
                raise DHCPError(f"Failed to checksum {filename} for safe removal.") from exc

            seen_match = False
            for _, result in RemoteHosts.results_to_list(results):
                remotesha256 = result.strip().split()[0]
                if remotesha256 != confsha256 and not self._dry_run:
                    raise DHCPError(f"Remote snippet {filename} has a mismatched SHA256, refusing to remove it.")
                seen_match = True

            if not seen_match:
                raise DHCPError(f"No output when trying to checksum snippet {filename}, refusing to remove it.")

        try:
            self._hosts.run_sync(f"/bin/rm -v {filename}", print_output=False, print_progress_bars=False)
        except RemoteExecutionError as exc:
            raise DHCPError(f"Failed to remove snippet {filename}.") from exc

        self.refresh_dhcp()

    @contextmanager
    def config(self, dhcp_config: DHCPConfiguration) -> Iterator[None]:
        """A context manager to perform actions while the given DHCP config is active.

        Arguments:
             dhcp_config: The DHCP configuration to use.

        """
        self.push_configuration(dhcp_config)
        try:
            yield
        finally:
            self.remove_configuration(dhcp_config)
