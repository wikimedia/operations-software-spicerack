"""Service module."""

import logging
from collections import abc
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import timedelta
from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import Optional, Union

from spicerack.administrative import Reason
from spicerack.alertmanager import Alertmanager, AlertmanagerHosts, MatchersType
from spicerack.confctl import ConftoolEntity
from spicerack.decorators import retry, set_tries
from spicerack.dnsdisc import Discovery, DiscoveryError
from spicerack.exceptions import SpicerackError

logger = logging.getLogger(__name__)


class ServiceError(SpicerackError):
    """Generic exception class for errors in the service module."""


class ServiceNotFoundError(ServiceError):
    """Exception class raised when a service is not found."""


class TooManyDiscoveryRecordsError(ServiceError):
    """Exception class raised when more than one DNS Discovery record is present but not name was specified."""


class DiscoveryRecordNotFoundError(ServiceError):
    """Exception class raised when a DNS Discovery record is not found by name or there is none."""


class DiscoveryStateError(ServiceError):
    """Exception class raised when a dns discovery record does not correspond to its conftool state."""


@dataclass(frozen=True)
class ServiceDiscoveryRecord:
    """Represents the DNS Discovery attributes of the service.

    See Also:
        Puppet's ``modules/wmflib/types/service/discovery.pp``.

    Arguments:
        active_active: :py:data:`True` if the service is active/active in DNS Discovery.
        dnsdisc: the name used in conftool for the discovery record.
        instance: the DNS Discovery intance to operate on the service.

    """

    active_active: bool
    dnsdisc: str
    instance: Discovery

    @property
    def state(self) -> set[str]:
        """The state of the dnsdisc object.

        Returns a set with the names of the datacenters where the record is pooled.
        """
        return set(self.instance.active_datacenters[self.dnsdisc])

    @property
    def fqdn(self) -> str:
        """The fqdn of the record."""
        return f"{self.dnsdisc}.discovery.wmnet"

    def is_pooled_in(self, datacenter: str) -> bool:
        """True if the dnsdisc object is pooled in the datacenter."""
        return datacenter in self.state

    def check_service_ips(
        self, service_ips: "ServiceIPs", ip_per_dc_map: dict[str, Union[IPv4Address, IPv6Address]]
    ) -> None:
        """Check the DNS records.

        For every datacenter the service is present in, we check that:
        * If the datacenter is pooled, resolving the name from a client in that datacenter
        returns the local IP of the service
        * If it's depooled, resolving the name from a client in that datacenter returns a
        non-local ip for the service.

        The most important function of this check is to ensure the etcd change has been
        propagated before we cleare the dns recursor caches.

        Arguments:
            service_ips: An instance of service IPs related to this record.
            ip_per_dc_map: map of client IPs from the different datacenters.

        Raises:
            spicerack.serviceDiscoveryStateError: on failure.

        """
        for datacenter in service_ips.sites:
            is_pooled = self.is_pooled_in(datacenter)
            local_ip = service_ips.get(datacenter)
            try:
                ip_by_ns = self.instance.resolve_with_client_ip(self.dnsdisc, ip_per_dc_map[datacenter])
            except DiscoveryError as exc:
                raise DiscoveryStateError(str(exc)) from exc

            for nameserver, actual_ip in ip_by_ns.items():
                resolves_locally = ip_address(actual_ip) == local_ip
                if is_pooled and not resolves_locally:
                    raise DiscoveryStateError(
                        f"Error checking auth dns for {self.fqdn} from {datacenter}: "
                        f"nameserver {nameserver} resolved to {actual_ip}, expected: {local_ip}"
                    )
                if not is_pooled and resolves_locally:
                    raise DiscoveryStateError(
                        f"Error checking auth dns for {self.fqdn} in {datacenter}: "
                        f"resolved to {local_ip}, a different IP was expected."
                    )


class ServiceDiscovery(abc.Iterable):
    """Represents the service Discovery records collection as list-like object with helper methods.

    The discovery behaves like an Iterator, so it can be iterated in list-comprehension and similar contructs.
    It supports also ``len()``, to quickly know how many records are configured for the service.

    """

    def __init__(self, records: Sequence[ServiceDiscoveryRecord]):
        """Initialize the instance with the records.

        Arguments:
            records: the DNS Discovery records.

        """
        self.records = records

    def __iter__(self) -> Iterator[ServiceDiscoveryRecord]:
        """Iterate over the DNS Discovery records in the instance.

        Yields:
            the records related to this discovery service.

        """
        return iter(self.records)

    def __len__(self) -> int:
        """Return the number of DNS Discovery records."""
        return len(self.records)

    def depool(self, site: str, *, name: str = "") -> None:
        """Depool the service from the given site in DNS Discovery.

        Args:
            site: the datacenter to depool the service from.
            name: the dnsdisc name of the DNS Discovery record to depool. If empty, and there is only one record, it
                will depool that one.

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
            site: the datacenter to pool the service to.
            name: the dnsdisc name of the DNS Discovery record to pool. If empty, and there is only one record, it
                will pool that one.

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
            site: the datacenter to depool the service from.
            name: the dnsdisc name of the DNS Discovery record to depool. If empty, and there is only one record, it
                will depool that one.
            repool_on_error: whether to repool the site on error or not.

        Yields:
            None: it just gives back control to the caller.

        Raises:
            spicerack.service.DiscoveryRecordNotFoundError: if there are no records at all or the record with the given
            name can't be found.
            spicerack.service.TooManyDiscoveryRecordsError: if the name is an empty string and there is more than one
            record.

        """
        self.depool(site, name=name)
        try:  # pylint: disable=no-else-raise
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
            name: the dnsdic name of the DNS Discovery record. If set to an empty string, and the service has only one
                service, it will return that one.

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
        data: a dictionary representing the service IPs data as defined in ``service::catalog``.

    """

    data: dict[str, dict[str, str]]

    @property
    def all(self) -> list[Union[IPv4Address, IPv6Address]]:
        """Return all the service IPs."""
        return [ip_address(j) for i in self.data.values() for j in i.values()]

    @property
    def sites(self) -> list[str]:
        """Returns all the datacenters where there is at least one IP for the service."""
        return list(self.data.keys())

    def get(self, site: str, label: str = "default") -> Union[IPv4Address, IPv6Address, None]:
        """Get the IP for a given datacenter and optional label.

        Arguments:
            site: the datacenter to filter for.
            label: the label of the IP.

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
        cluster: name of the cluster tag in conftool.
        service: name of the service tag in conftool.

    """

    cluster: str
    service: str


@dataclass(frozen=True)
class ServiceLVS:
    """Represent the load balancer configuration for the service.

    See Also:
        Puppet's ``modules/wmflib/types/service/lvs.pp``.

    Arguments:
        conftool: the conftool configuration for the service.
        depool_threshold: the percentage of the cluster that Pybal will keep pooled anyway on failure.
        enabled: whether the service is enabled on the load balancers.
        lvs_class: the traffic class of the service (e.g. ``low-traffic``).
        monitors: a dictionary of Pybal monitors configured for the service.
        bgp: whether Pybal advertise the service via BGP or not.
        protocol: the Internet protocol of the service.
        scheduler: the IPVS scheduler used for the service.
        scheduler_flag: the IPVS scheduler flag used for the service.
        ipip_encapsulation: Whether the realservers receive traffic from the load balancers using IPIP encapsulation

    """

    conftool: ServiceLVSConftool
    depool_threshold: float
    enabled: bool
    lvs_class: str
    monitors: Optional[dict[str, dict]] = None  # Optional field in puppet
    bgp: bool = True  # Default value in Puppet.
    protocol: str = "tcp"  # Default value in Puppet.
    scheduler: str = "wrr"  # Default value in Puppet.
    scheduler_flag: Optional[str] = None  # Default value in Puppet.
    ipip_encapsulation: bool = False  # Default value in Puppet.


@dataclass(frozen=True)
class ServiceMonitoringHostnames:
    """Represent the Icinga hostnames or FQDNs used to monitor the service in each datacenter.

    See Also:
        Puppet's ``modules/wmflib/types/service/monitoring.pp``.

    Arguments:
        data: the service monitoring dictionary.

    """

    data: dict[str, dict[str, str]]

    @property
    def all(self) -> list[str]:
        """Return all service monitoring Icinga hostnames/FQDNs."""
        return [j for i in self.data.values() for j in i.values()]

    @property
    def sites(self) -> list[str]:
        """Return all the datacenters in which the monitoring is configured for."""
        return list(self.data.keys())

    def get(self, site: str) -> str:
        """Get the monitoring hostname/FQDN for the service in the given datacenter, empty string if not configured."""
        return self.data.get(site, {}).get("hostname", "")


@dataclass(frozen=True)
class ServiceMonitoring:
    """Represent the monitoring configuration for the service.

    See Also:
        Puppet's ``modules/wmflib/types/service/monitoring.pp``.

    Arguments:
        check_command: the Icinga check command used to monitor the service.
        sites: the FQDNs used to monitor the service in each datacenter.
        contact_group: the name of the Icinga contact group used for the service.
        notes_url: the Icinga notes URL pointing to the service runbook.

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
        name: the service name.
        description: the service description.
        encryption: whether TLS encryption is enabled or not on the service.
        ip: the instance that represents all the service IPs.
        port: the port the service listen on.
        sites: the list of datacenters where the service is configured.
        state: the production state of the service (e.g. ``lvs_setup``).
        _alertmanager: the AlertmanagerHosts instance to perform downtime.
        aliases: a list of aliases names for the service.
        discovery: the collection of :py:class:`spicerack.service.ServiceDiscoveryRecord` instances reprensenting the
            DNS Discovery capabilities of the service.
        lvs: the load balancer configuration.
        monitoring: the service monitoring configuration.
        page: whether the monitoring for this service does page or not.
        probes: a list of probe dictionaries with all the parameters necessary to define the probes for this service.
        public_aliases: the list of public aliases set for this service.
        public_endpoint: the name of the public endpoint if present, empty string otherwise.
        role: the service role name in Puppet if present, empty string otherwise.

    """

    name: str
    description: str
    encryption: bool
    ip: ServiceIPs  # pylint: disable=invalid-name
    port: int
    sites: list[str]
    state: str
    _dry_run: bool
    _alertmanager: AlertmanagerHosts
    aliases: list[str] = field(default_factory=list)
    discovery: Optional[ServiceDiscovery] = None
    httpbb_dir: str = ""
    lvs: Optional[ServiceLVS] = None
    monitoring: Optional[ServiceMonitoring] = None
    page: bool = True  # Default value in Puppet.
    probes: list[dict] = field(default_factory=list)
    public_aliases: list[str] = field(default_factory=list)
    public_endpoint: str = ""
    role: str = ""

    def downtime(self, site: str, reason: Reason, *, duration: timedelta = timedelta(hours=4)) -> str:
        """Downtime the service on the given site in Alertmanager and return its ID.

        Args:
            site: the datacenter where to silence the service.
            reason: the silence reason.
            duration: how long to silence for.

        Raises:
            spicerack.service.ServiceError: if the service is not present in the given datacenter.

        """
        return self._alertmanager.downtime(reason, matchers=self._get_downtime_matchers(site), duration=duration)

    @contextmanager
    def downtimed(
        self, site: str, reason: Reason, *, duration: timedelta = timedelta(hours=4), remove_on_error: bool = False
    ) -> Iterator[None]:
        """Context manager to perform actions while the service is downtimed in the given site in Alertmanager.

        Args:
            site: the datacenter where to silence the service.
            reason: the silence reason.
            duration: how long to silence for.
            remove_on_error: should the downtime be removed even if an exception was raised.

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
            site: the datacenter where to silence the service.

        """
        if site not in self.sites:
            raise ServiceError(f"Service {self.name} is not present in site {site}. Available sites are {self.sites}")

        return [
            {"name": "site", "value": site, "isRegex": False},
            {"name": "job", "value": r"^probes/.*", "isRegex": True},
        ]

    @retry(backoff_mode="constant", exceptions=(DiscoveryStateError,), dynamic_params_callbacks=(set_tries,))
    def check_dns_state(
        self, ip_per_dc_map: dict[str, Union[IPv4Address, IPv6Address]], record_name: str = "", tries: int = 15
    ) -> None:
        """Checks the state of dns discovery is consistent.

        Checks that a discovery record state on the dns servers corresponds to the state in the conftool discovery
        backend.

        Arguments:
            ip_per_dc_map: mapping of datacenter -> client IP to use.
            record_name: the discovery record name to inspect. If left empty, it will pick up the only discovery
                record.
            tries: the number of retries to attempt before failing.

        Raises:
            ValueError: on invalid tries value.
            spicerack.service.DiscoveryStateError: if the two states don't correspond.
            spicerack.service.DiscoveryRecordNotFoundError: if there are no records at all or the record with the given
            name can't be found.
            spicerack.service.TooManyDiscoveryRecordsError: if the name is an empty string and there is more than one
            record.

        """
        if tries <= 0:
            raise ValueError("The tries argument must be a positive integer.")
        # No discovery records, nothing to check.
        if self.discovery is None:
            return
        self.discovery.get(record_name).check_service_ips(self.ip, ip_per_dc_map)


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

    def __init__(
        self,
        catalog: dict,
        *,
        alertmanager: Alertmanager,
        confctl: ConftoolEntity,
        authdns_servers: dict[str, str],
        dry_run: bool = True,
    ):
        """Initialize the instance.

        Args:
            catalog: the content of Puppet's ``hieradata/common/service.yaml``.
            alertmanager: the alertmanager instance to interact with.
            confctl: the instance to interact with confctl.
            authdns_servers: a dictionary where keys are the hostnames and values are the IPs of the authoritative
                nameservers to be used.
            dry_run: whether this is a DRY-RUN.

        """
        self._catalog = catalog
        self._alertmanager = alertmanager
        self._confctl = confctl
        self._authdns_servers = authdns_servers
        self._dry_run = dry_run

    def __iter__(self) -> Iterator[Service]:
        """Iterate over the catalog services.

        Yields:
            the service instances.

        """
        return (self.get(name) for name in self._catalog)

    def __len__(self) -> int:
        """Return the number of services in the catalog."""
        return len(self._catalog)

    @property
    def service_names(self) -> list[str]:
        """Get all defined service names."""
        return list(self._catalog.keys())

    def get(self, name: str) -> Service:
        """Get a single service by name.

        Examples:
            Get a specific service::

                >>> service = catalog.get("service_name")

        Arguments:
            name: the service name.

        Raises:
            spicerack.service.ServiceNotFoundError: if the service is not found.

        """
        if name not in self._catalog:
            raise ServiceNotFoundError(f"Service {name} was not found in service::catalog")

        params = deepcopy(self._catalog[name])
        params["name"] = name
        params["ip"] = ServiceIPs(data=params["ip"])
        params["_alertmanager"] = self._alertmanager.hosts([f"{name}:{params['port']}"], verbatim_hosts=True)
        params["_dry_run"] = self._dry_run
        if "discovery" in params:
            discovery = []
            for disc in params["discovery"]:
                instance = Discovery(
                    conftool=self._confctl,
                    authdns_servers=self._authdns_servers,
                    records=[disc["dnsdisc"]],
                    dry_run=self._dry_run,
                )
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
