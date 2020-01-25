"""Ganeti module."""

import logging

from typing import Dict, Optional

import requests
from requests.auth import HTTPBasicAuth
from requests.exceptions import Timeout

from spicerack.constants import PUPPET_CA_PATH
from spicerack.exceptions import SpicerackError
from spicerack.remote import Remote, RemoteHosts


logger = logging.getLogger(__name__)  # pylint: disable=invalid-name

# This is the template for the SVC URL for the RAPI end point
CLUSTER_SVC_URL = 'https://ganeti01.svc.{dc}.wmnet:5080'
# These are the configured available set of rows by Ganeti cluster DC
CLUSTERS_AND_ROWS = {'eqiad': ('A', 'C'), 'codfw': ('A', 'B'), 'esams': ('OE'),
                     'ulsfo': ('1'), 'eqsin': ('1')}


class GanetiError(SpicerackError):
    """Raised on errors from Ganeti operations."""


class GanetiRAPI:
    """Class which wraps the read-only Ganeti RAPI."""

    def __init__(self, cluster_url: str, username: str, password: str, timeout: int, ca_path: str):
        """Initialize the instance.

        Arguments:
            cluster_url (str): the short name of the cluster to access.
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


class GntInstance:
    """Class that wraps gnt-instance command execution on a Ganeti cluster master host."""

    def __init__(self, master: RemoteHosts, cluster: str, instance: str):
        """Initialize the instance.

        Arguments:
            master (spicerack.remote.RemoteHosts): the Ganeti cluster master remote instance.
            cluster (str): the Ganeti cluster name.
            instance (str): the FQDN of the Ganeti VM instance to act upon.

        """
        self._master = master
        self._cluster = cluster
        self._instance = instance

    @property
    def cluster(self) -> str:
        """Getter for the Ganeti cluster property.

        Returns:
            str: the Ganeti cluster name the instance belongs to.

        """
        return self._cluster

    def shutdown(self, *, timeout: int = 2) -> None:
        """Shutdown the Ganeti VM instance.

        Arguments:
            timeout (int): time in minutes to wait for a clean shutdown before pulling the plug.

        """
        self._master.run_sync('gnt-instance shutdown --timeout={timeout} {instance}'.format(
            timeout=timeout, instance=self._instance))

    def remove(self, *, shutdown_timeout: int = 2) -> None:
        """Shutdown and remove the VM instance from the Ganeti cluster, including its disks.

        Arguments:
            shutdown_timeout (int): time in minutes to wait for a clean shutdown before pulling the plug.

        Note:
            This action requires few minutes, inform the user about the waiting time when using this method.

        """
        self._master.run_sync('gnt-instance remove --shutdown-timeout={timeout} --force {instance}'.format(
            timeout=shutdown_timeout, instance=self._instance))


class Ganeti:
    """Class which wraps all Ganeti clusters."""

    def __init__(self, username: str, password: str, timeout: int, remote: Remote):
        """Initialize the instance.

        Arguments:
            username (str): The RAPI username to use.
            password (str): The RAPI password to use.
            timeout (int): The timeout in seconds for each request to the API.
            remote (spicerack.remote.Remote): the remote instance to connect to Ganeti hosts.

        """
        self._username = username
        self._password = password
        self._timeout = timeout
        self._remote = remote

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

    def fetch_cluster_for_instance(self, fqdn: str) -> str:
        """Return the cluster name for a given FQDN if possible.

        Arguments:
            fqdn (str): The FQDN for the host to locate.

        Returns:
            str: The cluster name if found.

        Raises:
           spicerack.ganeti.GanetiError: if the host was not found in any configured cluster.

        """
        for cluster in CLUSTERS_AND_ROWS:
            cluster_rapi = self.rapi(cluster)
            try:
                cluster_rapi.fetch_instance(fqdn)
                return cluster
            except GanetiError:
                continue

        raise GanetiError("Cannot find {} in any configured cluster.".format(fqdn))

    def instance(self, instance: str, *, cluster: str = '') -> GntInstance:
        """Return an instance of GntInstance to perform RW operation on the given Ganeti VM instance.

        Arguments:
            instance (str): the FQDN of the Ganeti VM instance to act upon.
            cluster (str, optional): the name of the Ganeti cluster where to look for the instance.

        Returns:
            spicerack.ganeti.GntInstance: ready to perform RW actions.

        """
        if not cluster:
            cluster = self.fetch_cluster_for_instance(instance)
        master = self.rapi(cluster).master
        if master is None:
            raise GanetiError('Master for cluster {cluster} is None'.format(cluster=cluster))

        return GntInstance(self._remote.query(master), cluster, instance)
