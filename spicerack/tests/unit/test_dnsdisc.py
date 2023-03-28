"""Dnsdisc module tests."""
import logging
from collections import namedtuple
from ipaddress import ip_address
from unittest import mock

import dns
import pytest
from dns.exception import DNSException
from wmflib.config import load_yaml_config

from spicerack.dnsdisc import Discovery, DiscoveryCheckError, DiscoveryError
from spicerack.tests import get_fixture_path

MockedRecord = namedtuple("Record", ["address"])
DISCOVERY_RESPONSE_OK = """id 57640
opcode QUERY
rcode NOERROR
flags QR RD RA
;QUESTION
record1.discovery.wmnet. IN A
;ANSWER
record1.discovery.wmnet. 300 IN A 10.10.10.10
;AUTHORITY
;ADDITIONAL
"""
DISCOVERY_RESPONSE_ERROR = """id 6890
opcode QUERY
rcode NXDOMAIN
flags QR RD RA
;QUESTION
record1.discovery.wmnet. IN A
;ANSWER
;AUTHORITY
wmnet. 2434 IN SOA ns0.wikimedia.org. hostmaster.wikimedia.org. 2023031514 43200 7200 1209600 3600
;ADDITIONAL
"""


def mock_obj(datacenter, svc, pooled):
    """Creates a mock conftool object."""
    obj = mock.MagicMock()
    obj.tags = {"dnsdisc": svc}
    obj.name = datacenter
    obj.pooled = pooled
    return obj


def get_mocked_dns_query_message(fail: bool) -> dns.message.Message:
    """Get a mocked low level response to be used with udp_with_fallback() mocks."""
    response = DISCOVERY_RESPONSE_ERROR if fail else DISCOVERY_RESPONSE_OK
    message = dns.message.from_text(response)
    message.find_rrset(
        message.answer,
        dns.name.from_text("record1.discovery.wmnet"),
        dns.rdataclass.from_text("IN"),
        dns.rdatatype.from_text("A"),
        create=True,
    )
    return message


class MockedQuery:
    """Class to mock a return object from a call to dns.resolver.query()."""

    def __init__(self, record):
        """Initialize it with the query."""
        if record == "fail.svc.eqiad.wmnet":
            self.address = "10.1.1.1"
            self.ttl = 600
        elif record.startswith("raise"):
            raise DNSException
        else:
            self.address = "10.0.0.1"
            self.ttl = 10

        self.record = MockedRecord(self.address)

    def __getitem__(self, _):
        """Allow indexing access."""
        return self.record

    def __iter__(self):
        """Allow iterating on results."""
        return iter([self.record])


class MockDnsResult:
    """Mocks dns.message.ChainingResult."""

    def __init__(self, ipaddr: str):
        """Creates the chaining result."""
        # Mocks a rrset
        a_record = mock.MagicMock()
        a_record.address = ipaddr
        # Where dns.resolver.Answer gets the data from
        self.answer = [a_record]
        self.canonical_name = "a_name"
        self.minimum_ttl = 10


class TestDiscovery:
    """Discovery class tests."""

    @mock.patch("spicerack.dnsdisc.resolver", autospec=True)
    def setup_method(self, _, mocked_resolver):
        """Initialize the test environment for Discovery."""
        # pylint: disable=attribute-defined-outside-init
        self.records = ["record1", "record2"]
        self.conftool_records = "(" + "|".join(self.records) + ")"

        self.mocked_confctl = mock.MagicMock()
        self.authdns_servers = load_yaml_config(get_fixture_path("discovery", "authdns.yaml"))
        self.mocked_resolver = mocked_resolver
        self.mocked_resolver.Resolver.return_value.query = MockedQuery

        self.discovery = Discovery(
            conftool=self.mocked_confctl, authdns_servers=self.authdns_servers, records=self.records, dry_run=False
        )
        self.discovery_single = Discovery(
            conftool=self.mocked_confctl, authdns_servers=self.authdns_servers, records=self.records[0:1], dry_run=False
        )
        self.discovery_dry_run = Discovery(
            conftool=self.mocked_confctl, authdns_servers=self.authdns_servers, records=self.records
        )

    def test_resolve_address(self):
        """Calling resolve_address() sould raise DiscoveryError if unable to resolve the address."""
        with pytest.raises(DiscoveryError, match="Unable to resolve raise.svc.eqiad.wmnet"):
            self.discovery_single.resolve_address("raise.svc.eqiad.wmnet")

    def test_update_ttl(self):
        """Calling update_ttl() should update the TTL of the conftool objects."""
        self.discovery.update_ttl(10)
        self.mocked_confctl.assert_has_calls([mock.call.set_and_verify("ttl", 10, dnsdisc=self.conftool_records)])

    @mock.patch("wmflib.decorators.time.sleep")
    def test_update_ttl_dry_run(self, mocked_sleep):
        """Calling update_ttl() in DRY-RUN mode should not raise when verifying the TTL."""
        self.discovery_dry_run.update_ttl(20)
        assert not mocked_sleep.called

    @mock.patch("wmflib.decorators.time.sleep")
    def test_update_ttl_ko(self, mocked_sleep):
        """Calling update_ttl() should raise DiscoveryCheckError if unable to verify the value."""
        with pytest.raises(DiscoveryCheckError, match="Expected TTL '20', got '10'"):
            self.discovery.update_ttl(20)

        assert mocked_sleep.called

    def test_check_ttl_ok(self):
        """Calling check_ttl() should verify that the correct TTL is returned by the authoritative nameservers."""
        self.discovery.check_ttl(10)

    @pytest.mark.parametrize(
        "expected, name",
        (
            ("record1.discovery.wmnet TTL is correct", "discovery_single"),
            ("['record1', 'record2'] discovery.wmnet TTLs are correct", "discovery"),
        ),
    )
    def test_check_ttl_log_message(self, expected, name, caplog):
        """The log message of check_ttl should reflect if a singular or multiple records matches."""
        with caplog.at_level(logging.INFO):
            getattr(self, name).check_ttl(10)
        assert expected in caplog.text

    @mock.patch("wmflib.decorators.time.sleep")
    def test_check_ttl_ko(self, mocked_sleep):
        """Calling check_ttl() should raise DiscoveryCheckError if the check fails."""
        with pytest.raises(DiscoveryCheckError, match="Expected TTL '20', got '10'"):
            self.discovery.check_ttl(20)

        assert mocked_sleep.called

    def test_check_record_ok(self):
        """Calling check_record() should verify that a record has a certain value on the nameservers."""
        self.discovery.check_record(self.records[0], "ok.svc.eqiad.wmnet")

    @mock.patch("wmflib.decorators.time.sleep")
    def test_check_record_ko(self, mocked_sleep):
        """Calling check_record() should raise DiscoveryError if unable to check the records."""
        with pytest.raises(
            DiscoveryError,
            match=f"Resolved record {self.records[0]} with the wrong IP",
        ):
            self.discovery.check_record(self.records[0], "fail.svc.eqiad.wmnet")

        assert mocked_sleep.called

    def test_resolve(self):
        """Calling resolve() should raise a DiscoveryError if unable to resolve the address."""
        with pytest.raises(DiscoveryError, match="Unable to resolve raise.discovery.wmnet from authdns"):
            for _ in self.discovery.resolve(name="raise"):
                pass

    @pytest.mark.parametrize("func, value", (("pool", True), ("depool", False)))
    def test_pool(self, func, value):
        """Calling pool() should update the pooled value of the conftool objects to True."""
        getattr(self.discovery, func)("eqiad")
        self.mocked_confctl.set_and_verify.assert_called_once_with(
            "pooled", value, dnsdisc=self.conftool_records, name="eqiad"
        )

    def test_active_datacenters(self):
        """The list of active datacenter is correctly composed."""
        self.mocked_confctl.get.return_value = [
            mock_obj("dcA", "svcA", True),
            mock_obj("dcB", "svcA", False),
            mock_obj("dcA", "svcB", True),
            mock_obj("dcB", "svcB", True),
        ]
        expected = {"svcA": ["dcA"], "svcB": ["dcA", "dcB"]}
        assert expected == self.discovery.active_datacenters
        self.mocked_confctl.get.assert_called_once_with(dnsdisc=self.conftool_records)

    def test_check_if_depoolable_ok(self):
        """No exception is raised if the active datacenters are ok."""
        self.mocked_confctl.get.return_value = [
            mock_obj("dcA", "svcA", False),
            mock_obj("dcB", "svcA", True),
            mock_obj("dcA", "svcB", True),
            mock_obj("dcB", "svcB", True),
        ]
        self.discovery.check_if_depoolable("dcA")
        # now let's assume a service is competely down. We should still get
        # a green light.
        self.mocked_confctl.get.return_value = [
            mock_obj("dcA", "svcA", False),
            mock_obj("dcB", "svcA", False),
            mock_obj("dcA", "svcB", True),
            mock_obj("dcB", "svcB", True),
        ]
        self.discovery.check_if_depoolable("dcA")

    def test_check_if_depoolable_ko(self):
        """A DiscoveryError is raised when a service would be taken out of commission."""
        self.mocked_confctl.get.return_value = [
            mock_obj("dcA", "svcA", False),
            mock_obj("dcB", "svcA", True),
            mock_obj("dcA", "svcB", False),
            mock_obj("dcB", "svcB", False),
        ]
        with pytest.raises(
            DiscoveryError,
            match="Services svcA cannot be depooled as they are only active in dcB",
        ):
            self.discovery.check_if_depoolable("dcB")
        self.mocked_confctl.get.return_value = [
            mock_obj("dcA", "svcA", False),
            mock_obj("dcB", "svcA", True),
            mock_obj("dcA", "svcB", False),
            mock_obj("dcB", "svcB", True),
        ]
        with pytest.raises(
            DiscoveryError,
            match="Services svcA, svcB cannot be depooled as they are only active in dcB",
        ):
            self.discovery.check_if_depoolable("dcB")

    def test_check_if_depoolable_ko_dry_run(self, caplog):
        """Doesn't raise exception when a service would be taken out of commission but in dry-run mode."""
        self.mocked_confctl.get.return_value = [
            mock_obj("dcA", "svcA", False),
            mock_obj("dcB", "svcA", True),
            mock_obj("dcA", "svcB", False),
            mock_obj("dcB", "svcB", False),
        ]
        with caplog.at_level(logging.DEBUG):
            self.discovery_dry_run.check_if_depoolable("dcB")
        assert "cannot be depooled as they are only active in" in caplog.text

    def test_resolve_with_client_ip(self):
        """Correctly returns the ip address for the query."""
        with mock.patch("dns.query.udp_with_fallback") as mock_query:
            retval = {name: ip_address("10.10.10.10") for name in self.authdns_servers}
            mock_query.return_value = (get_mocked_dns_query_message(fail=False), False)
            assert self.discovery_single.resolve_with_client_ip("record1", ip_address("10.24.1.0")) == retval

    def test_resolve_bad_record(self):
        """Requesting a record that is not present will raise a DiscoveryError."""
        with pytest.raises(DiscoveryError, match="Record 'nope' not found"):
            self.discovery_single.resolve_with_client_ip("nope", ip_address("10.24.1.0"))

    def test_resolve_bad_query(self):
        """Any exception thrown by dns.query.udp_with_fallback will result in a DiscoveryError."""
        with mock.patch("dns.query.udp_with_fallback") as mock_query:
            mock_query.side_effect = ValueError("test this")
            with pytest.raises(DiscoveryError, match="Unable to resolve record1.discovery.wmnet"):
                self.discovery_single.resolve_with_client_ip("record1", ip_address("10.24.1.0"))

    def test_resolve_bad_answer(self):
        """When the query response is empty or contains an invalid IP, a DiscoveryError is raised."""
        with mock.patch("dns.query.udp_with_fallback") as mock_query:
            mock_query.return_value = (get_mocked_dns_query_message(fail=True), False)
            with pytest.raises(DiscoveryError, match="Unable to resolve record1.discovery.wmnet"):
                self.discovery_single.resolve_with_client_ip("record1", ip_address("10.24.1.0"))
