"""Icinga module."""
import json
import logging
import re
import shlex
import time
from contextlib import contextmanager
from datetime import timedelta
from typing import Dict, Iterator, List, Mapping, Optional, Sequence, Tuple, cast

from cumin import NodeSet
from cumin.transports import Command

from spicerack.administrative import Reason
from spicerack.decorators import retry
from spicerack.exceptions import SpicerackCheckError, SpicerackError
from spicerack.remote import RemoteHosts
from spicerack.typing import TypeHosts

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
            raise IcingaError(f"Icinga host must match a single host, got: {icinga_host}")

        identifier = (str(icinga_host), config_file)

        if identifier in cls._command_files:
            return cast(CommandFile, cls._command_files[identifier])

        try:
            # Get the command_file value in the Icinga configuration.
            command = r"grep -P '\s*command_file\s*=.+' " + config_file
            command_file = ""
            for _, output in icinga_host.run_sync(
                command, is_safe=True, print_output=False, print_progress_bars=False
            ):  # Read only operation
                command_file = output.message().decode().split("=", 1)[-1].strip()

            if not command_file:
                raise ValueError(f"Empty or no value found for command_file configuration in {config_file}")

        except (SpicerackError, ValueError) as e:
            raise IcingaError(f"Unable to read command_file configuration in {config_file}") from e

        cls._command_files[identifier] = command_file
        return cast(CommandFile, command_file)


class IcingaError(SpicerackError):
    """Custom exception class for errors of this module."""


class IcingaCheckError(SpicerackCheckError):
    """Custom exception class for check errors of this module."""


class IcingaStatusParseError(IcingaError):
    """Custom exception class for errors while parsing the Icinga status."""


class IcingaStatusNotFoundError(IcingaError):
    """Custom exception class for a host missing from the Icinga status."""

    def __init__(self, hostnames: Sequence[str]):
        """Initializes an IcingaStatusNotFoundError instance.

        Arguments:
            hostnames (sequence): The hostnames not found in the Icinga status.

        """
        if len(hostnames) == 1:
            super().__init__(f"Host {hostnames[0]} was not found in Icinga status")
        else:
            hosts = ", ".join(hostnames)
            super().__init__(f"Hosts {hosts} were not found in Icinga status")


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
        downtimed: bool,
        notifications_enabled: bool,
        failed_services: Optional[Sequence[Mapping]] = None,
        services: Optional[Sequence[Mapping]] = None,
    ):
        """Initialize the instance.

        Either `services` or `failed_services` may be present, depending on the flags passed to icinga-status.

        Arguments:
            name (str): the hostname.
            state (str): the Icinga state for the host, one of ``UP``, ``DOWN``, UNREACHABLE``.
            optimal (bool): whether the host is in optimal state (all green).
            downtimed (bool): whether the host is currently downtimed.
            notifications_enabled: (bool): whether the host has notifications enabled.
            failed_services (list, optional): a list of dictionaries representing the failed services.
            services (list, optional): a list of dictionaries giving detailed service status.

        """
        self.name = name
        self.state = state
        self.optimal = optimal
        self.downtimed = downtimed
        self.notifications_enabled = notifications_enabled
        # TODO: could be improved creating a ServiceStatus class
        self.services = services if services is not None else []
        self.failed_services_raw = failed_services if failed_services is not None else []

    @property
    def failed_services(self) -> List[str]:
        """Return the list of service names that are failing.

        Returns:
            list: a list of strings with the check names.

        """
        return [service["name"] for service in self.failed_services_raw]


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
    def downtimed(
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
        self.downtime(reason, duration=duration)
        try:
            yield
        except BaseException:
            if remove_on_error:
                self.remove_downtime()
            raise
        else:
            self.remove_downtime()

    def downtime(self, reason: Reason, *, duration: timedelta = timedelta(hours=4)) -> None:
        """Downtime hosts on the Icinga server for the given time with a message.

        Arguments:
            reason (spicerack.administrative.Reason): the reason to set for the downtime on the Icinga server.
            duration (datetime.timedelta, optional): the length of the downtime period.

        """
        duration_seconds = int(duration.total_seconds())
        if duration_seconds < MIN_DOWNTIME_SECONDS:
            raise IcingaError(f"Downtime duration must be at least 1 minute, got: {duration}")

        try:
            self.get_status()  # Ensure all hosts are known to Icinga, ignoring the return value.
        except IcingaStatusNotFoundError as e:
            raise IcingaError(f"{e} - no hosts have been downtimed.") from e

        logger.info(
            "Scheduling downtime on Icinga server %s for hosts: %s",
            self._icinga_host,
            self._target_hosts,
        )
        start_time = str(int(time.time()))
        end_time = str(int(time.time() + duration_seconds))
        # TODO: SCHEDULE_HOST_DOWNTIME may not be needed, since a quick look at the Icinga source code suggests that
        #  SCHEDULE_HOST_SVC_DOWNTIME also downtimes the host itself, not just the services. But if it does so, that's
        #  an undocumented extra feature. For now we're keeping this call for consistency with the older icinga-downtime
        #  script, even though it may be redundant, and in the future we can evaluate whether it's unnecessary.
        self.run_icinga_command(
            "SCHEDULE_HOST_DOWNTIME",
            start_time,
            end_time,
            "1",  # Start at the start_time and end at the end_time.
            "0",  # Not triggered by another downtime.
            str(duration_seconds),
            reason.owner,
            reason.reason,
        )
        self.run_icinga_command(
            "SCHEDULE_HOST_SVC_DOWNTIME",
            start_time,
            end_time,
            "1",  # Start at the start_time and end at the end_time.
            "0",  # Not triggered by another downtime.
            str(duration_seconds),
            reason.owner,
            reason.reason,
        )
        try:  # Best effort attempt to ensure the downtime was applied. See T309447.
            self.wait_for_downtimed()
        except IcingaCheckError as e:
            logger.warning(e)

    @retry(
        tries=12,
        delay=timedelta(seconds=10),
        backoff_mode="constant",
        exceptions=(IcingaCheckError,),
        failure_message="Unable to verify all hosts got downtimed",
    )
    def wait_for_downtimed(self) -> None:
        """Poll the Icinga status to verify that the hosts got effectively downtimed.

        Raises:
            spicerack.icinga.IcingaError: if unable to verify that all hosts got downtimed.

        """
        not_downtimed = [hostname for hostname, host_status in self.get_status().items() if not host_status.downtimed]
        if not_downtimed:
            raise IcingaCheckError(f"Some hosts are not yet downtimed: {not_downtimed}")

    @contextmanager
    def services_downtimed(
        self,
        service_re: str,
        reason: Reason,
        *,
        duration: timedelta = timedelta(hours=4),
        remove_on_error: bool = False,
    ) -> Iterator[None]:
        """Context manager to perform actions while services are downtimed on Icinga.

        Arguments:
            service_re (str): the regular expression matching service names to downtime.
            reason (spicerack.administrative.Reason): the reason to set for the downtime on the Icinga server.
            duration (datetime.timedelta, optional): the length of the downtime period.
            remove_on_error (bool, optional): should the downtime be removed even if an exception was raised.

        Yields:
            None: it just yields control to the caller once Icinga has been downtimed and deletes the downtime once
            getting back the control.

        """
        self.downtime_services(service_re, reason, duration=duration)
        try:
            yield
        except BaseException:
            if remove_on_error:
                self.remove_service_downtimes(service_re)
            raise
        else:
            self.remove_service_downtimes(service_re)

    def downtime_services(self, service_re: str, reason: Reason, *, duration: timedelta = timedelta(hours=4)) -> None:
        """Downtime services on the Icinga server for the given time with a message.

        If there are multiple target_hosts, the set of matching services may vary from host to host (e.g. because a
        hostname, DB section, or other unique fact is included in the service name) and downtime_services will downtime
        each service on the correct target_host. If some hosts happen to have no matching services, they will be safely
        skipped. But if *no* hosts have matching services, IcingaError is raised (because the regex is probably wrong).

        Arguments:
            service_re (str): the regular expression matching service names to downtime.
            reason (spicerack.administrative.Reason): the reason to set for the downtime on the Icinga server.
            duration (datetime.timedelta, optional): the length of the downtime period.

        Raises:
            re.error: if service_re is an invalid regular expression.
            IcingaError: if no services on any target host match the regular expression.

        """
        duration_seconds = int(duration.total_seconds())
        if duration_seconds < MIN_DOWNTIME_SECONDS:
            raise IcingaError(f"Downtime duration must be at least 1 minute, got: {duration}")

        try:
            # This also validates the regular expression syntax and ensures all hosts are known to Icinga.
            status = self.get_status(service_re)
        except IcingaStatusNotFoundError as e:
            raise IcingaError(f"{e} - no hosts have been downtimed.") from e

        unique_services = set()
        for host_status in status.values():
            for service in host_status.services:
                unique_services.add(service["name"])
        unique_service_count = len(unique_services)
        matched_host_count = sum(1 if host_status.services else 0 for host_status in status.values())

        if not unique_services:
            raise IcingaError(f'No services on {self._target_hosts} matched "{service_re}"')

        logger.info(
            'Scheduling downtime on Icinga server %s for services "%s" for host%s: %s '
            "(matched %d unique service name%s on %d host%s)",
            self._icinga_host,
            service_re,
            "" if len(self._target_hosts) == 1 else "s",
            self._target_hosts,
            unique_service_count,
            "" if unique_service_count == 1 else "s",
            matched_host_count,
            "" if matched_host_count == 1 else "s",
        )
        start_time = str(int(time.time()))
        end_time = str(int(time.time() + duration_seconds))
        # This doesn't use self.run_icinga_command because if the service names are different, we'll set different
        # downtimes (and therefore run different Icinga commands) for each target_host.
        commands = []
        for hostname, host_status in status.items():
            for service in host_status.services:
                logger.debug('Downtiming "%s" on %s', service["name"], hostname)
                commands.append(
                    self._get_command_string(
                        "SCHEDULE_SVC_DOWNTIME",
                        hostname,
                        service["name"],
                        start_time,
                        end_time,
                        "1",  # Start at the start_time and end at the end_time.
                        "0",  # Not triggered by another downtime.
                        str(duration_seconds),
                        reason.owner,
                        reason.reason,
                    )
                )
        self._icinga_host.run_sync(*commands, print_output=False, print_progress_bars=False)

    def recheck_all_services(self) -> None:
        """Force recheck of all services associated with a set of hosts."""
        self.run_icinga_command("SCHEDULE_FORCED_HOST_SVC_CHECKS", str(int(time.time())))

    def recheck_failed_services(self) -> None:
        """Force recheck of all failed associated with a set of hosts."""
        status = self.get_status()
        if status.optimal:
            return
        commands = [
            self._get_command_string("SCHEDULE_FORCED_SVC_CHECK", hostname, service_name, str(int(time.time())))
            for hostname, failed in status.failed_services.items()
            for service_name in failed
        ]
        self._icinga_host.run_sync(*commands, print_output=False, print_progress_bars=False)

    def remove_downtime(self) -> None:
        """Remove a downtime from a set of hosts."""
        self.run_icinga_command("DEL_DOWNTIME_BY_HOST_NAME")

    def remove_service_downtimes(self, service_re: str) -> None:
        """Remove downtimes for services from a set of hosts.

        If there are multiple target_hosts, this method has the same behavior as downtime_services. If any matching
        service is not downtimed, it's silently skipped. (If one or more services exist matching the regex, but none of
        them is downtimed, this method does nothing.)

        Arguments:
            service_re (str): the regular expression matching service names to un-downtime.

        Raises:
            re.error: if service_re is an invalid regular expression.
            IcingaError: if no services on any target host match the regular expression.

        """
        status = self.get_status(service_re)  # This also validates the regular expression syntax.
        if not any(host_status.services for host_status in status.values()):
            raise IcingaError(f'No services on {self._target_hosts} matched "{service_re}"')

        logger.info(
            'Removing downtime on Icinga server %s for services "%s" for hosts: %s',
            self._icinga_host,
            service_re,
            self._target_hosts,
        )

        commands = []
        for hostname, host_status in status.items():
            for service in host_status.services:
                if not service["status"]["scheduled_downtime_depth"]:  # Skip if not downtimed.
                    continue
                logger.debug('Removing downtime for "%s" on %s', service["name"], hostname)
                # DEL_DOWNTIME_BY_HOST_NAME is misleadingly named -- it also accepts an optional service name argument.
                commands.append(self._get_command_string("DEL_DOWNTIME_BY_HOST_NAME", hostname, service["name"]))
        if commands:
            self._icinga_host.run_sync(*commands, print_output=False, print_progress_bars=False)
        else:
            logger.info("No services downtimed, nothing to do.")

    def run_icinga_command(self, command: str, *args: str) -> None:
        """Execute an Icinga command on the Icinga server for all the current hosts.

        This lower level API is meant to be used when the higher level API exposed in this class does not cover a
        given use case. The arguments passed to the underlying Icinga command will be the hostname plus all the
        arguments passed to this method. Hence it can be used only with Icinga commands that require a hostname.
        See the link below for more details on the available Icinga commands and their arguments.

        Arguments:
            command (str): the Icinga command to execute.
            *args (str): optional positional arguments to pass to the command.

        See Also:
            https://icinga.com/docs/icinga1/latest/en/extcommands2.html

        """
        commands = [self._get_command_string(command, target_host, *args) for target_host in self._target_hosts]
        self._icinga_host.run_sync(*commands, print_output=False, print_progress_bars=False)

    def get_status(self, service_re: str = "") -> HostsStatus:
        """Get the current status of the given hosts from Icinga.

        Arguments:
            service_re (str): if non-empty, the regular expression matching service names

        Returns:
            spicerack.icinga.HostsStatus: the instance that represents the status for the given hosts.

        Raises:
            IcingaError: if unable to get the status.
            IcingaStatusParseError: when failing to parse the status.
            IcingaStatusNotFoundError: if a host is not found in the Icinga status.
            re.error: if service_re is an invalid regular expression.

        """
        if service_re:
            # Compile the regex and ignore the result, in order to raise re.error if it's malformed.
            re.compile(service_re)

        # icinga-status exits with non-zero exit code on missing and non-optimal hosts.
        verbatim = " --verbatim-hosts" if self._verbatim_hosts else ""
        services = (" --services " + shlex.quote(service_re)) if service_re else ""
        command = Command(
            f'/usr/local/bin/icinga-status -j{verbatim}{services} "{self._target_hosts}"',
            ok_codes=[],
        )
        for _, output in self._icinga_host.run_sync(
            command, is_safe=True, print_output=False, print_progress_bars=False
        ):  # icinga-status is a read-only script
            json_status = output.message().decode()
            break
        else:
            raise IcingaError("Unable to get the status for the given hosts, no output from icinga-status")

        try:
            status = json.loads(json_status)
        except json.JSONDecodeError as e:
            raise IcingaStatusParseError("Unable to parse Icinga status") from e

        missing_hosts = [hostname for hostname, host_status in status.items() if host_status is None]
        if missing_hosts:
            raise IcingaStatusNotFoundError(missing_hosts)

        return HostsStatus({hostname: HostStatus(**host_status) for hostname, host_status in status.items()})

    def wait_for_optimal(self) -> None:
        """Waits for an icinga optimal status, else raises an exception.

        This function will first instruct icinga to recheck all failed services
        and then wait until all services are in an optimal status.  If an
        optimal status is not reached in 6 minutes then we raise IcingaError

        Raises:
            IcingaError: if the status is not optimal.

        """

        @retry(
            tries=15,
            delay=timedelta(seconds=3),
            backoff_mode="linear",
            exceptions=(IcingaError,),
        )
        def check() -> None:
            status = self.get_status()
            if not status.optimal:
                failed = [f"{k}:{','.join(v)}" for k, v in status.failed_services.items()]
                raise IcingaError("Not all services are recovered: " + " ".join(failed))

        self.recheck_failed_services()
        check()

    def _get_command_string(self, *args: str) -> str:
        """Get the Icinga command to execute given the current arguments.

        Arguments:
            *args (str): positional arguments to use to compose the Icinga command string.

        Returns:
            str: the command line to execute on the Icinga host.

        """
        args_str = ";".join(args)
        bash_cmd = f'echo -n "[{int(time.time())}] {args_str}" > {self._command_file} '
        return "bash -c " + shlex.quote(bash_cmd)
