"""Icinga module."""
import json
import logging
import time

from contextlib import contextmanager
from datetime import timedelta
from typing import Dict, Iterator, List, Mapping, Optional, Sequence

from cumin.transports import Command

from spicerack.administrative import Reason
from spicerack.exceptions import SpicerackError
from spicerack.remote import RemoteHosts
from spicerack.typing import TypeHosts


DOWNTIME_COMMAND: str = 'icinga-downtime -h "{hostname}" -d {duration} -r {reason}'
ICINGA_DOMAIN: str = 'icinga.wikimedia.org'
MIN_DOWNTIME_SECONDS: int = 60  # Minimum time in seconds the downtime can be set
logger = logging.getLogger(__name__)


class IcingaError(SpicerackError):
    """Custom exception class for errors of this module."""


class IcingaStatusParseError(IcingaError):
    """Custom exception class for errors while parsing the Icinga status."""


class IcingaStatusNotFoundError(IcingaError):
    """Custom exception class for errors while parsing the Icinga status."""


class HostsStatus(dict):
    """Represent the status of all Icinga checks for a set of hosts."""

    @property
    def optimal(self) -> bool:
        """Returns :py:data:`True` if all the hosts are optimal, :py:data:`False` otherwise.

        Returns:
            bool: whether all hosts are optimal.

        """
        return all(status.optimal for status in self.values())

    @property
    def non_optimal_hosts(self) -> List[str]:
        """Return the list of hostnames that are not in an optimal state.

        They can either not being up and running or have at least one failed service.

        Returns:
            list: a list of strings with the hostnames.

        """
        return [hostname for hostname, status in self.items() if not status.optimal]

    @property
    def failed_services(self) -> Dict[str, List[str]]:
        """Return the list of service names that are failing for each host that has at least one.

        Returns:
            dict: a dict with hostnames as keys and list of failing service name strings as values.

        """
        return {status.name: status.failed_services for status in self.values() if not status.optimal}

    @property
    def failed_hosts(self) -> List[str]:
        """Return the list of hostnames that are not up and running. They can either be down or unreachable.

        Returns:
            list: the list of strings with the hostnames.

        """
        return [status.name for status in self.values() if status.state != HostStatus.STATE_UP]


class HostStatus:
    """Represent the status of all Icinga checks for a single host."""

    STATE_UP = 'UP'
    """:py:class:`str`: the Icinga value for a host that is up and running. The other values for the Icinga host state
    are ``DOWN`` and ``UNREACHABLE``."""

    def __init__(self, *, name: str, state: str, optimal: bool, failed_services: Sequence[Mapping],
                 downtimed: bool, notifications_enabled: bool):
        """Initialize the instance.

        Arguments:
            name (str): the hostname.
            state (str): the Icinga state for the host, one of ``UP``, ``DOWN``, UNREACHABLE``.
            optimal (bool): whether the host is in optimal state (all green).
            failed_services (list): a list of dictionaries representing the failed services.
            downtimed (bool): whether the host is currently downtimed.
            notifications_enabled: (bool): whether the host has notifications enabled.

        """
        self.name = name
        self.state = state
        self.optimal = optimal
        self.failed_services_raw = failed_services  # TODO: could be improved creating a ServiceStatus class
        self.downtimed = downtimed
        self.notifications_enabled = notifications_enabled

    @property
    def failed_services(self) -> List[str]:
        """Return the list of service names that are failing.

        Returns:
            list: a list of strings with the check names.

        """
        return [service['name'] for service in self.failed_services_raw]


class Icinga:
    """Class to interact with the Icinga server."""

    def __init__(self, icinga_host: RemoteHosts, *, config_file: str = '/etc/icinga/icinga.cfg') -> None:
        """Initialize the instance.

        Todo:
            Add an IcingaHosts class that performs actions for a given set of hosts instead of passing them to
            all methods.

        Arguments:
            icinga_host (spicerack.remote.RemoteHosts): the RemoteHosts instance for the Icinga server.
            config_file (str, optional): the path to the Icinga main configuration file.

        """
        self._icinga_host = icinga_host
        self._config_file = config_file
        self._command_file: Optional[str] = None

    @property
    def command_file(self) -> Optional[str]:
        """Getter for the command_file property.

        Returns:
            str: the path of the Icinga command file.

        Raises:
            spicerack.icinga.IcingaError: if unable to get the command file path.

        """
        if self._command_file:
            return self._command_file

        try:
            # Get the command_file value in the Icinga configuration.
            command = r"""awk '/^\s*command_file=/{split($0, a, "="); print a[2] }' """ + self._config_file
            for _, output in self._icinga_host.run_sync(command, is_safe=True):
                command_file = output.message().decode().strip()

            if not command_file:
                raise ValueError('Empty or no value found for command_file configuration')

        except (SpicerackError, ValueError) as e:
            raise IcingaError('Unable to read command_file configuration') from e

        self._command_file = command_file
        return self._command_file

    @contextmanager
    def hosts_downtimed(
        self,
        hosts: TypeHosts,
        reason: Reason,
        *,
        duration: timedelta = timedelta(hours=4),
        remove_on_error: bool = False
    ) -> Iterator[None]:
        """Context manager to perform actions while the hosts are downtimed on Icinga.

        Arguments:
            hosts (spicerack.typing.TypeHosts): the set of hostnames or FQDNs to downtime.
            reason (spicerack.administrative.Reason): the reason to set for the downtime on the Icinga server.
            duration (datetime.timedelta, optional): the length of the downtime period.
            remove_on_error: should the downtime be removed even if an exception was raised.

        Yields:
            None: it just yields control to the caller once Icinga has been downtimed and deletes the downtime once
            getting back the control.

        """
        self.downtime_hosts(hosts, reason, duration=duration)
        try:
            yield
        except BaseException:
            if remove_on_error:
                self.remove_downtime(hosts)
            raise
        else:
            self.remove_downtime(hosts)

    def downtime_hosts(
        self,
        hosts: TypeHosts,
        reason: Reason,
        *,
        duration: timedelta = timedelta(hours=4)
    ) -> None:
        """Downtime hosts on the Icinga server for the given time with a message.

        Arguments:
            hosts (spicerack.typing.TypeHosts): the set of hostnames or FQDNs to downtime.
            reason (spicerack.administrative.Reason): the reason to set for the downtime on the Icinga server.
            duration (datetime.timedelta, optional): the length of the downtime period.

        """
        duration_seconds = int(duration.total_seconds())
        if duration_seconds < MIN_DOWNTIME_SECONDS:
            raise IcingaError('Downtime duration must be at least 1 minute, got: {duration}'.format(duration=duration))

        if not hosts:
            raise IcingaError('Got empty hosts list to downtime')

        hostnames = Icinga._get_hostnames(hosts)
        commands = [DOWNTIME_COMMAND.format(hostname=name, duration=duration_seconds, reason=reason.quoted())
                    for name in hostnames]

        logger.info('Scheduling downtime on Icinga server %s for hosts: %s', self._icinga_host, hosts)
        self._icinga_host.run_sync(*commands)

    def recheck_all_services(self, hosts: TypeHosts) -> None:
        """Force recheck of all services associated with a set of hosts.

        Arguments:
            hosts (spicerack.typing.TypeHosts): the set of hostnames or FQDNs to recheck.

        """
        self.host_command('SCHEDULE_FORCED_HOST_SVC_CHECKS', hosts, str(int(time.time())))

    def remove_downtime(self, hosts: TypeHosts) -> None:
        """Remove a downtime from a set of hosts.

        Arguments:
            hosts (spicerack.typing.TypeHosts): the set of hostnames or FQDNs to remove the downtime from.

        """
        self.host_command('DEL_DOWNTIME_BY_HOST_NAME', hosts)

    def host_command(self, command: str, hosts: TypeHosts, *args: str) -> None:
        """Execute a host-specific Icinga command on the Icinga server for a set of hosts.

        Arguments:
            command (str): the Icinga command to execute.
            hosts (spicerack.typing.TypeHosts): the set of hostnames or FQDNs to iterate the command to.
            *args (str): optional positional arguments to pass to the command.

        See Also:
            https://icinga.com/docs/icinga1/latest/en/extcommands2.html

        """
        hostnames = Icinga._get_hostnames(hosts)
        commands = [self._get_command_string(command, hostname, *args) for hostname in hostnames]
        self._icinga_host.run_sync(*commands)

    def get_status(self, hosts: TypeHosts) -> HostsStatus:
        """Get the current status of the given hosts from Icinga.

        Arguments:
            hosts (spicerack.typing.TypeHosts): the set of hostnames or FQDNs to iterate the command to.

        Returns:
            spicerack.icinga.HostsStatus: the instance that represents the status for the given hosts.

        Raises:
            IcingaError: if unable to get the status.
            IcingaStatusParseError: when failing to parse the status.
            IcingaStatusNotFoundError: if a host is not found in the Icinga status.

        """
        # icinga-status exits with non-zero exit code on missing and non-optimal hosts.
        command = Command('/usr/local/bin/icinga-status -j "{hosts}"'.format(hosts=hosts), ok_codes=[])
        for _, output in self._icinga_host.run_sync(command, is_safe=True):  # icinga-status is a read-only script
            json_status = output.message().decode()
            break
        else:
            raise IcingaError('Unable to get the status for the given hosts, no output from icinga-status')

        try:
            status = json.loads(json_status)
        except json.JSONDecodeError as e:
            raise IcingaStatusParseError('Unable to parse Icinga status') from e

        hosts_status = HostsStatus()
        for hostname, host_status in status.items():
            if not host_status:
                raise IcingaStatusNotFoundError('Host {host} was not found in Icinga status'.format(host=hostname))

            hosts_status[hostname] = HostStatus(**host_status)

        return hosts_status

    def _get_command_string(self, *args: str) -> str:
        """Get the Icinga command to execute given the current arguments.

        Arguments:
            *args (str): positional arguments to use to compose the Icinga command string.

        Returns:
            str: the command line to execute on the Icinga host.

        """
        return 'echo -n "[{now}] {args}" > {command_file}'.format(
            now=int(time.time()), args=';'.join(args), command_file=self.command_file)

    @staticmethod
    def _get_hostnames(fqdns: TypeHosts) -> List[str]:
        """Convert FQDNs into hostnames.

        Arguments:
            hosts (spicerack.typing.TypeHosts): an iterable with the list of hostnames to iterate the command for.

        Returns:
            list: the list of hostnames.

        """
        return [fqdn.split('.')[0] for fqdn in fqdns]
