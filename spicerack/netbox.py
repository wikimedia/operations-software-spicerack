"""Netbox module."""
import logging

from typing import Dict

import pynetbox

from wmflib.requests import http_session

from spicerack.exceptions import SpicerackError


NETBOX_DOMAIN: str = 'netbox.wikimedia.org'
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
        self._api.http_session = http_session('.'.join((self.__module__, self.__class__.__name__)))
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
            raise NetboxAPIError('Error retrieving Netbox host') from ex

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
            raise NetboxAPIError('Error retrieving Netbox VM') from ex

        if host is None:
            raise NetboxHostNotFoundError

        return host

    def put_host_status(self, hostname: str, status: str) -> None:
        """Set the device status.

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
        status = status.lower()
        host = self._fetch_host(hostname)
        oldstatus = host.status

        if self._dry_run:
            logger.info('Skipping Netbox status update in DRY-RUN mode for host %s %s -> %s',
                        hostname, oldstatus, status)
            return

        host.status = status
        try:
            save_result = host.save()
        except pynetbox.RequestError as ex:
            raise NetboxAPIError(
                'Failed to save Netbox status for host {} {} -> {}'.format(hostname, oldstatus, status)
            ) from ex

        if save_result:
            logger.info('Netbox status updated for host %s %s -> %s', hostname, oldstatus, status)
        else:
            raise NetboxAPIError('Failed to update Netbox status for host {} {} -> {}'.format(
                hostname, oldstatus, status))

    def fetch_host_status(self, hostname: str) -> str:
        """Return the current status of a host as a string.

        Arguments:
            hostname (str): the name of the host status

        Returns:
            str: the normalized status name

        Raises:
            NetboxAPIError: on API error
            NetboxError: on parameter error
            NetboxHostNotFoundError: if the host is not found

        """
        try:
            return self._fetch_host(hostname).status
        except NetboxHostNotFoundError:
            return self._fetch_virtual_machine(hostname).status

    def fetch_host_detail(self, hostname: str) -> Dict:
        """Return a dict containing details about the host.

        Arguments:
            hostname (str): the name of the host to retrieve.

        Returns:
            dict: data about the host

        Raises:
            NetboxAPIError: on API error
            NetboxError: on parameter error
            NetboxHostNotFoundError: if the host is not found

        """
        is_virtual = False
        vm_cluster = 'N/A'
        try:
            host = self._fetch_host(hostname)
        except NetboxHostNotFoundError:
            host = self._fetch_virtual_machine(hostname)
            is_virtual = True
            vm_cluster = host.cluster.name

        ret = host.serialize()
        ret['is_virtual'] = is_virtual
        ret['ganeti_cluster'] = vm_cluster
        return ret
