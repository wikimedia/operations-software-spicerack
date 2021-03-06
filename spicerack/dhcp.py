"""Provide an interface for manipulating DHCP configuration snippets for our dynamic/temporary DHCP system."""

import base64
import re
import textwrap
from abc import ABC, abstractmethod, abstractproperty
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from ipaddress import IPv4Address
from typing import Iterator, Optional

from wmflib.constants import ALL_DATACENTERS

from spicerack.exceptions import SpicerackError
from spicerack.remote import RemoteExecutionError, RemoteHosts

DHCP_TARGET_PATH = "/etc/dhcp/automation"
"""str: The path to the top of the DHCPd automation directory."""


MGMT_HOSTNAME_RE = r"\.mgmt\.{dc}\.wmnet"
"""str: A regular expression when formatted with a `dc` parameter will match a management hostname."""


class DHCPError(SpicerackError):
    """Base class for DHCP object errors."""


class DHCPRestartError(DHCPError):
    """Raised when the includes generator on target machine returns non-zero."""


class DHCPConfiguration(ABC):
    """An abstract class which defines the interface for the DHCP configuration generators."""

    @abstractmethod
    def __str__(self) -> str:
        """Return a string of this configuration rendered."""

    @abstractproperty
    def filename(self) -> str:
        """Return a string of the proposed filename for this configuration, from the automation directory."""


@dataclass
class DHCPConfOpt82(DHCPConfiguration):
    """A configuration generator for host installation DHCP entries."""

    hostname: str
    fqdn: str
    switch_hostname: str
    switch_port: str
    vlan: str
    ttys: int = 1
    distro: Optional[str] = None

    _template = """
    host {hostname} {{
        host-identifier option agent.circuit-id "{switch_hostname}:{switch_port}:{vlan}";
        fixed-address {fqdn};
        {pathprefix}
    }}
    """

    def __str__(self) -> str:
        """Return the rendered DHCP configuration snippet."""
        pathprefix = ""
        if self.distro is not None:
            pathprefix = f"""option pxelinux.pathprefix "http://apt.wikimedia.org/tftpboot/{self.distro}-installer/";"""
        return textwrap.dedent(
            self._template.format(
                hostname=self.hostname,
                switch_hostname=self.switch_hostname,
                switch_port=self.switch_port,
                vlan=self.vlan,
                fqdn=self.fqdn,
                pathprefix=pathprefix,
            )
        )

    @property
    def filename(self) -> str:
        """Return the proposed filename based on this configuration."""
        return f"opt82-entries.ttyS{self.ttys}-115200/{self.fqdn}.conf"


@dataclass
class DHCPConfMgmt(DHCPConfiguration):
    """A configuration for management network DHCP entries."""

    datacenter: str
    serial: str
    fqdn: str
    ip_address: IPv4Address

    _template = """
    class "{fqdn}" {{
        match if (option host-name = "iDRAC-{serial}")
    }}
    pool {{
        allow members of "{fqdn}";
        range {ip_address} {ip_address};
    }}
    """

    def __post_init__(self) -> None:
        """Validate parameters."""
        if self.datacenter not in ALL_DATACENTERS:
            raise DHCPError(f"invalid datacenter {self.datacenter}")
        if not re.search(MGMT_HOSTNAME_RE.format(dc=self.datacenter), self.fqdn):
            raise DHCPError(f"hostname does not look like a valid management hostname: {self.fqdn}")

    def __str__(self) -> str:
        """Return the rendered DHCP configuration snippet."""
        return textwrap.dedent(self._template.format(fqdn=self.fqdn, serial=self.serial, ip_address=self.ip_address))

    @property
    def filename(self) -> str:
        """Return the filename that corresponds to this configuration."""
        return f"""mgmt-{self.datacenter}/{self.fqdn}.conf"""


class DHCP:
    """A class which provides tools for manipulating DHCP configuration snippets by data center."""

    def __init__(self, hosts: RemoteHosts):
        """Create a DHCP instance.

        Arguments:
            hosts (`spicerack.remote.RemoteHosts`): The target datacenter's install servers.

        """
        if len(hosts) < 1:
            raise DHCPError("No target hosts provided.")
        self._hosts = hosts

    def refresh_dhcp(self) -> None:
        """Regenerate includes on target data center and restart DHCP, or raise if failure at any stage."""
        try:
            self._hosts.run_sync("/usr/local/sbin/dhcpincludes -r commit")
        except RemoteExecutionError as exc:
            raise DHCPRestartError("restarting generating dhcp config or restarting dhcpd failed") from exc

    def push_configuration(self, configuration: DHCPConfiguration) -> None:
        """Push a specified file with specified content to DHCP server and call refresh_dhcp.

        Arguments:
            configuration (`spicerack.dhcp.DHCPConfiguration`): An instance which provides content and filename for a
                                                                configuration.

        """
        filename = configuration.filename
        try:
            self._hosts.run_sync(f"/usr/bin/test '!' '-e'  {DHCP_TARGET_PATH}/{filename}", is_safe=True)
        except RemoteExecutionError as exc:
            raise DHCPError(f"target file {filename} exists") from exc

        b64encoded = base64.b64encode(str(configuration).encode()).decode()
        try:
            self._hosts.run_sync(f"/bin/echo '{b64encoded}' | /usr/bin/base64 -d > {DHCP_TARGET_PATH}/{filename}")
        except RemoteExecutionError as exc:
            raise DHCPError(f"target file {filename} failed to be created.") from exc

        self.refresh_dhcp()

    def remove_configuration(self, configuration: DHCPConfiguration, force: bool = False) -> None:
        """Remove configuration from target DHCP server then call refresh_dhcp.

        This will fail if contents do not match unless force is True.

        Arguments:
            configuration (spicerack.dhcp.DHCPConfiguration): An instance which provides content and filename for a
                                                              configuration.
            force (bool, default False): If set to True, will remove filename regardless.

        """
        if not force:
            confsha256 = sha256(str(configuration).encode()).hexdigest()
            try:
                results = self._hosts.run_sync(f"sha256sum {DHCP_TARGET_PATH}/{configuration.filename}", is_safe=True)
            except RemoteExecutionError as exc:
                raise DHCPError(f"Can't test {configuration.filename} for removal.") from exc
            seen_match = False
            for _, result in RemoteHosts.results_to_list(results):
                remotesha256 = result.strip().split()[0]
                if remotesha256 != confsha256:
                    raise DHCPError(f"Remote {configuration.filename} has a mismatched SHA256, refusing to remove.")
                seen_match = True
            if not seen_match:
                raise DHCPError("Did not get any result trying to get SHA256, refusing to attempt to remove.")
        try:
            self._hosts.run_sync(f"/bin/rm -v {DHCP_TARGET_PATH}/{configuration.filename}")
        except RemoteExecutionError as exc:
            raise DHCPError(f"Can't remove {configuration.filename}.") from exc

        self.refresh_dhcp()

    @contextmanager
    def dhcp_push(self, dhcp_config: DHCPConfiguration) -> Iterator[None]:
        """Adapt the DHCP configuration manager to context manager.

        Arguments:
             dhcp_config (spicerack.dhcp.DHCPConfiguration intance): The configuration instance to operate with.

        """
        self.push_configuration(dhcp_config)
        try:
            yield
        finally:
            self.remove_configuration(dhcp_config)
