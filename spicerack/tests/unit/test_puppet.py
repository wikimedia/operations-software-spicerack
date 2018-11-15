"""Puppet module tests."""
from unittest import mock

import pytest

from spicerack import puppet
from spicerack.administrative import Reason
from spicerack.remote import RemoteHosts


class TestPuppetHosts:
    """Test class for the PuppetHosts class."""

    def setup_method(self):
        """Setup the test environment."""
        # pylint: disable=attribute-defined-outside-init
        self.reason = Reason('Disable reason', 'user1', 'orchestration-host', task_id='T12345')
        self.mocked_remote_hosts = mock.MagicMock(spec_set=RemoteHosts)
        self.puppet_hosts = puppet.PuppetHosts(self.mocked_remote_hosts)

    def test_disable(self):
        """It should disable Puppet on the hosts."""
        self.puppet_hosts.disable(self.reason)
        self.mocked_remote_hosts.run_sync.assert_called_once_with(
            'disable-puppet {reason}'.format(reason=self.reason.quoted()))

    def test_enable(self):
        """It should enable Puppet on the hosts."""
        self.puppet_hosts.enable(self.reason)
        self.mocked_remote_hosts.run_sync.assert_called_once_with(
            'enable-puppet {reason}'.format(reason=self.reason.quoted()))

    def test_disabled(self):
        """It should disable Puppet, yield and enable Puppet on the hosts."""
        with self.puppet_hosts.disabled(self.reason):
            self.mocked_remote_hosts.run_sync.assert_called_once_with(
                'disable-puppet {reason}'.format(reason=self.reason.quoted()))
            self.mocked_remote_hosts.run_sync.reset_mock()

        self.mocked_remote_hosts.run_sync.assert_called_once_with(
            'enable-puppet {reason}'.format(reason=self.reason.quoted()))

    def test_disabled_on_raise(self):
        """It should re-enable Puppet even if the yielded code raises exception.."""
        with pytest.raises(RuntimeError):
            with self.puppet_hosts.disabled(self.reason):
                self.mocked_remote_hosts.run_sync.reset_mock()
                raise RuntimeError('Error')

        self.mocked_remote_hosts.run_sync.assert_called_once_with(
            'enable-puppet {reason}'.format(reason=self.reason.quoted()))
