"""Icinga module tests."""
from datetime import timedelta
from unittest import mock

import pytest

from cumin import NodeSet

from spicerack import icinga
from spicerack.administrative import Reason
from spicerack.remote import RemoteHosts


class TestIcinga:
    """Test class for the Icinga class."""

    def setup_method(self):
        """Setup the test environment."""
        # pylint: disable=attribute-defined-outside-init
        self.reason = Reason('Downtime reason', 'user1', 'icinga-host', task_id='T12345')
        self.mocked_icinga_host = mock.MagicMock(spec_set=RemoteHosts)
        self.icinga = icinga.Icinga(self.mocked_icinga_host)

    @pytest.mark.parametrize('hosts', (
        ['host1'],
        ['host1', 'host2'],
        NodeSet('host1'),
        NodeSet('host[1-9]'),
    ))
    def test_downtime_hosts_default_params(self, hosts):
        """It should downtime the hosts on the Icinga server with the default params."""
        self.icinga.downtime_hosts(hosts, self.reason)
        calls = [('icinga-downtime -h "{host}" -d 14400 -r {reason}').format(host=host, reason=self.reason.quoted())
                 for host in hosts]
        self.mocked_icinga_host.run_sync.assert_called_once_with(*calls)

    def test_downtime_hosts_custom_duration(self):
        """It should downtime the hosts for the given duration on the Icinga server."""
        self.icinga.downtime_hosts(['host1'], self.reason, duration=timedelta(minutes=30))
        self.mocked_icinga_host.run_sync.assert_called_once_with((
            'icinga-downtime -h "host1" -d 1800 -r {reason}'.format(reason=self.reason.quoted())))

    def test_downtime_hosts_invalid_duration(self):
        """It should raise IcingaError if the duration is too short."""
        with pytest.raises(icinga.IcingaError, match='Downtime duration must be at least 1 minute'):
            self.icinga.downtime_hosts(['host1'], self.reason, duration=timedelta(seconds=59))

    def test_downtime_hosts_no_hosts(self):
        """It should raise IcingaError if there are no hosts to downtime."""
        with pytest.raises(icinga.IcingaError, match='Got empty hosts list to downtime'):
            self.icinga.downtime_hosts([], self.reason)
