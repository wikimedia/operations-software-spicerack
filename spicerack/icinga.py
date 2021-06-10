"""Icinga module."""
import json
import logging
import time
import warnings
from contextlib import contextmanager
from datetime import timedelta
from typing import Dict, Iterator, List, Mapping, Sequence, Tuple, cast

from cumin import NodeSet
from cumin.transports import Command

from spicerack.administrative import Reason
from spicerack.decorators import retry
from spicerack.exceptions import SpicerackError
from spicerack.remote import RemoteHosts
from spicerack.typing import TypeHosts

DOWNTIME_COMMAND: str = 'icinga-downtime -h "{hostname}" -d {duration} -r {reason}'
ICINGA_DOMAIN: str = "icinga.wikimedia.org"
MIN_DOWNTIME_SECONDS: int = 60  # Minimum time in seconds the downtime can be set
logger = logging.getLogger(__name__)


class CommandFile(str):
    """String class to represent an Icinga command file path with cache capabilities."""

    _command_files: Dict[Tuple[str, str], str] = {}  # Cache a command file per Icinga hostname and configuration file

    def __new__(cls, icinga_host: RemoteHosts, *, config_file: str = "/etc/icinga/icinga.cfg") -> "CommandFile":
        """Get the Icinga host command file where to write the commands and cache it.

        Arguments:
            icinga_host (spicerack.remote.RemoteHosts): the Icinga host instance.
            config_file (str, optional): the Icinga configuration file to check for the command file directive.

        Returns:
            str: the Icinga command file path on the Icinga host.

        Raises:
            spicerack.icinga.IcingaError: if unable to get the command file path.

        """
        # Can't use functools cache decorators because NodeSet are not hashable
        if len(icinga_host) != 1:
            raise IcingaError("Icinga host must match a single host, got: {host}".format(host=icinga_host))

        identifier = (str(icinga_host), config_file)

        if identifier in cls._command_files:
            return cast(CommandFile, cls._command_files[identifier])

        try:
            # Get the command_file value in the Icinga configuration.
            command = r"grep -P '\s*command_file\s*=.+' " + config_file
            command_file = ""
            for _, output in icinga_host.run_sync(command, is_safe=True):  # Read only operation
                command_file = output.message().decode().split("=", 1)[-1].strip()

            if not command_file:
                raise ValueError(
                    "Empty or no value found for command_file configuration in {config}".format(config=config_file)
                )

        except (SpicerackError, ValueError) as e:
            raise IcingaError("Unable to read command_file configuration in {config}".format(config=config_file)) from e

        cls._command_files[identifier] = command_file
        return cast(CommandFile, command_file)


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

    STATE_UP = "UP"
    """:py:class:`str`: the Icinga value for a host that is up and running. The other values for the Icinga host state
    are ``DOWN`` and ``UNREACHABLE``."""

    def __init__(
        self,
        *,
        name: str,
        state: str,
        optimal: bool,
        failed_services: Sequence[Mapping],
        downtimed: bool,
        notifications_enabled: bool,
    ):
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
        return [service["name"] for service in self.failed_services_raw]


class Icinga:
    """Class to interact with the Icinga server."""

    def __init__(self, icinga_host: RemoteHosts) -> None:
        """Initialize the instance.

        .. deprecated:: v0.0.50
            use :py:class:`spicerack.icinga.IcingaHosts` instead.

        Arguments:
            icinga_host (spicerack.remote.RemoteHosts): the RemoteHosts instance for the Icinga server.

        """
        self._icinga_host = icinga_host
        warnings.warn("Deprecated class, use spicearack.icinga_hosts() instead", DeprecationWarning)

    @property
    def command_file(self) -> str:
        """Getter for the command_file property.

        Returns:
            str: the path of the Icinga command file.

        Raises:
            spicerack.icinga.IcingaError: if unable to get the command file path.

        """
        return CommandFile(self._icinga_host)

    @contextmanager
    def hosts_downtimed(
        self,
        hosts: TypeHosts,
        reason: Reason,
        *,
        duration: timedelta = timedelta(hours=4),
        remove_on_error: bool = False,
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

    def downtime_hosts(self, hosts: TypeHosts, reason: Reason, *, duration: timedelta = timedelta(hours=4)) -> None:
        """Downtime hosts on the Icinga server for the given time with a message.

        Arguments:
            hosts (spicerack.typing.TypeHosts): the set of hostnames or FQDNs to downtime.
            reason (spicerack.administrative.Reason): the reason to set for the downtime on the Icinga server.
            duration (datetime.timedelta, optional): the length of the downtime period.

        """
        duration_seconds = int(duration.total_seconds())
        if duration_seconds < MIN_DOWNTIME_SECONDS:
            raise IcingaError("Downtime duration must be at least 1 minute, got: {duration}".format(duration=duration))

        if not hosts:
            raise IcingaError("Got empty hosts list to downtime")

        hostnames = Icinga._get_hostnames(hosts)
        commands = [
            DOWNTIME_COMMAND.format(hostname=name, duration=duration_seconds, reason=reason.quoted())
            for name in hostnames
        ]

        logger.info(
            "Scheduling downtime on Icinga server %s for hosts: %s",
            self._icinga_host,
            hosts,
        )
        self._icinga_host.run_sync(*commands)

    def recheck_all_services(self, hosts: TypeHosts) -> None:
        """Force recheck of all services associated with a set of hosts.

        Arguments:
            hosts (spicerack.typing.TypeHosts): the set of hostnames or FQDNs to recheck.

        """
        self.host_command("SCHEDULE_FORCED_HOST_SVC_CHECKS", hosts, str(int(time.time())))

    def remove_downtime(self, hosts: TypeHosts) -> None:
        """Remove a downtime from a set of hosts.

        Arguments:
            hosts (spicerack.typing.TypeHosts): the set of hostnames or FQDNs to remove the downtime from.

        """
        self.host_command("DEL_DOWNTIME_BY_HOST_NAME", hosts)

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

    def get_status(self, hosts: NodeSet) -> HostsStatus:
        """Get the current status of the given hosts from Icinga.

        Arguments:
            hosts (cumin.NodeSet): the set of hostnames or FQDNs to iterate the command to.

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
            raise IcingaError("Unable to get the status for the given hosts, no output from icinga-status")

        try:
            status = json.loads(json_status)
        except json.JSONDecodeError as e:
            raise IcingaStatusParseError("Unable to parse Icinga status") from e

        hosts_status = HostsStatus()
        for hostname, host_status in status.items():
            if not host_status:
                raise IcingaStatusNotFoundError("Host {host} was not found in Icinga status".format(host=hostname))

            hosts_status[hostname] = HostStatus(**host_status)

        return hosts_status

    @retry(
        tries=15,
        delay=timedelta(seconds=3),
        backoff_mode="linear",
        exceptions=(IcingaError,),
    )
    def wait_for_optimal(self, hosts: NodeSet) -> None:
        """Waits for an icinga optimal status, else raises an exception.

        Arguments:
            hosts (cumin.NodeSet): the set of hostnames or FQDNs to iterate the command to.

        Raises:
            IcingaError

        """
        status = self.get_status(hosts)
        if not status.optimal:
            failed = ["{}:{}".format(k, ",".join(v)) for k, v in status.failed_services.items()]
            raise IcingaError("Not all services are recovered: {}".format(" ".join(failed)))

    def _get_command_string(self, *args: str) -> str:
        """Get the Icinga command to execute given the current arguments.

        Arguments:
            *args (str): positional arguments to use to compose the Icinga command string.

        Returns:
            str: the command line to execute on the Icinga host.

        """
        return "bash -c 'echo -n \"[{now}] {args}\" > {command_file} '".format(
            now=int(time.time()), args=";".join(args), command_file=self.command_file
        )

    @staticmethod
    def _get_hostnames(fqdns: TypeHosts) -> List[str]:
        """Convert FQDNs into hostnames.

        Arguments:
            hosts (spicerack.typing.TypeHosts): an iterable with the list of hostnames to iterate the command for.

        Returns:
            list: the list of hostnames.

        """
        return [fqdn.split(".")[0] for fqdn in fqdns]


class IcingaHosts:
    """Class to manage the Icinga checks of a given set of hosts."""

    def __init__(self, icinga_host: RemoteHosts, target_hosts: TypeHosts, *, verbatim_hosts: bool = False) -> None:
        """Initialize the instance.

        Arguments:
            icinga_host (spicerack.remote.RemoteHosts): the RemoteHosts instance for the Icinga server.
            target_hosts (spicerack.typing.TypeHosts): the target hosts either as a NodeSet instance or a sequence of
                strings.
            verbatim_hosts (bool, optional): if :py:data:`True` use the hosts passed verbatim as is, if instead
                :py:data:`False`, the default, consider the given target hosts as FQDNs and extract their hostnames to
                be used in Icinga.

        """
        if not verbatim_hosts:
            target_hosts = [target_host.split(".")[0] for target_host in target_hosts]

        if isinstance(target_hosts, NodeSet):
            self._target_hosts = target_hosts
        else:
            self._target_hosts = NodeSet.fromlist(target_hosts)

        if not self._target_hosts:
            raise IcingaError("Got empty target hosts list.")

        self._command_file = CommandFile(icinga_host)  # This validates also that icinga_host matches a single server.
        self._icinga_host = icinga_host
        self._verbatim_hosts = verbatim_hosts

    @contextmanager
    def hosts_downtimed(
        self, reason: Reason, *, duration: timedelta = timedelta(hours=4), remove_on_error: bool = False
    ) -> Iterator[None]:
        """Context manager to perform actions while the hosts are downtimed on Icinga.

        Arguments:
            reason (spicerack.administrative.Reason): the reason to set for the downtime on the Icinga server.
            duration (datetime.timedelta, optional): the length of the downtime period.
            remove_on_error: should the downtime be removed even if an exception was raised.

        Yields:
            None: it just yields control to the caller once Icinga has been downtimed and deletes the downtime once
            getting back the control.

        """
        self.downtime_hosts(reason, duration=duration)
        try:
            yield
        except BaseException:
            if remove_on_error:
                self.remove_downtime()
            raise
        else:
            self.remove_downtime()

    def downtime_hosts(self, reason: Reason, *, duration: timedelta = timedelta(hours=4)) -> None:
        """Downtime hosts on the Icinga server for the given time with a message.

        Arguments:
            reason (spicerack.administrative.Reason): the reason to set for the downtime on the Icinga server.
            duration (datetime.timedelta, optional): the length of the downtime period.

        """
        duration_seconds = int(duration.total_seconds())
        if duration_seconds < MIN_DOWNTIME_SECONDS:
            raise IcingaError("Downtime duration must be at least 1 minute, got: {duration}".format(duration=duration))

        commands = [
            DOWNTIME_COMMAND.format(hostname=name, duration=duration_seconds, reason=reason.quoted())
            for name in self._target_hosts
        ]

        logger.info(
            "Scheduling downtime on Icinga server %s for hosts: %s",
            self._icinga_host,
            self._target_hosts,
        )
        self._icinga_host.run_sync(*commands)

    def recheck_all_services(self) -> None:
        """Force recheck of all services associated with a set of hosts."""
        self.host_command("SCHEDULE_FORCED_HOST_SVC_CHECKS", str(int(time.time())))

    def remove_downtime(self) -> None:
        """Remove a downtime from a set of hosts."""
        self.host_command("DEL_DOWNTIME_BY_HOST_NAME")

    def host_command(self, command: str, *args: str) -> None:
        """Execute a host-specific Icinga command on the Icinga server for a set of hosts.

        Arguments:
            command (str): the Icinga command to execute.
            *args (str): optional positional arguments to pass to the command.

        See Also:
            https://icinga.com/docs/icinga1/latest/en/extcommands2.html

        """
        commands = [self._get_command_string(command, target_host, *args) for target_host in self._target_hosts]
        self._icinga_host.run_sync(*commands)

    def get_status(self) -> HostsStatus:
        """Get the current status of the given hosts from Icinga.

        Returns:
            spicerack.icinga.HostsStatus: the instance that represents the status for the given hosts.

        Raises:
            IcingaError: if unable to get the status.
            IcingaStatusParseError: when failing to parse the status.
            IcingaStatusNotFoundError: if a host is not found in the Icinga status.

        """
        # icinga-status exits with non-zero exit code on missing and non-optimal hosts.
        verbatim = " --verbatim-hosts" if self._verbatim_hosts else ""
        command = Command(
            '/usr/local/bin/icinga-status -j{verbatim} "{hosts}"'.format(verbatim=verbatim, hosts=self._target_hosts),
            ok_codes=[],
        )
        for _, output in self._icinga_host.run_sync(command, is_safe=True):  # icinga-status is a read-only script
            json_status = output.message().decode()
            break
        else:
            raise IcingaError("Unable to get the status for the given hosts, no output from icinga-status")

        try:
            status = json.loads(json_status)
        except json.JSONDecodeError as e:
            raise IcingaStatusParseError("Unable to parse Icinga status") from e

        hosts_status = HostsStatus()
        for hostname, host_status in status.items():
            if not host_status:
                raise IcingaStatusNotFoundError("Host {host} was not found in Icinga status".format(host=hostname))

            hosts_status[hostname] = HostStatus(**host_status)

        return hosts_status

    @retry(
        tries=15,
        delay=timedelta(seconds=3),
        backoff_mode="linear",
        exceptions=(IcingaError,),
    )
    def wait_for_optimal(self) -> None:
        """Waits for an icinga optimal status, else raises an exception.

        Raises:
            IcingaError: if the status is not optimal.

        """
        status = self.get_status()
        if not status.optimal:
            failed = ["{}:{}".format(k, ",".join(v)) for k, v in status.failed_services.items()]
            raise IcingaError("Not all services are recovered: {}".format(" ".join(failed)))

    def _get_command_string(self, *args: str) -> str:
        """Get the Icinga command to execute given the current arguments.

        Arguments:
            *args (str): positional arguments to use to compose the Icinga command string.

        Returns:
            str: the command line to execute on the Icinga host.

        """
        return "bash -c 'echo -n \"[{now}] {args}\" > {command_file} '".format(
            now=int(time.time()), args=";".join(args), command_file=self._command_file
        )
