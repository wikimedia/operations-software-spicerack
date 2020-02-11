"""Netbox module."""
import logging

from typing import Dict

import pynetbox

from spicerack.exceptions import SpicerackError


NETBOX_DOMAIN = 'netbox.wikimedia.org'
logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


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
        self._api = pynetbox.api(url, token)
        self._dry_run = dry_run

        self._dcim_choices = self._get_dcim_choices(self._api)

    @staticmethod
    def _get_dcim_choices(api: pynetbox.api) -> Dict[str, Dict]:
        """Access the netbox choices API and return the choices values for the DCIM module.

        Arguments:
            api (:obj:`pynetbox.api`): An instantiated pynetbox api object.

        Returns:
            dict: A dictionary keyed by choice identifier.

        Raises:
            spicerack.netbox.NetboxAPIError: on API error.

        """
        try:
            dcim_choices = api.dcim.choices()
        except pynetbox.RequestError as ex:
            raise NetboxAPIError('error fetching dcim choices') from ex
        return dcim_choices

    @property
    def device_status_choices(self) -> Dict[str, int]:
        """Return the dictionary of device status choices.

        Returns:
           dict: the device status choices, keyed by label, with the value as the field value.

        Raises:
            spicerack.netbox.NetboxAPIError: on API errors populating the choice list.
            spicerack.netbox.NetboxError: On the choice list not being available.

        """
        if 'device:status' not in self._dcim_choices:
            raise NetboxError(
                'device:status not present in DCIM choices returned by API (keys in choices: {})'.format(
                    self._dcim_choices.keys()
                )
            )

        return {ch['label']: ch['value'] for ch in self._dcim_choices['device:status']}

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
            raise NetboxAPIError('error retrieving host') from ex
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
            raise NetboxAPIError('error retrieving VM') from ex

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
            status (str): A status name, from the keys on .device_status_choices

        Raises:
            NetboxAPIError: on API error.
            NetboxError: on parameter error.

        """
        status = status.capitalize()
        if status not in self.device_status_choices:
            raise NetboxError('{} is not an available status'.format(status))

        host = self._fetch_host(hostname)
        oldstatus = host.status

        if self._dry_run:
            logger.info('skipping host status write due to dry-run mode for %s %s -> %s', hostname, oldstatus, status)
            return

        host.status = self.device_status_choices[status]
        try:
            save_result = host.save()
        except pynetbox.RequestError as ex:
            raise NetboxAPIError(
                'failed to save host status for {} {} -> {}'.format(hostname, oldstatus, status)
            ) from ex

        if save_result:
            logger.info('wrote status for %s %s -> %s', hostname, oldstatus, status)
        else:
            raise NetboxAPIError('failed to save status for {} {} -> {}'.format(hostname, oldstatus, status))

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
