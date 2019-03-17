"""Icinga module."""
import logging
import time

from contextlib import contextmanager
from datetime import timedelta
from typing import Iterator, Sequence, Union

from cumin import NodeSet

from spicerack.administrative import Reason
from spicerack.exceptions import SpicerackError
from spicerack.remote import RemoteHosts


DOWNTIME_COMMAND = 'icinga-downtime -h "{hostname}" -d {duration} -r {reason}'
ICINGA_DOMAIN = 'icinga.wikimedia.org'
MIN_DOWNTIME_SECONDS = 60  # Minimum time in seconds the downtime can be set
logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


class IcingaError(SpicerackError):
    """Custom exception class for errors of this module."""


class Icinga:
    """Class to interact with the Icinga server."""

    def __init__(self, icinga_host: RemoteHosts, *, config_file: str = '/etc/icinga/icinga.cfg') -> None:
        """Initialize the instance.

        Arguments:
            icinga_host (spicerack.remote.RemoteHosts): the RemoteHosts instance for the Icinga server.
        """
        self._icinga_host = icinga_host
        self._config_file = config_file
        self._command_file = None

    @property
    def command_file(self) -> str:
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
        return self._command_file  # type: ignore

    @contextmanager
    def hosts_downtimed(
        self,
        hosts: Sequence[Union[str, NodeSet]],
        reason: Reason,
        *,
        duration: timedelta = timedelta(hours=4),
        remove_on_error: bool = False
    ) -> Iterator[None]:
        """Context manager to perform actions while the hosts are downtimed on Icinga.

        Arguments:
            hosts (list, cumin.NodeSet): an iterable with the list of hostnames to downtime.
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
        hosts: Union[Sequence[str], NodeSet],
        reason: Reason,
        *,
        duration: timedelta = timedelta(hours=4)
    ) -> None:
        """Downtime hosts on the Icinga server for the given time with a message.

        Arguments:
            hosts (list, cumin.NodeSet): an iterable with the list of hostnames to downtime.
            reason (spicerack.administrative.Reason): the reason to set for the downtime on the Icinga server.
            duration (datetime.timedelta, optional): the length of the downtime period.
        """
        duration_seconds = int(duration.total_seconds())
        if duration_seconds < MIN_DOWNTIME_SECONDS:
            raise IcingaError('Downtime duration must be at least 1 minute, got: {duration}'.format(duration=duration))

        if not hosts:
            raise IcingaError('Got empty hosts list to downtime')

        hostnames = [host.split('.')[0] for host in hosts]
        commands = [DOWNTIME_COMMAND.format(hostname=name, duration=duration_seconds, reason=reason.quoted())
                    for name in hostnames]

        logger.info('Scheduling downtime on Icinga server %s for hosts: %s', self._icinga_host, hosts)
        self._icinga_host.run_sync(*commands)

    def remove_downtime(self, hosts: Union[Sequence[str], NodeSet]) -> None:
        """Remove a downtime from a set of hosts.

        Arguments:
            hosts (list, cumin.NodeSet): an iterable with the list of hostnames to iterate the command for.
        """
        self.host_command('DEL_DOWNTIME_BY_HOST_NAME', hosts)

    def host_command(self, command: str, hosts: Union[Sequence[str], NodeSet], *args: str) -> None:
        """Execute a host-specific Icinga command on the Icinga server for a set of hosts.

        Arguments:
            command (str): the Icinga command to execute.
            hosts (list, cumin.NodeSet): an iterable with the list of hostnames to iterate the command for.
            *args (str): optional positional arguments to pass to the command.

        See Also:
            https://icinga.com/docs/icinga1/latest/en/extcommands2.html

        """
        commands = [self._get_command_string(command, host.split('.')[0], *args) for host in hosts]
        self._icinga_host.run_sync(*commands)

    def _get_command_string(self, *args: str) -> str:
        """Get the Icinga command to execute given the current arguments.

        Arguments:
            *args (str): positional arguments to use to compose the Icinga command string.

        Returns:
            str: the command line to execute on the Icinga host.

        """
        return 'echo -n "[{now}] {args}" > {command_file}'.format(
            now=int(time.time()), args=';'.join(args), command_file=self.command_file)
