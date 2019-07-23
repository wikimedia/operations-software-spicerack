"""Debmonitor module."""
import logging

import requests

from spicerack.exceptions import SpicerackError


logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


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
        self._base_url = 'https://{host}'.format(host=host)
        self._cert = cert
        self._key = key
        self._dry_run = dry_run

    def host_delete(self, hostname: str) -> None:
        """Remove a host and all its packages from Debmonitor.

        Arguments:
            host (str): the FQDN of the host to remove from Debmonitor.

        Raises:
            spicerack.debmonitor.DebmonitorError: on failure to delete. It doesn't raise if the host is already absent
                in Debmonitor.

        """
        if self._dry_run:
            logger.debug('Skip removing host %s from Debmonitor in DRY-RUN', hostname)
            return

        url = '{base}/hosts/{host}'.format(base=self._base_url, host=hostname)
        response = requests.delete(url, cert=(self._cert, self._key), timeout=3)

        if response.status_code == requests.codes['no_content']:
            logger.info('Removed host %s from Debmonitor', hostname)
        elif response.status_code == requests.codes['not_found']:
            logger.info('Host %s already missing on Debmonitor', hostname)
        else:
            raise DebmonitorError('Unable to remove host {host} from Debmonitor, got: {code} {msg}'.format(
                host=hostname, code=response.status_code, msg=response.reason))
