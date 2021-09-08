"""DNS Discovery module."""
import logging
from collections import defaultdict
from typing import Dict, Iterator, List, Optional

from dns import resolver
from dns.exception import DNSException

from spicerack.confctl import ConftoolEntity
from spicerack.decorators import retry
from spicerack.exceptions import SpicerackCheckError, SpicerackError
from spicerack.remote import Remote

logger = logging.getLogger(__name__)


class DiscoveryError(SpicerackError):
    """Custom exception class for errors of the Discovery class."""


class DiscoveryCheckError(SpicerackCheckError):
    """Custom exception class for errors while performing checks."""


class Discovery:
    """Class to manage Confctl discovery objects."""

    def __init__(
        self,
        conftool: ConftoolEntity,
        remote: Remote,
        records: List[str],
        dry_run: bool = True,
    ) -> None:
        """Initialize the instance.

        Arguments:
            conftool (spicerack.confctl.ConftoolEntity): the conftool instance for the discovery type objects.
            remote (spicerack.remote.Remote): the Remote instance.
            records (list): list of strings, each one must be a Discovery DNS record name.
            dry_run (bool, optional): whether this is a DRY-RUN.

        Raises:
            spicerack.dnsdisc.DiscoveryError: if unable to initialize the resolvers.

        """
        self._conftool = conftool
        self._remote = remote
        self._records = records
        self._dry_run = dry_run

        self._resolvers: Dict[str, resolver.Resolver] = {}
        for nameserver in self._remote.query("A:dns-auth").hosts:
            self._resolvers[nameserver] = resolver.Resolver(configure=False)
            self._resolvers[nameserver].port = 5353
            try:
                self._resolvers[nameserver].nameservers = [rdata.address for rdata in resolver.query(nameserver)]
            except DNSException as e:
                raise DiscoveryError(f"Unable to resolve {nameserver}") from e

    @property
    def _conftool_selector(self) -> str:
        """Generate the Conftool selector for the records.

        Returns:
            str: the Conftool selector.

        """
        regexp = "|".join(self._records)
        return f"({regexp})"

    @property
    def active_datacenters(self) -> defaultdict:
        """Information about pooled state of services.

        Returns:
            dict: a map of services, with values given by a list of datacenters where the service is pooled, i.e.::

                {
                    'svc_foo': ['dc1', 'dc2'],
                    'svc_bar': ['dc1'],
                }

        """
        services = defaultdict(list)
        for obj in self._conftool.get(dnsdisc=self._conftool_selector):
            if obj.pooled:
                service = obj.tags["dnsdisc"]
                services[service].append(obj.name)

        return services

    def resolve_address(self, name: str) -> str:
        """Resolve the IP of a given record.

        Todo:
            move a more generalized version of this into a DNS resolver module.

        Arguments:
            name (str): the DNS record to resolve.

        Returns:
            str: the resolved IP address.

        Raises:
            spicerack.discovery.DiscoveryError: if unable to resolve the address.

        """
        try:  # Querying the first resolver
            return next(iter(self._resolvers.values())).query(name)[0].address
        except DNSException as e:
            raise DiscoveryError(f"Unable to resolve {name}") from e

    def update_ttl(self, ttl: int) -> None:
        """Update the TTL for all registered records.

        Arguments:
            ttl (int): the new TTL value to set.

        Raises:
            spicerack.discovery.DiscoveryError: if the check of the modified TTL fail and not in DRY-RUN mode.

        """
        # DRY-RUN handled by confctl
        logger.debug("Updating the TTL of %s to %d seconds", self._conftool_selector, ttl)
        self._conftool.set_and_verify("ttl", ttl, dnsdisc=self._conftool_selector)
        try:
            self.check_ttl(ttl)
        except DiscoveryCheckError:
            if not self._dry_run:
                raise

    @retry(
        tries=10,
        backoff_mode="constant",
        exceptions=(DiscoveryCheckError,),
        failure_message="Waiting for DNS TTL update...",
    )
    def check_ttl(self, ttl: int) -> None:
        """Check the TTL for all records.

        Arguments:
            ttl (int): the expected TTL value.

        Raises:
            DiscoveryError: if the expected TTL is not found.

        """
        logger.debug("Checking that TTL=%d for %s discovery.wmnet records", ttl, self._records)

        for record in self.resolve():
            if record.ttl != ttl:
                raise DiscoveryCheckError(f"Expected TTL '{ttl}', got '{record.ttl}' for record {record[0].address}")
        if len(self._records) == 1:
            logger.info("%s.discovery.wmnet TTL is correct.", self._records[0])
        else:
            logger.info("%s discovery.wmnet TTLs are correct.", self._records)

    @retry(
        tries=10,
        backoff_mode="constant",
        exceptions=(DiscoveryError,),
        failure_message="Waiting for DNS record update...",
    )
    def check_record(self, name: str, expected_name: str) -> None:
        """Check that a Discovery record resolves on all authoritative resolvers to the correct IP.

        The IP to use for the comparison is obtained resolving the expected_name record.
        For example with name='servicename-rw.discovery.wmnet' and expected_name='servicename.svc.eqiad.wmnet', this
        method will resolve the 'expected_name' to get its IP address and then verify that on all authoritative
        resolvers the record for 'name' resolves to the same IP.
        It is retried to allow the change to be propagated through all authoritative resolvers.

        See Also:
            https://wikitech.wikimedia.org/wiki/DNS/Discovery

        Arguments:
            name (str): the record to check the resolution for.
            expected_name (str): the name of a record to be resolved and used as the expected address.

        Raises:
            DiscoveryError: if the record doesn't match the IP of the expected_name.

        """
        expected_address = self.resolve_address(expected_name)
        logger.info(
            "Checking that %s.discovery.wmnet records matches %s (%s)",
            name,
            expected_name,
            expected_address,
        )

        failed = False
        for record in self.resolve(name=name):
            if not self._dry_run and record[0].address != expected_address:
                failed = True
                logger.error(
                    "Expected IP '%s', got '%s' for record %s",
                    expected_address,
                    record[0].address,
                    name,
                )

        if failed:
            raise DiscoveryError(f"Resolved record {name} with the wrong IP")

        logger.info("%s.discovery.wmnet record is correct.", name)

    def resolve(self, name: Optional[str] = None) -> Iterator[resolver.Answer]:
        """Generator that yields the resolved records.

        Todo:
            move a more generalized version of this into a DNS resolver module.

        Arguments:
            name (str, optional): record name to use for the resolution instead of self.records.

        Yields:
            dns.resolver.Answer: the DNS response.

        Raises:
            spicerack.discovery.DiscoveryError: if unable to resolve the address.

        """
        if name is not None:
            records = [name]
        else:
            records = self._records

        for nameserver, dns_resolver in self._resolvers.items():
            for record in records:
                try:
                    record_name = f"{record}.discovery.wmnet"
                    answer = dns_resolver.query(record_name)
                except DNSException as e:
                    raise DiscoveryError(f"Unable to resolve {record_name} from {nameserver}") from e

                logger.debug(
                    "[%s] %s -> %s TTL %d",
                    nameserver,
                    record,
                    answer[0].address,
                    answer.ttl,
                )
                yield answer

    def pool(self, datacenter: str) -> None:
        """Set the records as pooled in the given datacenter.

        Arguments:
            datacenter (str): the DC in which to pool the discovery records.

        """
        # DRY-RUN handled by confctl
        self._conftool.set_and_verify("pooled", True, dnsdisc=self._conftool_selector, name=datacenter)

    def depool(self, datacenter: str) -> None:
        """Set the records as depooled in the given datacenter.

        Arguments:
            datacenter (str): the DC from which to depool the discovery records.

        """
        self.check_if_depoolable(datacenter)
        # DRY-RUN handled by confctl
        self._conftool.set_and_verify("pooled", False, dnsdisc=self._conftool_selector, name=datacenter)

    def check_if_depoolable(self, datacenter: str) -> None:
        """Determine if a datacenter can be depooled for all records.

        Arguments:
            datacenter (str): the datacenter to depool

        Raises:
            spicerack.discovery.DiscoveryError: if any service cannot be depooled.

        """
        # NB: we only discard services that would become inactive removing the current DC
        # we don't care about services that are completely down.
        non_depoolable = [svc for svc, dcs in self.active_datacenters.items() if dcs == [datacenter]]
        if non_depoolable:
            services = ", ".join(sorted(non_depoolable))
            message = f"Services {services} cannot be depooled as they are only active in {datacenter}"
            if self._dry_run:
                logger.debug(message)
            else:
                raise DiscoveryError(message)
