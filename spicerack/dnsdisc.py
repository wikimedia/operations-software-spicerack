"""DNS Discovery module."""
import logging

from dns import resolver

from spicerack.decorators import retry
from spicerack.exceptions import SpicerackError


logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


class DiscoveryError(SpicerackError):
    """Custom exception class for errors of the Discovery class."""


class Discovery:
    """Class to manage Confctl discovery objects."""

    def __init__(self, conftool, remote, records, dry_run=True):
        """Initialize the instance.

        Arguments:
            conftool (spicerack.confctl.ConftoolEntity): the conftool instance for the discovery type objects.
            remote (spicerack.remote.Remote): the Remote instance, pre-initialized.
            records (list): list of strings, each one must be a Discovery DNS record name.
            dry_run (bool, optional): whether this is a DRY-RUN.
        """
        self._conftool = conftool
        self._remote = remote
        self._records = records
        self._dry_run = dry_run

        self._resolvers = {}
        for nameserver in self._remote.query('A:dns-auth').hosts:
            self._resolvers[nameserver] = resolver.Resolver()
            self._resolvers[nameserver].nameservers = [rdata.address for rdata in resolver.query(nameserver)]

    def resolve_address(self, name):
        """Resolve the IP of a given record.

        TODO: move a more generalized version of this into a DNS resolver module.

        Arguments:
            name (str): the DNS record to resolve.

        Returns:
            str: the resolved IP address.

        """
        # Querying the first resolver
        return next(iter(self._resolvers.values())).query(name)[0].address

    def update_ttl(self, ttl):
        """Update the TTL for all registered records.

        Arguments:
            ttl (int): the new TTL value to set.

        Raises:
            DiscoveryError: if the check of the modified TTL fail and not in DRY-RUN mode.

        """
        # DRY-RUN handled by confctl
        dnsdisc = '({regexp})'.format(regexp='|'.join(self._records))
        logger.debug('Updating the TTL of %s to %d seconds', dnsdisc, ttl)
        self._conftool.update({'ttl': ttl}, dnsdisc=dnsdisc)

        if self._dry_run:
            logger.info('Skipping check of modified TTL in DRY-RUN mode')
        else:
            self.check_ttl(ttl)

    @retry(backoff_mode='linear', exceptions=(DiscoveryError,))
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
                raise DiscoveryError("Expected TTL '{expected}', got '{ttl}' for record {record}".format(
                    expected=ttl, ttl=record.ttl, record=record))

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
        logger.debug('Checking that %s.discovery.wmnet records matches %s (%s)', name, expected_name, expected_address)

        failed = False
        for record in self.resolve(name=name):
            if not self._dry_run and record[0].address != expected_address:
                failed = True
                logger.error("Expected IP '%s', got '%s' for record %s", expected_address, record[0].address, name)

        if failed:
            raise DiscoveryError('Failed to check record {name}'.format(name=name))

    def resolve(self, name=None):
        """Generator that yields the resolved records.

        TODO: move a more generalized version of this into a DNS resolver module.

        Arguments:
            name (str, optional): record name to use for the resolution instead of self.records.

        Yields:
            dns.resolver.Answer: the DNS response.

        """
        if name is not None:
            records = [name]
        else:
            records = self._records

        for nameserver, dns_resolver in self._resolvers.items():
            for record in records:
                answer = dns_resolver.query('{record}.discovery.wmnet'.format(record=record))
                logger.debug('[%s] %s -> %s TTL %d', nameserver, record, answer[0].address, answer.ttl)
                yield answer
