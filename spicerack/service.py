"""Service module."""
import logging
from collections import abc
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import timedelta
from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import Dict, Iterator, List, Optional, Sequence, Union

from spicerack.administrative import Reason
from spicerack.alertmanager import AlertmanagerHosts, MatchersType
from spicerack.confctl import ConftoolEntity
from spicerack.dnsdisc import Discovery
from spicerack.exceptions import SpicerackError
from spicerack.remote import Remote

logger = logging.getLogger(__name__)


class ServiceError(SpicerackError):
    """Generic exception class for errors in the service module."""


class ServiceNotFoundError(ServiceError):
    """Exception class raised when a service is not found."""


class TooManyDiscoveryRecordsError(ServiceError):
    """Exception class raised when more than one DNS Discovery record is present but not name was specified."""


class DiscoveryRecordNotFoundError(ServiceError):
    """Exception class raised when a DNS Discovery record is not found by name or there is none."""


@dataclass(frozen=True)
class ServiceDiscoveryRecord:
    """Represents the DNS Discovery attributes of the service.

    See Also:
        Puppet's ``modules/wmflib/types/service/discovery.pp``.

    Arguments:
        active_active (bool): :py:data:`True` if the service is active/active in DNS Discovery.
        dnsdisc (str): the name used in conftool for the discovery record.
        instance (spicerack.dnsdisc.Discovery): the DNS Discovery intance to operate on the service.

    """

    active_active: bool
    dnsdisc: str
    instance: Discovery


class ServiceDiscovery(abc.Iterable):
    """Represents the service Discovery records collection as list-like object with helper methods.

    The discovery behaves like an Iterator, so it can be iterated in list-comprehension and similar contructs.
    It supports also ``len()``, to quickly know how many records are configured for the service.

    """

    def __init__(self, records: Sequence[ServiceDiscoveryRecord]):
        """Initialize the instance with the records.

        Arguments:
            records (iterable, optional): the DNS Discovery records.

        """
        self.records = records

    def __iter__(self) -> Iterator[ServiceDiscoveryRecord]:
        """Iterate over the DNS Discovery records in the instance.

        Returns:
            iterator: iterator over the records.

        """
        return iter(self.records)

    def __len__(self) -> int:
        """Return the length of the instance.

        Returns:
            int: the number of DNS Discovery records.

        """
        return len(self.records)

    def depool(self, site: str, *, name: str = "") -> None:
        """Depool the service from the given site in DNS Discovery.

        Args:
            site (str): the datacenter to depool the service from.
            name (str, optional): the dnsdisc name of the DNS Discovery record to depool. If empty, and there is only
                one record, it will depool that one.

        Raises:
            spicerack.service.DiscoveryRecordNotFoundError: if there are no records at all or the record with the given
            name can't be found.
            spicerack.service.TooManyDiscoveryRecordsError: if the name is an empty string and there is more than one
            record.

        """
        self.get(name).instance.depool(site)

    def pool(self, site: str, *, name: str = "") -> None:
        """Pool the service to the given site in DNS Discovery.

        Args:
            site (str): the datacenter to pool the service to.
            name (str, optional): the dnsdisc name of the DNS Discovery record to pool. If empty, and there is only
                one record, it will pool that one.

        Raises:
            spicerack.service.DiscoveryRecordNotFoundError: if there are no records at all or the record with the given
            name can't be found.
            spicerack.service.TooManyDiscoveryRecordsError: if the name is an empty string and there is more than one
            record.

        """
        self.get(name).instance.pool(site)

    @contextmanager
    def depooled(self, site: str, *, name: str = "", repool_on_error: bool = False) -> Iterator[None]:
        """Context manager to act while the service is depooled from the given site in DNS Discovery.

        It will not repool the service on the given site if any exception is raised within the context manager context,
        unless ``repool_on_error`` is set to :py:data:`True`.

        Args:
            site (str): the datacenter to depool the service from.
            name (str, optional): the dnsdisc name of the DNS Discovery record to depool. If empty, and there is only
                one record, it will depool that one.
            repool_on_error (bool, optional): whether to repool the site on error or not.

        Yields:
            None

        Raises:
            spicerack.service.DiscoveryRecordNotFoundError: if there are no records at all or the record with the given
            name can't be found.
            spicerack.service.TooManyDiscoveryRecordsError: if the name is an empty string and there is more than one
            record.

        """
        self.depool(site, name=name)
        try:
            yield
        except Exception:
            if repool_on_error:
                self.pool(site, name=name)
            raise
        else:
            self.pool(site, name=name)

    def get(self, name: str = "") -> ServiceDiscoveryRecord:
        """Return the DNS Discovery record for the given name, raise an exception if not found.

        Arguments:
            name (str, optional): the dnsdic name of the DNS Discovery record. If set to an empty string, and the
                service has only one service, it will return that one.

        Raises:
            spicerack.service.DiscoveryRecordNotFoundError: if there are no records at all or the record with the given
            name can't be found.
            spicerack.service.TooManyDiscoveryRecordsError: if the name is an empty string and there is more than one
            record.

        """
        if not self.records:
            raise DiscoveryRecordNotFoundError("No DNS Discovery record present.")

        if name:
            matching = [record for record in self.records if record.dnsdisc == name]
            if not matching:
                raise DiscoveryRecordNotFoundError(f"Unable to find DNS Discovery record {name}.")
            if len(matching) > 1:
                raise TooManyDiscoveryRecordsError(
                    f"There are {len(matching)} DNS Discovery records matching name {name}."
                )
            return matching[0]

        if len(self.records) > 1:
            raise TooManyDiscoveryRecordsError(
                f"There are {len(self.records)} DNS Discovery records but dnsdisc was not set."
            )
        return self.records[0]


@dataclass(frozen=True)
class ServiceIPs:
    """Represent the service IPs.

    See Also:
        Puppet's ``modules/wmflib/types/service/ipblock.pp``.

    Arguments:
        data (dict): a dictionary representing the service IPs data as defined in ``service::catalog``.

    """

    data: Dict[str, Dict[str, str]]

    @property
    def all(self) -> List[Union[IPv4Address, IPv6Address]]:
        """Return all service IPs.

        Returns:
            list: a list of IP addresses.

        """
        return [ip_address(j) for i in self.data.values() for j in i.values()]

    @property
    def sites(self) -> List[str]:
        """Returns all the datacenters where there is at least one IP for the service.

        Returns:
            list: a list of strings.

        """
        return list(self.data.keys())

    def get(self, site: str, label: str = "default") -> Union[IPv4Address, IPv6Address, None]:
        """Get the IP for a given datacenter and optional label.

        Arguments:
            site (str): the datacenter to filter for.
            label (str, optional): the label of the IP.

        Returns:
            ipaddress.IPv4Address: if the matched IP is an IPv4.
            ipaddress.IPv6Address: if the matched IP is an IPv6.
            None: if there is no IP matching the criteria.

        """
        ip_str = self.data.get(site, {}).get(label, "")
        if ip_str:
            return ip_address(ip_str)

        return None


@dataclass(frozen=True)
class ServiceLVSConftool:
    """Represent the conftool configuration for the service for the load balancers.

    Arguments:
        cluster (str): name of the cluster tag in conftool.
        service (str): name of the service tag in conftool.

    """

    cluster: str
    service: str


@dataclass(frozen=True)
class ServiceLVS:
    """Represent the load balancer configuration for the service.

    See Also:
        Puppet's ``modules/wmflib/types/service/lvs.pp``.

    Arguments:
        conftool (spicerack.service.ServiceLVSConftool): the conftool configuration for the service.
        depool_threshold (str): the percentage of the cluster that Pybal will keep pooled anyway on failure.
        enabled (bool): whether the service is enabled on the load balancers.
        lvs_class (str): the traffic class of the service (e.g. ``low-traffic``).
        monitors (dict): a dictionary of Pybal monitors configured for the service.
        bgp (bool, optional): whether Pybal advertise the service via BGP or not.
        protocol (str, optional): the Internet protocol of the service.
        scheduler (str, optional): the IPVS scheduler used for the service.

    """

    conftool: ServiceLVSConftool
    depool_threshold: str
    enabled: bool
    lvs_class: str
    monitors: Dict[str, Dict]
    bgp: bool = True  # Default value in Puppet.
    protocol: str = "tcp"  # Default value in Puppet.
    scheduler: str = "wrr"  # Default value in Puppet.


@dataclass(frozen=True)
class ServiceMonitoringHostnames:
    """Represent the Icinga hostnames or FQDNs used to monitor the service in each datacenter.

    See Also:
        Puppet's ``modules/wmflib/types/service/monitoring.pp``.

    Arguments:
        data (dict): the service monitoring dictionary.

    """

    data: Dict[str, Dict[str, str]]

    @property
    def all(self) -> List[str]:
        """Return all service monitoring Icinga hostnames/FQDNs.

        Returns:
            list: the list of Icinga hostnames/FQDNs.

        """
        return [j for i in self.data.values() for j in i.values()]

    @property
    def sites(self) -> List[str]:
        """Return all the datacenters in which the monitoring is configured for.

        Returns:
            list: the list of datacenters.

        """
        return list(self.data.keys())

    def get(self, site: str) -> str:
        """Get the monitoring hostname/FQDN for the service in the given datacenter.

        Returns:
            str: the hostname/FQDN for the given datacenter if configured, empty string otherwise.

        """
        return self.data.get(site, {}).get("hostname", "")


@dataclass(frozen=True)
class ServiceMonitoring:
    """Represent the monitoring configuration for the service.

    See Also:
        Puppet's ``modules/wmflib/types/service/monitoring.pp``.

    Arguments:
        check_command (str): the Icinga check command used to monitor the service.
        sites (spicerack.service.ServiceMonitoringHostnames): the FQDNs used to monitor the service in each datacenter.
        contact_group (str, optional): the name of the Icinga contact group used for the service.
        notes_url (str, optional): the Icinga notes URL pointing to the service runbook.

    """

    check_command: str
    sites: ServiceMonitoringHostnames
    contact_group: str = ""
    notes_url: str = ""


@dataclass(frozen=True)
class Service:  # pylint: disable=too-many-instance-attributes
    """Class to represent a service as defined in Puppet's ``service::catalog`` hieradata.

    See Also:
        Puppet's ``modules/wmflib/types/service.pp``.

    Arguments:
        name (str): the service name.
        description (str): the service description.
        encryption (bool): whether TLS encryption is enabled or not on the service.
        ip (spicerack.service.ServiceIPs): the instance that represents all the service IPs.
        port (int): the port the service listen on.
        sites (list): the list of datacenters where the service is configured.
        state (str): the production state of the service (e.g. ``lvs_setup``).
        _alertmanager (spicerack.alertmanager:AlertmanagerHosts): the AlertmanagerHosts instance to perform downtime.
        aliases (list, optional): a list of aliases names for the service.
        discovery (spicerack.service.ServiceDiscovery, optional): the collection of
            :py:class:`spicerack.service.ServiceDiscoveryRecord` instances reprensenting the DNS Discovery capabilities
            of the service.
        lvs (spicerack.service.ServiceLVS, optional): the load balancer configuration.
        monitoring (spicerack.service.ServiceMonitoring, optional): the service monitoring configuration.
        page (bool, optional): whether the monitoring for this service does page or not.
        probes (list, optional): a list of probe dictionaries with all the parameters necessary to define the probes
            for this service.
        public_aliases (list, optional): the list of public aliases set for this service.
        public_endpoint (str, optional): the name of the public endpoint if present, empty string otherwise.
        role (str, optional): the service role name in Puppet if present, empty string otherwise.

    """

    name: str
    description: str
    encryption: bool
    ip: ServiceIPs  # pylint: disable=invalid-name
    port: int
    sites: List[str]
    state: str
    _alertmanager: AlertmanagerHosts
    aliases: List[str] = field(default_factory=list)
    discovery: Optional[ServiceDiscovery] = None
    lvs: Optional[ServiceLVS] = None
    monitoring: Optional[ServiceMonitoring] = None
    page: bool = True  # Default value in Puppet.
    probes: List[Dict] = field(default_factory=list)
    public_aliases: List[str] = field(default_factory=list)
    public_endpoint: str = ""
    role: str = ""

    def downtime(self, site: str, reason: Reason, *, duration: timedelta = timedelta(hours=4)) -> str:
        """Downtime the service on the given site in Alertmanager.

        Args:
            site (str): the datacenter where to silence the service.
            reason (spicerack.administrative.Reason): the silence reason.
            duration (datetime.timedelta, optional): how long to silence for.

        Raises:
            spicerack.service.ServiceError: if the service is not present in the given datacenter.

        Returns:
            str: the downtime ID.

        """
        return self._alertmanager.downtime(reason, matchers=self._get_downtime_matchers(site), duration=duration)

    @contextmanager
    def downtimed(
        self, site: str, reason: Reason, *, duration: timedelta = timedelta(hours=4), remove_on_error: bool = False
    ) -> Iterator[None]:
        """Context manager to perform actions while the service is downtimed in the given site in Alertmanager.

        Args:
            site (str): the datacenter where to silence the service.
            reason (spicerack.administrative.Reason): the silence reason.
            duration (datetime.timedelta, optional): how long to silence for.
            remove_on_error (bool, optional): should the downtime be removed even if an exception was raised.

        Raises:
            spicerack.service.ServiceError: if the service is not present in the given datacenter.

        """
        with self._alertmanager.downtimed(
            reason, matchers=self._get_downtime_matchers(site), duration=duration, remove_on_error=remove_on_error
        ):
            yield

    def _get_downtime_matchers(self, site: str) -> MatchersType:
        """Get the downtime matchers to use to downtime the service in Alertmanager.

        Args:
            site (str): the datacenter where to silence the service.

        """
        if site not in self.sites:
            raise ServiceError(f"Service {self.name} is not present in site {site}. Available sites are {self.sites}")

        return [
            {"name": "site", "value": site, "isRegex": False},
            {"name": "job", "value": r"^probes/.*", "isRegex": True},
        ]


class Catalog:
    """Class to represent the service catalog of Puppet's hierdata ``service::catalog``.

    The catalog behaves like an Iterator, so it can be iterated in list-comprehension and similar contructs.
    It supports also ``len()``, to quickly know how many services are loaded in the catalog.

    Examples:
        Get all service that are present in a given datacenter::

            >>> esams = [service for service in catalog if "esams" in service.sites]

        See how many services are configured::

            >>> num_services = len(catalog)

    """

    def __init__(self, catalog: Dict, confctl: ConftoolEntity, remote: Remote, dry_run: bool = True):
        """Initialize the instance.

        Args:
            catalog (dict): the content of Puppet's ``hieradata/common/service.yaml``.
            confctl (spicerack.confctl.ConftoolEntity): the instance to interact with confctl.
            remote (spicerack.remote.Remote): the instance to execute remote commands.
            dry_run (bool, optional): whether this is a DRY-RUN.

        """
        self._catalog = catalog
        self._confctl = confctl
        self._remote = remote
        self._dry_run = dry_run

    def __iter__(self) -> Iterator[Service]:
        """Iterate over the catalog services.

        Returns:
            iterator: iterator over the services.

        """
        return (self.get(name) for name in self._catalog)

    def __len__(self) -> int:
        """Return the length of the instance.

        Returns:
            int: the number of services in the catalog.

        """
        return len(self._catalog)

    @property
    def service_names(self) -> List[str]:
        """All defined service names.

        Returns:
            list: the list of service names.

        """
        return list(self._catalog.keys())

    def get(self, name: str) -> Service:
        """Get a single service by name.

        Examples:
            Get a specific service::

                >>> service = catalog.get("service_name")

        Arguments:
            name (str): the service name.

        Raises:
            spicerack.service.ServiceNotFoundError: if the service is not found.

        Returns:
            spicerack.service.Service: the instance of the matched service.

        """
        if name not in self._catalog:
            raise ServiceNotFoundError(f"Service {name} was not found in service::catalog")

        params = deepcopy(self._catalog[name])
        params["name"] = name
        params["ip"] = ServiceIPs(data=params["ip"])
        params["_alertmanager"] = AlertmanagerHosts(
            [f"{name}:{params['port']}"], verbatim_hosts=True, dry_run=self._dry_run
        )
        if "discovery" in params:
            discovery = []
            for disc in params["discovery"]:
                instance = Discovery(self._confctl, self._remote, [disc["dnsdisc"]], dry_run=self._dry_run)
                discovery.append(ServiceDiscoveryRecord(instance=instance, **disc))
            params["discovery"] = ServiceDiscovery(discovery)

        if "monitoring" in params:
            params["monitoring"]["sites"] = ServiceMonitoringHostnames(data=params["monitoring"]["sites"])
            params["monitoring"] = ServiceMonitoring(**params["monitoring"])

        if "lvs" in params:
            params["lvs"]["lvs_class"] = params["lvs"].pop("class")  # Rename class, reserved word in Python.
            params["lvs"]["conftool"] = ServiceLVSConftool(**params["lvs"]["conftool"])
            params["lvs"] = ServiceLVS(**params["lvs"])

        return Service(**params)
