"""Debmonitor module."""
import logging

import requests
from wmflib.requests import http_session

from spicerack.exceptions import SpicerackError

logger = logging.getLogger(__name__)


class DebmonitorError(SpicerackError):
    """Custom exception class for errors of the Debmonitor class."""


class Debmonitor:
    """Class to interact with a Debmonitor website."""

    def __init__(self, host: str, cert: str, key: str, dry_run: bool = True) -> None:
        """Initialize the instance.

        Arguments:
            host (str): the hostname of the Debmonitor server (without protocol).
            cert (str): the path to the TLS certificate to use to authenticate on Debmonitor.
            key (str): the path to the TLS key to use to authenticate on Debmonitor.
            dry_run (bool, optional): whether this is a DRY-RUN.

        """
        self._base_url: str = f"https://{host}"
        self._cert = cert
        self._key = key
        self._dry_run = dry_run
        self._http_session = http_session(".".join((self.__module__, self.__class__.__name__)))

    def host_delete(self, hostname: str) -> None:
        """Remove a host and all its packages from Debmonitor.

        Arguments:
            host (str): the FQDN of the host to remove from Debmonitor.

        Raises:
            spicerack.debmonitor.DebmonitorError: on failure to delete. It doesn't raise if the host is already absent
                in Debmonitor.

        """
        if self._dry_run:
            logger.debug("Skip removing host %s from Debmonitor in DRY-RUN", hostname)
            return

        url = f"{self._base_url}/hosts/{hostname}"
        response = self._http_session.delete(url, cert=(self._cert, self._key))

        if response.status_code == requests.codes["no_content"]:
            logger.info("Removed host %s from Debmonitor", hostname)
        elif response.status_code == requests.codes["not_found"]:
            logger.info("Host %s already missing on Debmonitor", hostname)
        else:
            raise DebmonitorError(
                f"Unable to remove host {hostname} from Debmonitor, got: {response.status_code} {response.reason}"
            )
