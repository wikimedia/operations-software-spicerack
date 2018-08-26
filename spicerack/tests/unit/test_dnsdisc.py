"""Dnsdisc module tests."""
from collections import namedtuple
from unittest import mock

import pytest

from spicerack.dnsdisc import Discovery, DiscoveryError

from spicerack.tests import caplog_not_available


MockedRecord = namedtuple('Record', ['address'])


class MockedQuery:
    """Class to mock a return object from a call to dns.resolver.query()."""

    def __init__(self, record):
        """Initialize it with the query."""
        if record == 'fail.svc.eqiad.wmnet':
            self.address = '10.1.1.1'
            self.ttl = 600
        else:
            self.address = '10.0.0.1'
            self.ttl = 10

        self.record = MockedRecord(self.address)

    def __getitem__(self, _):
        """Allow indexing access."""
        return self.record


class TestDiscovery:
    """Discovery class tests."""

    @mock.patch('spicerack.dnsdisc.resolver')
    def setup_method(self, _, mocked_resolver):
        """Initialize the test environment for Discovery."""
        # pylint: disable=attribute-defined-outside-init
        self.records = ['record1', 'record2']
        self.nameservers = ['authdns1', 'authdns2']

        self.mocked_confctl = mock.MagicMock()
        self.mocked_remote = mock.MagicMock()
        self.mocked_remote.query.return_value.hosts = self.nameservers

        self.mocked_resolver = mocked_resolver
        self.mocked_resolver.Resolver.return_value.query = MockedQuery

        self.discovery = Discovery(self.mocked_confctl, self.mocked_remote, self.records, dry_run=False)
        self.discovery_dry_run = Discovery(self.mocked_confctl, self.mocked_remote, self.records)

    def test_init(self):
        """Creating a Discovery instance should initialize the resolvers based on a cumin query."""
        self.mocked_remote.query.assert_has_calls([mock.call('A:dns-auth')] * 2)
        self.mocked_resolver.Resolver.assert_called_with()
        assert self.mocked_resolver.Resolver.call_count == 4
        self.mocked_resolver.query.assert_has_calls(
            [mock.call(self.nameservers[0]), mock.call(self.nameservers[1])], any_order=True)
        assert self.mocked_resolver.query.call_count == 4

    def test_update_ttl(self):
        """Calling update_ttl() should update the TTL of the conftool objects."""
        self.discovery.update_ttl(10)
        records = '({records})'.format(records='|'.join(self.records))
        self.mocked_confctl.assert_has_calls([mock.call.update({'ttl': 10}, dnsdisc=records)])

    @pytest.mark.skipif(caplog_not_available(), reason='Requires caplog fixture')
    def test_update_ttl_dry_run(self, caplog):
        """Calling update_ttl() in DRY-RUN mode should skip the verification."""
        self.discovery_dry_run.update_ttl(10)
        assert 'Skipping check of modified TTL' in caplog.text

    def test_check_ttl_ok(self):
        """Calling check_ttl() should verify that the correct TTL is returned by the authoritative nameservers."""
        self.discovery.check_ttl(10)

    @mock.patch('spicerack.decorators.time.sleep')
    def test_check_ttl_ko(self, mocked_sleep):
        """Calling check_ttl() should raise DiscoveryError if the check fails."""
        with pytest.raises(DiscoveryError, match="Expected TTL '20', got '10'"):
            self.discovery.check_ttl(20)

        assert mocked_sleep.called

    def test_check_record_ok(self):
        """Calling check_record() should verify that a record has a certain value on the nameservers."""
        self.discovery.check_record(self.records[0], 'ok.svc.eqiad.wmnet')

    @mock.patch('spicerack.decorators.time.sleep')
    def test_check_record_ko(self, mocked_sleep):
        """Calling check_record() should raise DiscoveryError if unable to check the records."""
        with pytest.raises(DiscoveryError, match='Failed to check record {record}'.format(record=self.records[0])):
            self.discovery.check_record(self.records[0], 'fail.svc.eqiad.wmnet')

        assert mocked_sleep.called
