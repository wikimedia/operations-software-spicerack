"""Management module tests."""
from unittest import mock

import pytest

from spicerack.management import Management, ManagementError
from spicerack.constants import ALL_DATACENTERS
from spicerack.dns import Dns, DnsError


class TestManagement:
    """Test class for the Managament class."""

    def setup_method(self):
        """Setup the test class."""
        # pylint: disable=attribute-defined-outside-init
        self.mocked_dns = mock.Mock(spec_set=Dns)
        self.management = Management(self.mocked_dns)

    def _setup_mocked_dns(self, *args):
        """Set the mocked Dns responses based on the given args."""
        if len(args) == 1:
            self.mocked_dns.resolve_ipv4.side_effect = args[0]
        else:
            self.mocked_dns.resolve_ipv4.side_effect = list(args)

    def test_get_management_internal_ok(self):
        """It should return the management interface for an internal hostname."""
        hostname = 'host1.eqiad.wmnet'
        mgmt = 'host1.mgmt.eqiad.wmnet'
        self._setup_mocked_dns('127.0.0.1')
        assert self.management.get_fqdn(hostname) == mgmt

    def test_get_management_internal_raise(self):
        """It should raise ManagementError for an internal hostname that doesn't resolve."""
        hostname = 'host1.eqiad.wmnet'
        self._setup_mocked_dns(DnsError)
        with pytest.raises(ManagementError, match='Invalid management FQDN'):
            self.management.get_fqdn(hostname)

    def test_get_management_external_known_dc_ok(self):
        """It should return the management interface for an external hostname that matches naming conventions."""
        hostname = 'host2001.example.com'
        mgmt = 'host2001.mgmt.codfw.wmnet'
        self._setup_mocked_dns('127.0.0.1')
        assert self.management.get_fqdn(hostname) == mgmt

    def test_get_management_external_known_dc_raise(self):
        """It should raise ManagementError for an external hostname that matches naming conventions."""
        hostname = 'host2001.example.com'
        self._setup_mocked_dns(DnsError)
        with pytest.raises(ManagementError, match='Unable to find management FQDN for host'):
            self.management.get_fqdn(hostname)

    @pytest.mark.parametrize('dc_index', range(len(ALL_DATACENTERS)))
    def test_get_management_external_guess_ok(self, dc_index):
        """It should find the management interface for an external hostname that doesn't match naming conventions."""
        hostname = 'host1.example.com'
        mgmt = 'host1.mgmt.{dc}.wmnet'.format(dc=ALL_DATACENTERS[dc_index])
        ret_values = [DnsError] * dc_index + ['127.0.0.1']
        self._setup_mocked_dns(*ret_values)
        assert self.management.get_fqdn(hostname) == mgmt

    def test_get_management_external_guess_raise(self):
        """It should raise ManagementError for an external hostname that doesn't match naming conventions."""
        hostname = 'host1.example.com'
        self._setup_mocked_dns(DnsError)
        with pytest.raises(ManagementError, match='Unable to find management FQDN for host'):
            self.management.get_fqdn(hostname)
