"""Provide an interface for manipulating DHCP configuration snippets for our dynamic/temporary DHCP system."""

import base64
import logging
import re
import struct
import textwrap
from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from hashlib import sha256
from ipaddress import IPv4Address
from typing import Union

from wmflib.constants import ALL_DATACENTERS

from spicerack.exceptions import SpicerackError
from spicerack.locking import Lock, NoLock
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

    dhcp_filename: str = ""
    dhcp_filename_exclude_vendor: str = ""
    dhcp_options: dict[str, str] = {}
    distro: str = ""
    media_type: str = "installer"

    def __post_init__(self) -> None:
        """According to Python's dataclass API to validate/augment the arguments.

        See Also:
           https://docs.python.org/3/library/dataclasses.html#post-init-processing

        """
        if not self.dhcp_options and self.distro:
            self.dhcp_options["pxelinux.pathprefix"] = (
                f"http://apt.wikimedia.org/tftpboot/{self.distro}-{self.media_type}/"
            )

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

    @property
    def rendered_dhcp_options(self) -> str:
        """Return the DHCP options config strings.

        Returns:
            A string representing the DHCP options config provided.

        """
        options = ""
        for key, value in self.dhcp_options.items():
            options += f'\n        option {key} "{value}";'
        return options

    @property
    def rendered_dhcp_filename(self) -> str:
        """Return the DHCP filename config string.

        Returns:
            A string representing the DHCP filename config provided.

        """
        if self.dhcp_filename:
            if self.dhcp_filename_exclude_vendor:
                rendered_filename = textwrap.dedent(
                    f"""\
                    if option vendor-class-identifier = "{self.dhcp_filename_exclude_vendor}" {{
                        filename "";
                    }} else {{
                        filename "{self.dhcp_filename}";
                    }}"""
                )
            else:
                rendered_filename = f'filename "{self.dhcp_filename}";'
            return "\n" + textwrap.indent(rendered_filename, "        ")
        return ""


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
        distro: the codename of the Debian distribution to use for the PXE
        installer (empty string or None is allowed and removes the related dhcp
        default options from the config).
        media_type: the media type to use e.g. ``installer``, ``installer-11.0``, ``rescue``.
        dhcp_filename: the DHCP filename option to set.
        dhcp_filename_exclude_vendor: vendor to exclude from sending over the filename, e.g. d-i
        dhcp_options: a dictionary of DHCP option settings to use.

    """

    hostname: str
    ipv4: IPv4Address
    switch_hostname: str
    switch_iface: str
    vlan: str
    ttys: int
    distro: str
    media_type: str = "installer"
    dhcp_filename: str = ""
    dhcp_filename_exclude_vendor: str = ""
    dhcp_options: dict[str, str] = field(default_factory=dict)

    _template: str = """
    host {s.hostname} {{
        host-identifier option agent.circuit-id "{s.switch_hostname}:{s.switch_iface}:{s.vlan}";
        fixed-address {s.ipv4};{s.rendered_dhcp_filename}{s.rendered_dhcp_options}
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
        distro: the codename of the Debian distribution to use for the PXE
        installer (empty string or None is allowed and removes the related dhcp
        default options from the config).
        media_type: The media type to use e.g. installer, installer-11.0, rescue
        dhcp_filename: the DHCP filename option to set.
        dhcp_filename_exclude_vendor: vendor to exclude from sending over the filename, e.g. d-i
        dhcp_options: a dictionary of DHCP option settings to use.

    """

    hostname: str
    ipv4: IPv4Address
    mac: str
    ttys: int
    distro: str
    media_type: str = "installer"
    dhcp_filename: str = ""
    dhcp_filename_exclude_vendor: str = ""
    dhcp_options: dict[str, str] = field(default_factory=dict)

    _template: str = """
    host {s.hostname} {{
        hardware ethernet {s.mac};
        fixed-address {s.ipv4};{s.rendered_dhcp_filename}{s.rendered_dhcp_options}
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
        super().__post_init__()

    @property
    def filename(self) -> str:
        """Return the proposed filename based on this configuration."""
        return f"ttyS{self.ttys}-115200/{self.hostname}.conf"


@dataclass(frozen=True)
class DHCPConfUUID(DHCPConfiguration):
    """A configuration generator for host installation DHCP entries via SMBIOS UUIDs.

    Arguments:
        hostname: the hostname to generate the DHCP matching block for.
        ipv4: the IPv4 to be assigned to the host.
        uuid: the SMBIOS UUID of the host.
        ttys: which ttyS to use for this host, accepted values are 0 and 1.
        distro: the codename of the Debian distribution to use for the PXE
        installer (empty string or None is allowed and removes the related dhcp
        default options from the config).
        media_type: The media type to use e.g. installer, installer-11.0, rescue
        dhcp_filename: the DHCP filename option to set.
        dhcp_filename_exclude_vendor: vendor to exclude from sending over the filename, e.g. d-i
        dhcp_options: a dictionary of DHCP option settings to use.

    """

    hostname: str
    ipv4: IPv4Address
    uuid: str
    ttys: int
    distro: str
    media_type: str = "installer"
    dhcp_filename: str = ""
    dhcp_filename_exclude_vendor: str = ""
    dhcp_options: dict[str, str] = field(default_factory=dict)

    # The leading 00 on the pxe-client-id is needed to match the UUID type
    # code, which is always 0 in practice for Option 97 UUIDS
    _template: str = """
    host {s.hostname} {{
        host-identifier option pxe-client-id 00:{pxe_client_id};
        fixed-address {s.ipv4};{s.rendered_dhcp_filename}{s.rendered_dhcp_options}
    }}
    """

    def __str__(self) -> str:
        """Return the rendered DHCP configuration snippet."""
        return textwrap.dedent(self._template.format(s=self, pxe_client_id=self._uuid_to_pxe_client_id(self.uuid)))

    @property
    def filename(self) -> str:
        """Return the proposed filename based on this configuration."""
        return f"ttyS{self.ttys}-115200/{self.hostname}.conf"

    # Converts a string SMBIOS UUID to the pxe-client-id found in DHCP Option
    # 97. The first three parts of the string format UUID are in litte endian
    # order, however the data in the DHCP packet is all big endian[1]. The
    # output of this function is a hex string separated by colons, which is the
    # form needed to match a host with a dhcp host-identifier keyword.
    # [1]: https://devblogs.microsoft.com/oldnewthing/20220928-00/?p=107221
    def _uuid_to_pxe_client_id(self, uuid: str) -> str:
        """Return a pxe-client-id suitable for a DHCP config."""
        parts = uuid.split("-")
        le = bytes.fromhex(parts[0] + parts[1] + parts[2])
        lev = struct.unpack("<LHH", le)
        be = bytes.fromhex(parts[3] + parts[4])
        bev = struct.unpack(">HLH", be)
        be_uuid = struct.pack(">LHHHLH", *lev, *bev)
        return bytes.hex(be_uuid, ":")


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
    distro: str = ""  # unused
    dhcp_options: dict[str, str] = field(default_factory=dict)

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
        super().__post_init__()

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

    def __init__(self, hosts: RemoteHosts, *, datacenter: str, lock: Union[Lock, NoLock], dry_run: bool = True):
        """Create a DHCP instance.

        Arguments:
            hosts: the target datacenter's install servers.
            datacenter: the datacenter name.
            lock: the locking instance to use to acquire locks around delicate operations.
            dry_run: whether this is a DRY-RUN.

        """
        if len(hosts) < 1:
            raise DHCPError("No target hosts provided.")

        if datacenter not in ALL_DATACENTERS:
            raise DHCPError(f"Invalid datacenter {datacenter}, must be one of {ALL_DATACENTERS}.")

        self._dry_run = dry_run
        self._lock = lock
        self._datacenter = datacenter
        self._hosts = hosts
        # Key to be used to acquire an exclusive lock on a per-DC basis
        self._lock_key = f"{self.__module__}.{self.__class__.__name__}:{self._datacenter}"

    def _refresh_dhcp(self) -> None:
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
        b64encoded = base64.b64encode(str(configuration).encode()).decode()

        with self._lock.acquired(self._lock_key, concurrency=1, ttl=120):
            try:
                self._hosts.run_sync(
                    f"/bin/echo '{b64encoded}' | /usr/bin/base64 -d > {filename}", print_progress_bars=False
                )
            except RemoteExecutionError as exc:
                raise DHCPError(f"Failed to create snippet {filename}.") from exc

            try:
                self._refresh_dhcp()
            except DHCPRestartError:
                logger.error("Failed to refresh DHCPd, removing snippet {filename} and refreshing again.")
                self._hosts.run_sync(f"/bin/rm -v {filename}", print_output=False, print_progress_bars=False)
                self._refresh_dhcp()
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

        with self._lock.acquired(self._lock_key, concurrency=1, ttl=60):
            try:
                self._hosts.run_sync(f"/bin/rm -v {filename}", print_output=False, print_progress_bars=False)
            except RemoteExecutionError as exc:
                raise DHCPError(f"Failed to remove snippet {filename}.") from exc

            self._refresh_dhcp()

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
