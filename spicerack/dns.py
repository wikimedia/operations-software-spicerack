"""DNS module."""
import logging

import dns

from spicerack.exceptions import SpicerackError

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


class DnsError(SpicerackError):
    """Custom exception class for errors of the Dns class."""


class DnsNotFound(DnsError):
    """Custom exception class to indicate the record was not found.

    One or more resource records exist for this domain but there isn’t a record matching the resource record type.
    """


class Dns:
    """Class to interact with the DNS."""

    def __init__(self, *, nameserver_address=None, dry_run=True):
        """Initialize the instance.

        Arguments:
            nameserver_address (str, optional): the nameserver address to use, if not set uses the OS configuration.
            dry_run (bool, optional): whether this is a DRY-RUN.
        """
        self._dry_run = dry_run
        if nameserver_address:
            self._resolver = dns.resolver.Resolver(configure=False)
            self._resolver.nameservers = [nameserver_address]
        else:
            self._resolver = dns.resolver.Resolver()

    def resolve_ipv4(self, name):
        """Perform a DNS lookup for an A record for the given name.

        Arguments:
            name (str): the name to resolve.

        Returns:
            list: the list of IPv4 addresses as strings returned by the DNS response.

        """
        return self._resolve_addresses(name, 'A')

    def resolve_ipv6(self, name):
        """Perform a DNS lookup for an AAAA record for the given name.

        Arguments:
            name (str): the name to resolve.

        Returns:
            list: the list of IPv6 addresses as strings returned by the DNS response.

        """
        return self._resolve_addresses(name, 'AAAA')

    def resolve_ips(self, name):
        """Perform a DNS lookup for A and AAAA records for the given name.

        Arguments:
            name (str): the name to resolve.

        Returns:
            list: the list of IPv4 and IPv6 addresses as strings returned by the DNS response.

        """
        addresses = []
        for func in ('resolve_ipv4', 'resolve_ipv6'):
            try:
                addresses += getattr(self, func)(name)
            except DnsNotFound:
                pass  # Allow single stack answers

        if not addresses:
            raise DnsNotFound('Record A or AAAA not found for {name}'.format(name=name))

        return addresses

    def resolve_ptr(self, address):
        """Perform a DNS lookup for PTR record for the given address.

        Arguments:
            address (str): the IPv4 or IPv6 address to resolve.

        Returns:
            list: the list of absolute target PTR records as strings, without the trailing dot.

        """
        response = self.resolve(dns.reversename.from_address(address), 'PTR')
        return self._parse_targets(response.rrset)

    def resolve_cname(self, name):
        """Perform a DNS lookup for CNAME record for the given name.

        Arguments:
            name (str): the name to resolve.

        Returns:
            str: the absolute target name for this CNAME, without the trailing dot.

        """
        targets = self._parse_targets(self.resolve(name, 'CNAME').rrset)
        if len(targets) != 1:
            raise DnsError('Found multiple CNAMEs target for {name}: {targets}'.format(name=name, targets=targets))

        return targets[0]

    def resolve(self, qname, record_type):
        """Perform a DNS lookup for the given qname and record type.

        Arguments:
            qname (str): the name or address to resolve.
            record_type (str): the DNS record type to lookup for, like 'A', 'AAAA', 'PTR', etc.

        Returns:
            dns.resolver.Answer: the DNS response.

        Raises:
            spicerack.dns.DnsNotFound: if there are no records for the given record type but the qname has records for
                different record type(s).
            spicerack.dns.DnsError: on generic error.

        """
        try:
            response = self._resolver.query(qname, record_type)
            logger.debug('Resolved %s record for %s: %s', record_type, qname, response)
        except dns.resolver.NoAnswer as e:
            raise DnsNotFound('Record {record_type} not found for {qname}'.format(
                record_type=record_type, qname=qname)) from e
        except dns.exception.DNSException as e:
            raise DnsError('Unable to resolve {record_type} record for {qname}'.format(
                record_type=record_type, qname=qname)) from e

        return response

    def _resolve_addresses(self, name, record_type):
        """Extract and return all the matching addresses for the given name and record type.

        Arguments:
            name (str): the name to resolve.
            record_type (str): the DNS record type to lookup for, like 'A' and 'AAAA'.

        Returns:
            list: the list of IPv4 or IPv6 addresses as strings returned by the DNS response.

        """
        return [rdata.address for rdata in self.resolve(name, record_type).rrset]

    @staticmethod
    def _parse_targets(rrset):
        """Extract and return all the matching names from the given rrset without the trailing dot.

        Arguments:
            rrset (dns.rrset.RRset): the RRset to parse.

        Returns:
            list: the list of absolute target record names as strings without the trailing dot.

        Raises:
            spicerack.dns.DnsError: if a relative record is found.

        """
        targets = []
        for rdata in rrset:
            target = rdata.target.to_text()
            if target[-1] != '.':
                raise DnsError('Unsupported relative target {target} found'.format(target=target))

            targets.append(target[:-1])

        return targets