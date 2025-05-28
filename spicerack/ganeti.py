"""Ganeti module."""

import logging
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv6Address
from typing import Optional, Union

from requests.auth import HTTPBasicAuth
from requests.exceptions import RequestException
from wmflib.requests import http_session

from spicerack.constants import WMF_CA_BUNDLE_PATH
from spicerack.exceptions import SpicerackError
from spicerack.netbox import Netbox
from spicerack.remote import Remote, RemoteHosts

logger = logging.getLogger(__name__)

RAPI_URL_FORMAT: str = "https://{cluster}:5080"
"""The template string to construct the Ganeti RAPI URL."""
INSTANCE_LINKS: tuple[str, ...] = ("public", "private", "analytics", "sandbox")
"""The list of possible instance link types."""
STORAGE_TYPES = ("drbd", "plain")
"""The possible values for the instance storage type."""


class GanetiError(SpicerackError):
    """Raised on errors from Ganeti operations."""


@dataclass(frozen=True)
class GanetiCluster:
    """Represents a Ganeti cluster with all the related attributes.

    Arguments:
        name: the Ganeti cluster short name, equivalent to the Netbox cluster group name.
        fqdn: the FQDN of the Ganeti cluster VIP.
        rapi: the Ganeti RAPI endpoint URL to connect to.
        routed: Whether the cluster's network is in routed mode or switched mode.

    """

    name: str
    fqdn: str
    rapi: str
    routed: bool


@dataclass(frozen=True)
class GanetiGroup:
    """Represents a Ganeti group with all the related attributes.

    Arguments:
        name: the Ganeti group name, equivalent to the Netbox cluster name.
        site: the Datacenter of the Ganeti group short name, equivalent of the Netbox site slug.
        cluster: the Ganeti cluster the group belongs to.

    """

    name: str
    site: str
    cluster: GanetiCluster


class GanetiRAPI:
    """Class which wraps the read-only Ganeti RAPI."""

    def __init__(self, cluster_url: str, username: str, password: str, timeout: int, ca_path: str):
        """Initialize the instance.

        Arguments:
            cluster_url: the URL of the RAPI endpoint.
            username: the RAPI user name
            password: the RAPI user's password
            timeout: the timeout in seconds for each request
            ca_path: the path to the signing certificate authority

        """
        self._url = cluster_url
        self._http_session = http_session(".".join((self.__module__, self.__class__.__name__)), timeout=timeout)
        self._http_session.auth = HTTPBasicAuth(username, password)
        self._http_session.verify = ca_path

    def _api_get_request(self, *targets: str) -> dict:
        """Perform a RAPI request and return its JSON decoded response.

        Arguments:
           *targets: The path components of the request (minus the /2/ part of the path).

        Raises:
           spicerack.ganeti.GanetiError: on non-200 responses.

        """
        full_url = "/".join([self._url, "2"] + list(targets))
        try:
            result = self._http_session.get(full_url)
        except RequestException as ex:
            raise GanetiError("Error while performing request to RAPI") from ex

        if result.status_code != 200:
            raise GanetiError(f"Non-200 from API: {result.status_code}: {result.text}")

        return result.json()

    @property
    def info(self) -> dict:
        """Return the complete cluster information.

        Raises:
            spicerack.ganeti.GanetiError: on API errors.

        """
        return self._api_get_request("info")

    @property
    def master(self) -> Optional[str]:
        """Return the internal name for the current ganeti master node or none if the data is missing.

        Raises:
            spicerack.ganeti.GanetiError: on API errors.

        """
        return self.info.get("master")

    def fetch_instance(self, fqdn: str) -> dict:
        """Return full information about an instance.

        Arguments:
           fqdn: the FQDN of the instance in question.

        Raises:
           spicerack.ganeti.GanetiError: on API errors.

        """
        return self._api_get_request("instances", fqdn)

    def fetch_instance_mac(self, fqdn: str) -> str:
        """Convenience method to return the 0th adapter's MAC address for an instance.

        Note that we don't allow the creation of instances with more than one MAC address at this time.

        Arguments:
           fqdn: the FQDN of the instance in question.

        Raises:
            spicerack.ganeti.GanetiError: on API errors.

        """
        instance_info = self.fetch_instance(fqdn)
        if "nic.macs" not in instance_info or not instance_info["nic.macs"]:
            raise GanetiError("Can't find any MACs for instance")

        return instance_info["nic.macs"][0]

    def groups(self, bulk: bool = False) -> dict:
        """Get a list of Cluster groups.

        Arguments:
            bulk: if true set bulk=1 to return detailed information.
                see https://docs.ganeti.org/docs/ganeti/2.9/html/rapi.html#bulk

        """
        target = "groups?bulk=1" if bulk else "groups"
        return self._api_get_request(target)

    def nodes(self, bulk: bool = False) -> dict:
        """Get a list of Cluster nodes.

        Arguments:
            bulk: if true set bulk=1 to return detailed information.
                see https://docs.ganeti.org/docs/ganeti/2.9/html/rapi.html#bulk

        """
        target = "nodes?bulk=1" if bulk else "nodes"
        return self._api_get_request(target)


class GntInstance:
    """Class that wraps gnt-instance command execution on a Ganeti cluster master host."""

    def __init__(self, master: RemoteHosts, cluster: str, instance: str):
        """Initialize the instance.

        Arguments:
            master: the Ganeti cluster master remote instance.
            cluster: the Ganeti cluster name.
            instance: the FQDN of the Ganeti VM instance to act upon.

        """
        self._master = master
        self._cluster = cluster
        self._instance = instance

    @property
    def cluster(self) -> str:
        """Getter for the Ganeti cluster name the instance belongs to."""
        return self._cluster

    def shutdown(self, *, timeout: int = 2) -> None:
        """Shutdown the Ganeti VM instance.

        Arguments:
            timeout: time in minutes to wait for a clean shutdown before pulling the plug.

        """
        logger.info("Shutting down VM %s in cluster %s", self._instance, self._cluster)
        self._master.run_sync(f"gnt-instance shutdown --force --timeout={timeout} {self._instance}")

    def startup(self) -> None:
        """Start the Ganeti VM instance."""
        logger.info("Starting VM %s in cluster %s", self._instance, self._cluster)
        self._master.run_sync(f"gnt-instance startup --force {self._instance}")

    def set_boot_media(self, boot: str) -> None:
        """Set the boot media of the Ganeti VM to the given media.

        Arguments:
            boot: the boot media to use. Use `disk` to boot from disk and `network` to boot from PXE.

        """
        self._master.run_sync(f"gnt-instance modify --hypervisor-parameters=boot_order={boot} {self._instance}")
        logger.info("Set boot media to %s for VM %s in cluster %s", boot, self._instance, self._cluster)

    def remove(self, *, shutdown_timeout: int = 2) -> None:
        """Shutdown and remove the VM instance from the Ganeti cluster, including its disks.

        Arguments:
            shutdown_timeout: time in minutes to wait for a clean shutdown before pulling the plug.

        Note:
            This action requires few minutes, inform the user about the waiting time when using this method.

        """
        logger.info(
            "Removing VM %s in cluster %s. This may take a few minutes.",
            self._instance,
            self._cluster,
        )
        self._master.run_sync(f"gnt-instance remove --shutdown-timeout={shutdown_timeout} --force {self._instance}")

    def add(  # pylint: disable=too-many-arguments
        self,
        *,
        group: str,
        vcpus: int,
        memory: Union[int, float],
        disk: int,
        storage_type: str,
        net: Union[str, IPv4Address],
        ip6: IPv6Address,
    ) -> None:
        """Create the VM for the instance in the Ganeti cluster with the specified characteristic.

        Arguments:
            group: the Ganeti group that matches the Datacenter physical row or rack where to allocate the instance.
            vcpus: the number of virtual CPUs to assign to the instance.
            memory: the amount of RAM to assign to the instance in gigabytes.
            disk: the amount of disk to assign to the instance in gigabytes.
            storage_type: the storage type for the VM (one of :py:const:`spicerack.ganeti.STORAGE_TYPES`).
            net: either the IP or the type of network link to use (from :py:const:`spicerack.ganeti.INSTANCE_LINKS`).
            ip6: the IPv6 assigned to the VM.

        Raises:
            spicerack.ganeti.GanetiError: on parameter validation error.

        Note:
            This action requires few minutes, inform the user about the waiting time when using this method.

        """
        kvm_extra = ""
        if isinstance(net, str):
            if net not in INSTANCE_LINKS:
                raise GanetiError(f"Invalid link '{net}', expected one of: {INSTANCE_LINKS}")
            net_option = f"0:link={net}"
        elif isinstance(net, IPv4Address):
            net_option = f"0:ip={net}"
            kvm_extra = f',kvm_extra="-fw_cfg name=opt/ip\\,string={net} -fw_cfg name=opt/ip6\\,string={ip6}"'
        else:
            raise GanetiError(f"'{net}' must be an IPv4Address or one of: {INSTANCE_LINKS}.")

        if not isinstance(ip6, IPv6Address):
            raise GanetiError(f"'{ip6}' must be an IPv6Address object.")

        if storage_type not in STORAGE_TYPES:
            raise GanetiError(f"Invalid storage type '{storage_type}', expected one of: {STORAGE_TYPES}.")

        local_vars = locals()
        for var_label in ("vcpus", "memory", "disk"):
            if local_vars[var_label] <= 0:
                raise GanetiError(
                    f"Invalid value '{local_vars[var_label]}' for {var_label}, expected positive integer."
                )

        memory_mb = int(memory * 1024)
        command = (
            "gnt-instance add"
            f" -t {storage_type}"
            " -I hail"
            f" --net {net_option}"
            f" --hypervisor-parameters=kvm:boot_order=network{kvm_extra}"
            " -o debootstrap+default"
            " --no-install"
            " --no-wait-for-sync"
            f" -g {group}"
            f" -B vcpus={vcpus},memory={memory_mb}m"
            f" --disk 0:size={disk}g"
            f" {self._instance}"
        )

        logger.info(
            (
                "Creating VM %s in cluster %s with group=%s vcpus=%d memory=%dGB disk=%dGB net=%s. "
                "This may take a few minutes."
            ),
            self._instance,
            self._cluster,
            group,
            vcpus,
            memory,
            disk,
            net,
        )

        results = self._master.run_sync(command, print_output=True)
        for _, output in results:
            logger.debug(output.message().decode())


class Ganeti:
    """Class which wraps all Ganeti clusters operations."""

    def __init__(self, username: str, password: str, timeout: int, remote: Remote, netbox: Netbox):
        """Initialize the instance.

        Arguments:
            username: The RAPI username to use.
            password: The RAPI password to use.
            timeout: The timeout in seconds for each request to the API.
            remote: the remote instance to connect to Ganeti hosts.
            netbox: the Netbox instance to gather data from the source of truth.

        """
        self._username = username
        self._password = password
        self._timeout = timeout
        self._remote = remote
        self._netbox = netbox

    def get_cluster(self, name: str) -> GanetiCluster:
        """Get a GanetiCluster instance for the given cluster name.

        Arguments:
            name: the name of the Ganeti cluster, equivalent to the cluster group in Netbox.

        Raises:
            spicerack.ganeti.GanetiError: if unable to find the cluster endpoint.

        """
        cluster_group = self._netbox.api.virtualization.cluster_groups.get(name=name)
        if cluster_group is None:
            raise GanetiError(f"Unable to find virtualization cluster group {name} on Netbox.")

        address_field = cluster_group.custom_fields.get("ip_address")
        if address_field is None:
            raise GanetiError(f"Virtualization cluster group {name} has no IP address.")

        routed = cluster_group.custom_fields.get("routed")
        if routed is None:
            raise GanetiError(f"Virtualization cluster group {name} doesn't have the 'routed' custom field set.")

        address = address_field.get("address")
        if not address:  # Covers also the case it's an empty string
            raise GanetiError(f"Virtualization cluster group {name} IP address has no address.")

        ip_address = self._netbox.api.ipam.ip_addresses.get(address=address)
        if ip_address is None:
            raise GanetiError(f"Unable to find the IP address for the virtualization cluster group {name}.")

        if not ip_address.dns_name:
            raise GanetiError(f"Virtualization cluster group {name}'s IP address {address} has no DNS name.")

        return GanetiCluster(
            name=name, fqdn=ip_address.dns_name, rapi=RAPI_URL_FORMAT.format(cluster=ip_address.dns_name), routed=routed
        )

    def get_group(self, name: str, *, cluster: str) -> GanetiGroup:
        """Get a GanetiGroup instance for the given group name.

        Arguments:
            name: the name of the Ganeti group, equivalent to the cluster in Netbox.
            cluster: the name of the Ganeti cluster where to look for the group, equivalent to the cluster group in
                Netbox.

        Raises:
            spicerack.ganeti.GanetiError: if unable to find the group.

        """
        cluster_obj = self.get_cluster(cluster)
        group = self._netbox.api.virtualization.clusters.get(name=name, group=cluster)
        if group is None:
            raise GanetiError(f"Unable to find virtualization cluster {name} in cluster group {cluster} on Netbox.")

        return GanetiGroup(name=name, site=group.site.slug, cluster=cluster_obj)

    def rapi(self, cluster: str) -> GanetiRAPI:
        """Return a RAPI object for a particular cluster.

        Arguments:
            cluster: the name of the cluster group in Netbox for this Ganeti cluster.

        Raises:
            spicerack.ganeti.GanetiError: if unable to find the cluster endpoint.

        """
        return GanetiRAPI(
            self.get_cluster(cluster).rapi, self._username, self._password, self._timeout, WMF_CA_BUNDLE_PATH
        )

    def instance(self, instance: str, *, cluster: str = "") -> GntInstance:
        """Return an instance of GntInstance to perform RW operation on the given Ganeti VM instance.

        Arguments:
            instance: the FQDN of the Ganeti VM instance to act upon.
            cluster: the name of the Ganeti cluster to which the instance belongs, or will belong in case of a new
                instance to be created. If not provided it will be auto-detected for existing instances.

        """
        if not cluster:
            vm = self._netbox.api.virtualization.virtual_machines.get(name=instance.split(".")[0])
            if not vm:
                raise GanetiError(
                    f"Ganeti Virtual Machine {instance} does not exist on Netbox and no manual cluster was provided"
                )

            cluster = vm.cluster.group.name

        master = self.rapi(cluster).master
        if master is None:
            raise GanetiError(f"Master for cluster {cluster} is None")

        return GntInstance(self._remote.query(master), cluster, instance)
