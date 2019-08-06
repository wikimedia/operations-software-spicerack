"""Ganeti module."""

import logging

from typing import Dict, Optional

import requests
from requests.auth import HTTPBasicAuth
from requests.exceptions import Timeout

from spicerack.constants import PUPPET_CA_PATH
from spicerack.exceptions import SpicerackError


logger = logging.getLogger(__name__)  # pylint: disable=invalid-name

# This is the template for the SVC URL for the RAPI end point
CLUSTER_SVC_URL = 'https://ganeti01.svc.{dc}.wmnet:5080'
# These are the configured available set of rows by Ganeti cluster DC
CLUSTERS_AND_ROWS = {'eqiad': ('A', 'C'), 'codfw': ('A', 'B')}


class GanetiError(SpicerackError):
    """Raised on errors from Ganeti operations."""


class GanetiRAPI:
    """Class which wraps the read-only Ganeti RAPI."""

    def __init__(self, cluster_url: str, username: str, password: str, timeout: int, ca_path: str):
        """Initialize the instance.

        Arguments:
            cluster (str): the short name of the cluster to access.
            username (str): the RAPI user name
            password (str): the RAPI user's password
            timeout (int): the timeout in seconds for each request
            ca_path (str): the path to the signing certificate authority

        """
        self._auth = HTTPBasicAuth(username, password)
        self._ca_path = ca_path
        self._url = cluster_url
        self._timeout = timeout

    def _api_get_request(self, *targets: str) -> Dict:
        """Perform a RAPI request.

        Arguments:
           *targets: The path components of the request (minus the /2/ part of the path)

        Returns:
           dict: The decoded JSON response

        Raises:
           spicerack.ganeti.GanetiError: on non-200 responses

        """
        full_url = '/'.join([self._url, '2'] + list(targets))
        try:
            result = requests.get(full_url, auth=self._auth, verify=self._ca_path, timeout=self._timeout)
        except Timeout as ex:
            raise GanetiError('Timeout performing request to RAPI') from ex

        if result.status_code != 200:
            raise GanetiError('Non-200 from API: {}: {}'.format(result.status_code, result.text))

        return result.json()

    @property
    def info(self) -> Dict:
        """Return complete cluster information.

        Returns:
            dict: Cluster information dictionary

        Raises:
            spicerack.ganeti.GanetiError: API errors

        """
        return self._api_get_request('info')

    @property
    def master(self) -> Optional[str]:
        """Return the internal name for the current ganeti master node.

        Returns:
            str: The hostname of the master node (or None if the data is missing).

        Raises:
            spicerack.ganeti.GanetiError: API errors

        """
        return self.info.get('master')

    def fetch_instance(self, fqdn: str) -> Dict:
        """Return full information about an instance.

        Arguments:
           fqdn: the FQDN of the instance in question

        Returns:
           dict: host information

        Raises:
           spicerack.ganeti.GanetiError: API errors

        """
        return self._api_get_request('instances', fqdn)

    def fetch_instance_mac(self, fqdn: str) -> str:
        """Convenience method to return the 0th adapter's MAC address for an instance.

        Note that we don't allow the creation of instances with more than one MAC address at this time.

        Arguments:
           fqdn: the FQDN of the instance in question

        Returns:
           str: MAC address

        Raises:
           GanetiError: API errors

        """
        instance_info = self.fetch_instance(fqdn)
        if 'nic.macs' not in instance_info or not instance_info['nic.macs']:
            raise GanetiError("Can't find any MACs for instance")

        return instance_info['nic.macs'][0]


class Ganeti:
    """Class which wraps all Ganeti clusters."""

    def __init__(self, username: str, password: str, timeout: int):
        """Initialize the instance.

        Arguments:
            username (str): The RAPI username to use.
            password (str): The RAPI password to use.
            timeout (int): The timeout in seconds for each request to the API.

        """
        self._username = username
        self._password = password
        self._timeout = timeout

    def rapi(self, cluster: str) -> GanetiRAPI:
        """Return a RAPI object for a particular cluster.

        Arguments:
            cluster (str): the name of the cluster to get a RAPI for.

        Returns:
            spicerack.ganeti.GanetiRAPI: the RAPI interface object

        Raises:
            spicerack.ganeti.GanetiError: on an invalid cluster name

        """
        if cluster not in CLUSTERS_AND_ROWS:
            raise GanetiError('Cannot find cluster {} (expected {}).'.format(cluster, tuple(CLUSTERS_AND_ROWS.keys())))

        cluster_url = CLUSTER_SVC_URL.format(dc=cluster)

        return GanetiRAPI(cluster_url, self._username, self._password, self._timeout, PUPPET_CA_PATH)
