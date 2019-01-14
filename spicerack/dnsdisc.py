"""DNS Discovery module."""
import logging

from collections import defaultdict

from dns import resolver
from dns.exception import DNSException

from spicerack.decorators import retry
from spicerack.exceptions import SpicerackCheckError, SpicerackError


logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


class DiscoveryError(SpicerackError):
    """Custom exception class for errors of the Discovery class."""


class DiscoveryCheckError(SpicerackCheckError):
    """Custom exception class for errors while performing checks."""


class Discovery:
    """Class to manage Confctl discovery objects."""

    def __init__(self, conftool, remote, records, dry_run=True):
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

        self._resolvers = {}
        for nameserver in self._remote.query('A:dns-auth').hosts:
            self._resolvers[nameserver] = resolver.Resolver()
            try:
                self._resolvers[nameserver].nameservers = [rdata.address for rdata in resolver.query(nameserver)]
            except DNSException as e:
                raise DiscoveryError('Unable to resolve {name}'.format(name=nameserver)) from e

    @property
    def _conftool_selector(self):
        """Generate the Conftool selector for the records.

        Returns:
            str: the Conftool selector.

        """
        return '({regexp})'.format(regexp='|'.join(self._records))

    @property
    def active_datacenters(self):
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
                service = obj.tags['dnsdisc']
                services[service].append(obj.name)

        return services

    def resolve_address(self, name):
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
            raise DiscoveryError('Unable to resolve {name}'.format(name=name)) from e

    def update_ttl(self, ttl):
        """Update the TTL for all registered records.

        Arguments:
            ttl (int): the new TTL value to set.

        Raises:
            spicerack.discovery.DiscoveryError: if the check of the modified TTL fail and not in DRY-RUN mode.

        """
        # DRY-RUN handled by confctl
        logger.debug('Updating the TTL of %s to %d seconds', self._conftool_selector, ttl)
        self._conftool.set_and_verify('ttl', ttl, dnsdisc=self._conftool_selector)
        try:
            self.check_ttl(ttl)
        except DiscoveryCheckError:
            if not self._dry_run:
                raise

    @retry(backoff_mode='linear', exceptions=(DiscoveryCheckError,))
    def check_ttl(self, ttl):
        """Check the TTL for all records.

        Arguments:
            ttl (int): the expected TTL value.

        Raises:
            DiscoveryError: if the expected TTL is not found.

        """
        logger.debug('Checking that TTL=%d for %s discovery.wmnet records', ttl, self._records)

        for record in self.resolve():
            if record.ttl != ttl:
                raise DiscoveryCheckError("Expected TTL '{expected}', got '{ttl}' for record {record}".format(
                    expected=ttl, ttl=record.ttl, record=record[0].address))

    @retry(backoff_mode='linear', exceptions=(DiscoveryError,))
    def check_record(self, name, expected_name):
        """Check that a Discovery record resolves on all authoritative resolvers to the correct IP.

        The IP to use for the comparison it obtained resolving the expected_name record.
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
        logger.info('Checking that %s.discovery.wmnet records matches %s (%s)', name, expected_name, expected_address)

        failed = False
        for record in self.resolve(name=name):
            if not self._dry_run and record[0].address != expected_address:
                failed = True
                logger.error("Expected IP '%s', got '%s' for record %s", expected_address, record[0].address, name)

        if failed:
            raise DiscoveryError('Failed to check record {name}'.format(name=name))

    def resolve(self, name=None):
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
                    record_name = '{record}.discovery.wmnet'.format(record=record)
                    answer = dns_resolver.query(record_name)
                except DNSException as e:
                    raise DiscoveryError(
                        'Unable to resolve {name} from {ns}'.format(name=record_name, ns=nameserver)) from e

                logger.debug('[%s] %s -> %s TTL %d', nameserver, record, answer[0].address, answer.ttl)
                yield answer

    def pool(self, datacenter):
        """Set the records as pooled in the given datacenter.

        Arguments:
            datacenter (str): the DC in which to pool the discovery records.
        """
        # DRY-RUN handled by confctl
        self._conftool.set_and_verify('pooled', True, dnsdisc=self._conftool_selector, name=datacenter)

    def depool(self, datacenter):
        """Set the records as depooled in the given datacenter.

        Arguments:
            datacenter (str): the DC from which to depool the discovery records.
        """
        self.check_if_depoolable(datacenter)
        # DRY-RUN handled by confctl
        self._conftool.set_and_verify('pooled', False, dnsdisc=self._conftool_selector, name=datacenter)

    def check_if_depoolable(self, datacenter):
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
            message = "Services {svcs} cannot be depooled as they are only active in {dc}".format(
                svcs=", ".join(sorted(non_depoolable)), dc=datacenter)
            if self._dry_run:
                logger.debug(message)
            else:
                raise DiscoveryError(message)
