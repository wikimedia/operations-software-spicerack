"""DNS module tests."""
from collections import namedtuple
from unittest import mock

import dns
import pytest

from spicerack.dns import Dns, DnsError, DnsNotFound


# TODO: convert the mocked objects using dnspython objects. It requires quite some code given the structure of
#       dnspython API.
MockedDnsAddress = namedtuple('MockedDnsAddress', ['address'])
MockedDnsTarget = namedtuple('MockedDnsTarget', ['target'])
MockedDnsAnswer = namedtuple('MockedDnsAnswer', ['ttl', 'rrset'])


class MockedTarget:
    """Represent a DNS PTR response target."""

    def __init__(self, target):
        """Constructor."""
        self.target = target

    def to_text(self):
        """Required to mock the dnspython object."""
        return self.target


MOCKED_RESPONSES = {
    # (qname, record_type): MockedDnsAnswer(),
    ('host1.example.com', 'A'): MockedDnsAnswer(ttl=600, rrset=[MockedDnsAddress(address='10.0.0.1')]),
    ('host1.example.com', 'AAAA'): MockedDnsAnswer(ttl=600, rrset=[MockedDnsAddress(address='2001::1')]),
    ('10.0.0.1', 'PTR'): MockedDnsAnswer(ttl=600, rrset=[MockedDnsTarget(target=MockedTarget('host1.example.com.'))]),
    ('2001::1', 'PTR'): MockedDnsAnswer(ttl=600, rrset=[MockedDnsTarget(target=MockedTarget('host1.example.com.'))]),
    ('host2.example.com', 'A'): MockedDnsAnswer(ttl=600, rrset=[MockedDnsAddress(address='10.0.0.1')]),
    ('host2.example.com', 'AAAA'): dns.resolver.NoAnswer('Not found'),
    ('host3.example.com', 'A'):
        MockedDnsAnswer(ttl=600, rrset=[MockedDnsAddress(address='10.0.0.1'), MockedDnsAddress(address='10.0.0.2')]),
    ('host3.example.com', 'AAAA'):
        MockedDnsAnswer(ttl=600, rrset=[MockedDnsAddress(address='2001::1'), MockedDnsAddress(address='2001::2')]),
    ('2001::2', 'PTR'):
        MockedDnsAnswer(ttl=600, rrset=[
            MockedDnsTarget(target=MockedTarget('host3.example.com.')),
            MockedDnsTarget(target=MockedTarget('service.example.com.'))]),
    ('service.example.com', 'CNAME'): MockedDnsAnswer(
        ttl=600, rrset=[MockedDnsTarget(target=MockedTarget('host1.example.com.'))]),
    ('multiservice.example.com', 'CNAME'): MockedDnsAnswer(
        ttl=600, rrset=[MockedDnsTarget(target=MockedTarget('host1.example.com.')),
                        MockedDnsTarget(target=MockedTarget('host2.example.com.'))]),
    ('relative.example.com', 'CNAME'): MockedDnsAnswer(ttl=600, rrset=[MockedDnsTarget(target=MockedTarget('host1'))]),
}


def mocked_dns_query(qname, record_type):
    """Mock a dnspython query response."""
    if record_type == 'PTR':
        qname = dns.reversename.to_address(qname)
        if isinstance(qname, bytes):
            qname = qname.decode()

        if qname.startswith('192.168.') or qname.startswith('fe80::'):
            raise dns.exception.DNSException('Not defined')

    elif record_type in ('A', 'AAAA') and qname.startswith('raise.'):
        raise dns.exception.DNSException('Not defined')
    elif record_type in ('A', 'AAAA') and qname.startswith('missing.'):
        raise dns.resolver.NoAnswer('Not found')

    response = MOCKED_RESPONSES[(qname, record_type)]
    if isinstance(response, Exception):
        raise response

    return response


class TestDns:
    """Dns class tests."""

    @mock.patch('spicerack.dns.resolver.Resolver')
    def setup_method(self, _, mocked_resolver):
        """Initialize the test environment for Dns."""
        # pylint: disable=attribute-defined-outside-init
        self.mocked_resolver = mocked_resolver
        self.mocked_resolver.return_value.query = mocked_dns_query
        self.dns = Dns()

    def test_init(self):
        """The dns.resolver.Resolver should have been called without parameters."""
        self.mocked_resolver.assert_called_once_with()

    @mock.patch('spicerack.dns.resolver.Resolver')
    def test_init_with_nameserver(self, mocked_resolver):
        """When passing a nameserver address, this should be set in the dns Resolver too."""
        Dns(nameserver_address='127.0.0.1')
        mocked_resolver.assert_called_once_with(configure=False)
        assert mocked_resolver.return_value.nameservers == ['127.0.0.1']
        self.mocked_resolver.assert_called_once_with()

    @mock.patch('spicerack.dns.resolver.Resolver')
    def test_init_with_nameserver_and_port(self, mocked_resolver):
        """A non-standard port should be set in the dns Resolver if a nameserver is set."""
        Dns(nameserver_address='127.0.0.1', port=5353)
        mocked_resolver.assert_called_once_with(configure=False)
        assert mocked_resolver.return_value.nameservers == ['127.0.0.1']
        assert mocked_resolver.return_value.port == 5353
        self.mocked_resolver.assert_called_once_with()

    def test_resolve_ipv4(self):
        """Should return the list of IPv4 matching the name."""
        assert self.dns.resolve_ipv4('host1.example.com') == ['10.0.0.1']
        assert self.dns.resolve_ipv4('host3.example.com') == ['10.0.0.1', '10.0.0.2']

    def test_resolve_ipv6(self):
        """Should return the list of IPv6 matching the name."""
        assert self.dns.resolve_ipv6('host1.example.com') == ['2001::1']
        assert self.dns.resolve_ipv6('host3.example.com') == ['2001::1', '2001::2']

    def test_resolve_ips_ok(self):
        """Should return the list of IPv4 and IPv6 matching the name."""
        assert self.dns.resolve_ips('host1.example.com') == ['10.0.0.1', '2001::1']
        assert self.dns.resolve_ips('host3.example.com') == ['10.0.0.1', '10.0.0.2', '2001::1', '2001::2']

    def test_resolve_ips_one_only(self):
        """Should not fail there is no match for IPv4 or IPv6."""
        assert self.dns.resolve_ips('host2.example.com') == ['10.0.0.1']

    def test_resolve_ips_not_found(self):
        """Should raise DnsNotFound exception if the name raises NoAnswer for both A and AAAA records."""
        with pytest.raises(DnsNotFound, match='Record A or AAAA not found for missing.example.com'):
            self.dns.resolve_ips('missing.example.com')

    @pytest.mark.parametrize('address, response', (
        ('10.0.0.1', ['host1.example.com']),
        ('2001::1', ['host1.example.com']),
        ('2001::2', ['host3.example.com', 'service.example.com']),
    ))
    def test_resolve_ptr(self, address, response):
        """Should return the list of pointers matching the address."""
        assert self.dns.resolve_ptr(address) == response

    def test_resolve_cname(self):
        """Should return the target of a CNAME."""
        assert self.dns.resolve_cname('service.example.com') == 'host1.example.com'

    def test_resolve_cname_multiple_targets(self):
        """Should raise DnsError if more than one target is returned."""
        with pytest.raises(DnsError, match='Found multiple CNAMEs target for multiservice.example.com'):
            self.dns.resolve_cname('multiservice.example.com')

    def test_resolve_cname_relative_target(self):
        """Should raise DnsError if a relative target is found."""
        with pytest.raises(DnsError, match='Unsupported relative target host1 found'):
            self.dns.resolve_cname('relative.example.com')

    def test_resolve_not_found(self):
        """Should raise DnsNotFound exception if the record type is not defined for the qname."""
        with pytest.raises(DnsNotFound, match='Record AAAA not found for host2.example.com'):
            self.dns.resolve('host2.example.com', 'AAAA')

    @pytest.mark.parametrize('qname, record_type', (
        ('raise.example.com', 'A'),
        ('raise.example.com', 'AAAA'),
        (dns.reversename.from_address('192.168.1.1'), 'PTR'),
        (dns.reversename.from_address('fe80::1'), 'PTR'),
    ))
    def test_resolve_raise(self, qname, record_type):
        """Should raise DnsError if the qname is not defined."""
        with pytest.raises(DnsError, match='Unable to resolve {record_type} record for {qname}'.format(
                record_type=record_type, qname=qname)):
            self.dns.resolve(qname, record_type)
