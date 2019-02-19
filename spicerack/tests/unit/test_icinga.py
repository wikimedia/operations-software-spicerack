"""Icinga module tests."""
from datetime import timedelta
from unittest import mock

import pytest

from ClusterShell.MsgTree import MsgTreeElem
from cumin import NodeSet

from spicerack import icinga
from spicerack.administrative import Reason
from spicerack.remote import RemoteHosts


def set_mocked_icinga_host_output(mocked_icinga_host, output):
    """Setup the mocked icinga_host return value with the given output."""
    out = MsgTreeElem(output.encode(), parent=MsgTreeElem())
    mocked_icinga_host.run_sync.return_value = iter([(NodeSet('icinga-host'), out)])


class TestIcinga:
    """Test class for the Icinga class."""

    def setup_method(self):
        """Setup the test environment."""
        # pylint: disable=attribute-defined-outside-init
        self.reason = Reason('Downtime reason', 'user1', 'orchestration-host', task_id='T12345')
        self.mocked_icinga_host = mock.MagicMock(spec_set=RemoteHosts)
        set_mocked_icinga_host_output(self.mocked_icinga_host, '/var/lib/icinga/rw/icinga.cmd')
        self.icinga = icinga.Icinga(self.mocked_icinga_host)

    def test_command_file_ok(self):
        """It should return the command_file setting from the Icinga configuration."""
        assert self.icinga.command_file == '/var/lib/icinga/rw/icinga.cmd'

    @pytest.mark.parametrize('output', (
        '',
        ' ',
    ))
    def test_command_file_raise(self, output):
        """It should raise IcingaError if failing to get the configuration value."""
        set_mocked_icinga_host_output(self.mocked_icinga_host, output)
        with pytest.raises(icinga.IcingaError, match='Unable to read command_file configuration'):
            self.icinga.command_file  # pylint: disable=pointless-statement

    def test_command_file_cached(self):
        """It should return the already cached value of the command_file if accessed again."""
        command_file = self.icinga.command_file
        self.mocked_icinga_host.reset_mock()
        assert self.icinga.command_file == command_file
        assert not self.mocked_icinga_host.called

    @mock.patch('spicerack.icinga.time.time', return_value=1514764800)
    def test_hosts_downtimed(self, mocked_time):
        """It should downtime the hosts on Icinga, yield and delete the downtime once done."""
        hosts = ['host1']
        call = 'icinga-downtime -h "host1" -d 14400 -r {reason}'.format(reason=self.reason.quoted())

        with self.icinga.hosts_downtimed(hosts, self.reason):
            self.mocked_icinga_host.run_sync.assert_called_once_with(call)
            self.mocked_icinga_host.run_sync.reset_mock()

        self.mocked_icinga_host.run_sync.assert_has_calls([
            mock.call('echo -n "[1514764800] DEL_DOWNTIME_BY_HOST_NAME;host1" > /var/lib/icinga/rw/icinga.cmd')])
        assert mocked_time.called

    def test_downtime_is_kept_when_exception_is_raised(self):
        """Downtime should not be removed if an exception is raised."""
        hosts = ['host1']
        call = 'icinga-downtime -h "host1" -d 14400 -r {reason}'.format(reason=self.reason.quoted())

        with pytest.raises(ValueError):
            with self.icinga.hosts_downtimed(hosts, self.reason):
                self.mocked_icinga_host.run_sync.assert_called_once_with(call)
                self.mocked_icinga_host.run_sync.reset_mock()
                raise ValueError()
        assert not self.mocked_icinga_host.run_sync.called

    def test_downtime_is_removed_when_exception_is_raised(self):
        """Downtime should not be removed if an exception is raised."""
        hosts = ['host1']
        call = 'icinga-downtime -h "host1" -d 14400 -r {reason}'.format(reason=self.reason.quoted())

        with pytest.raises(ValueError):
            with self.icinga.hosts_downtimed(hosts, self.reason, remove_on_error=True):
                self.mocked_icinga_host.run_sync.assert_called_once_with(call)
                self.mocked_icinga_host.run_sync.reset_mock()
                raise ValueError()
        assert self.mocked_icinga_host.run_sync.called

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

    @pytest.mark.parametrize('hosts', (
        ['host1'],
        ['host1', 'host2'],
        NodeSet('host1'),
        NodeSet('host[1-9]'),
    ))
    @mock.patch('spicerack.icinga.time.time', return_value=1514764800)
    def test_host_command(self, mocked_time, hosts):
        """It should run the specified command for all the hosts on the Icinga server."""
        self.icinga.host_command('TEST_COMMAND', hosts, 'arg1', 'arg2')
        calls = [
            'echo -n "[1514764800] TEST_COMMAND;{host};arg1;arg2" > /var/lib/icinga/rw/icinga.cmd'.format(host=host)
            for host in hosts]

        self.mocked_icinga_host.run_sync.assert_called_with(*calls)
        assert mocked_time.called

    @mock.patch('spicerack.icinga.time.time', return_value=1514764800)
    def test_remove_downtime(self, mocked_time):
        """It should remove the downtime for the hosts on the Icinga server."""
        self.icinga.remove_downtime(NodeSet('host1'))
        self.mocked_icinga_host.run_sync.assert_called_with(
            'echo -n "[1514764800] DEL_DOWNTIME_BY_HOST_NAME;host1" > /var/lib/icinga/rw/icinga.cmd')
        assert mocked_time.called
