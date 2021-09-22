"""Management module."""
import logging
import re
import warnings

from wmflib.constants import ALL_DATACENTERS
from wmflib.dns import Dns, DnsError

from spicerack.constants import INTERNAL_TLD, MANAGEMENT_SUBDOMAIN
from spicerack.exceptions import SpicerackError

DC_HOSTNAME_PATTERN: re.Pattern = re.compile(r"(?P<dc_id>[1-5])[0-9]{3}$")
logger = logging.getLogger(__name__)


class ManagementError(SpicerackError):
    """Custom exception class for errors of the Management class."""


class Management:
    """Class to interact with management FQDNs."""

    def __init__(self, dns: Dns) -> None:
        """Initialize the instance.

        .. deprecated:: v1.0.0
            use :py:class:`spicerack.netbox.NetboxServer` instead that has a ``mgmt_fqdn``
            and ``asset_tag_fqdn`` properties.

        Arguments:
            dns (wmflib.dns.Dns): the instance to use for DNS resolution.

        """
        self._dns = dns
        warnings.warn("Deprecated class, use spicearack.netbox_server() instead", DeprecationWarning)

    def get_fqdn(self, hostname: str) -> str:
        """Get the FQDN of the management interface.

        Arguments:
            hostname (str): the FQDN of the hostname for which the management FQDN should be returned.

        Returns:
            str: the FQDN of the management interface.

        Raises:
            spicerack.management.ManagementError: if unable to find or verify the FQDN of the management interface.

        """
        # TODO: replace this querying Netbox API
        if hostname.split(".")[-1] == INTERNAL_TLD:
            mgmt = self._internal_mgmt_fqdn(hostname)
        else:
            mgmt = self._external_mgmt_fqdn(hostname)

        logger.debug("Management FQDN for %s is %s", hostname, mgmt)
        return mgmt

    def _is_valid_fqdn(self, fqdn: str) -> bool:
        """Check if the calculated management FQDN exists in the local DNS.

        Arguments:
            fqdn (str): the management FQDN to validate.

        Returns:
            bool: :py:data:`True` if the FQDN is valid, :py:data:`False` otherwise.

        """
        try:
            self._dns.resolve_ipv4(fqdn)
            return True
        except DnsError:
            return False

    def _internal_mgmt_fqdn(self, hostname: str) -> str:
        """Generate the management FQDN for the given internal hostname.

        Arguments:
            hostname (str): the FQDN of the internal host to generate the management FQDN for.

        Returns:
            str: the management FQDN.

        Raises:
            spicerack.management.ManagementError: if the generated management FQDN is invalid.

        """
        parts = hostname.split(".")
        parts.insert(-2, MANAGEMENT_SUBDOMAIN)  # Direct injection of the management subdomain
        mgmt = ".".join(parts)
        if not self._is_valid_fqdn(mgmt):
            raise ManagementError(f"Invalid management FQDN {mgmt} for {hostname}")

        return mgmt

    def _external_mgmt_fqdn(self, hostname: str) -> str:
        """Generate the management FQDN for the given external hostname.

        Arguments:
            hostname (str): the FQDN of the external host to generate the management FQDN for.

        Returns:
            str: the management FQDN.abs

        Raises:
            spicerack.management.ManagementError: if unable to find a valid management FQDN across all DCs.

        """
        parts = hostname.split(".")
        hostname_search = DC_HOSTNAME_PATTERN.search(parts[-3])
        if hostname_search is not None:
            # Detection of the datacenter from the hostname
            datacenters = [ALL_DATACENTERS[int(hostname_search.groupdict()["dc_id"]) - 1]]
        else:
            datacenters = list(ALL_DATACENTERS)

        # Search the matching management valid hostname in all datacenters
        for dc in datacenters:
            mgmt = ".".join(parts[:-2] + [MANAGEMENT_SUBDOMAIN, dc, INTERNAL_TLD])
            if self._is_valid_fqdn(mgmt):
                break
        else:
            raise ManagementError(
                f"Unable to find management FQDN for host {hostname} in these datacenters: {datacenters}"
            )

        return mgmt
