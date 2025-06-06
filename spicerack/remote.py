"""Remote module to execute commands on hosts via Cumin."""

import logging
import math
import time
from collections.abc import Callable, Iterator, Sequence
from datetime import datetime, timedelta
from typing import Any, Optional, Union

from ClusterShell.MsgTree import MsgTreeElem
from cumin import Config, CuminError, NodeSet, query, transport, transports
from cumin.cli import target_batch_size
from cumin.transports import Command
from cumin.transports.clustershell import NullReporter, TqdmReporter

from spicerack.confctl import ConftoolEntity
from spicerack.decorators import retry
from spicerack.exceptions import SpicerackCheckError, SpicerackError

logger = logging.getLogger(__name__)


class RemoteError(SpicerackError):
    """Custom exception class for errors of this module."""


class RemoteCheckError(SpicerackCheckError):
    """Custom exception class for check errors of this module."""


class RemoteExecutionError(RemoteError):
    """Custom exception class for remote execution errors."""

    def __init__(self, retcode: int, message: str, results: Iterator[tuple[NodeSet, MsgTreeElem]]) -> None:
        """Override parent constructor to add the return code attribute.

        Arguments:
            retcode: the return code of the remote execution.
            message: the exception message.
            results: the cumin results.

        """
        super().__init__(f"{message} (exit_code={retcode})")
        self.retcode = retcode
        self.results = results


class RemoteClusterExecutionError(RemoteError):
    """Custom exception class for collecting multiple execution errors on a cluster."""

    def __init__(
        self,
        results: list[tuple[NodeSet, MsgTreeElem]],
        failures: list[RemoteExecutionError],
    ):
        """Override the parent constructor to add failures and results as attributes.

        Arguments:
            results: the remote results.
            failures: the list of exceptions raised in the cluster execution.

        """
        super().__init__(f"{len(failures)} hosts have failed execution")
        self.failures = failures
        self.results = results


class RemoteHostsAdapter:
    """Base adapter to write classes that expand the capabilities of RemoteHosts.

    This adapter class is a helper class to reduce duplication when writing classes that needs to add capabilities to a
    RemoteHosts instance. The goal is to not extend the RemoteHosts but instead delegate to its instances.
    This class fits when a single RemoteHosts instance is enough, but for more complex cases, in which multiple
    RemoteHosts instances should be orchestrated, it's ok to not extend this class and create a standalone one.
    """

    def __init__(self, remote_hosts: "RemoteHosts") -> None:
        """Initialize the instance.

        Arguments:
            remote_hosts: the instance to act on the remote hosts.

        """
        self._remote_hosts = remote_hosts

    def __str__(self) -> str:
        """String representation of the instance.

        Returns:
            the string representation of the ``remote_hosts`` of the instance in ``NodeSet`` notation.

        """
        return str(self._remote_hosts)

    def __len__(self) -> int:
        """Get the number of target hosts in this instance."""
        return len(self._remote_hosts)

    @property
    def remote_hosts(self) -> "RemoteHosts":
        """Getter for the remote_hosts property.

        Returns:
            The instance to run commands on the underlying remote hosts.

        """
        return self._remote_hosts


class LBRemoteCluster(RemoteHostsAdapter):
    """Class usable to operate on a cluster of servers with pooling/depooling logic in conftool."""

    def __init__(self, config: Config, remote_hosts: "RemoteHosts", conftool: ConftoolEntity) -> None:
        """Initialize the instance.

        Arguments:
            config: cumin configuration.
            remote_hosts: the instance to act on the remote hosts.
            conftool: the conftool entity to operate on.

        """
        self._config = config
        self._conftool = conftool
        super().__init__(remote_hosts)

    def run(  # pylint: disable=too-many-arguments
        self,
        *commands: Union[str, Command],
        svc_to_depool: Optional[list[str]] = None,
        batch_size: int = 1,
        batch_sleep: Optional[float] = None,
        is_safe: bool = False,
        max_failed_batches: int = 0,
        print_output: bool = True,
        print_progress_bars: bool = True,
    ) -> list[tuple[NodeSet, MsgTreeElem]]:
        """Run commands while depooling servers in groups of batch_size.

        For clusters behind a load balancer, we typically want to be able to
        depool a server from a specific service, then run any number of commands
        on it, and finally repool it.

        We also want to ensure we can only have at max N hosts depooled at any
        time. Given cumin doesn't have pre- and post- execution hooks, we break
        the remote run in smaller groups and execute on one group at a time,
        in parallel on all the servers.
        Note this works a bit differently than how the cumin moving window works,
        as here we'll have to wait for the execution on all servers in a group
        before moving on to the next.

        Arguments:
            *commands: Arbitrary number of commands to execute.
            svc_to_depool: A list of services (in conftool) to depool.
            batch_size: the batch size for cumin, as an integer. Defaults to 1.
            batch_sleep: the batch sleep in seconds to use before scheduling the next batch of hosts.
            is_safe: whether the command is safe to run also in dry-run mode because it's a read-only
            max_failed_batches: Maximum number of batches that can fail. Defaults to 0.
            print_output: whether to print Cumin's output to stdout.
            print_progress_bars: whether to print Cumin's progress bars to stderr.

        Returns:
            What :py:meth:`cumin.transports.BaseWorker.get_results` returns to allow to iterate over the results.

        Raises:
            spicerack.remote.RemoteExecutionError, spicerack.remote.RemoteClusterExecutionError: if the Cumin execution
                returns a non-zero exit code.

        """
        n_hosts = len(self._remote_hosts)
        # Ensure the batch size is smaller than the whole cluster. When acting on a cluster
        # we should never act on all hosts in parallel.
        # If that's needed, RemoteHosts can be used directly.
        # TODO: the right thing to do would be to check that batch_size is smaller than
        # (1 - depool_threshold) * pooled_hosts, but that would also need to know the current
        # state of the cluster.
        if batch_size <= 0 or batch_size >= n_hosts:
            raise RemoteError(f"Values for batch_size must be 0 < x < {n_hosts}, got {batch_size}")

        # If no service needs depooling, the standard behavior of remote_hosts.run_async is used
        # TODO: add the ability to select all services.
        if svc_to_depool is None:
            return list(
                self._remote_hosts.run_async(
                    *commands,
                    success_threshold=(1.0 - (max_failed_batches * batch_size) / n_hosts),
                    batch_size=batch_size,
                    batch_sleep=batch_sleep,
                    is_safe=is_safe,
                    print_output=print_output,
                    print_progress_bars=print_progress_bars,
                )
            )

        results = []
        # Find how much we must split the pool up to achieve the desired batch size.
        n_slices = math.ceil(n_hosts / batch_size)
        # TODO: add better failure handling. Right now we just support counting batches with a failure, while we might
        # want to support success_threshold.
        failures = []
        for remotes_slice in self._remote_hosts.split(n_slices):
            # Select the pooled servers for the selected services, from the group we're operating on now.
            with self._conftool.change_and_revert(
                "pooled",
                "yes",
                "no",
                service="|".join(svc_to_depool),
                name="|".join(remotes_slice.hosts.striter()),
            ):
                try:
                    for result in remotes_slice.run_async(
                        *commands,
                        is_safe=is_safe,
                        success_threshold=1.0,
                        print_output=print_output,
                        print_progress_bars=print_progress_bars,
                    ):
                        results.append(result)
                except RemoteExecutionError as e:
                    failures.append(e)
                    # Break the execution loop if more than the maximum number of failures happened.
                    if len(failures) > max_failed_batches:
                        break
            # TODO: skip sleep on the last run
            if batch_sleep is not None:
                time.sleep(batch_sleep)
        if failures:
            raise RemoteClusterExecutionError(results, failures)
        return results

    def restart_services(
        self,
        services: list[str],
        svc_to_depool: list[str],
        *,
        batch_size: int = 1,
        batch_sleep: Optional[float] = None,
        verbose: bool = True,
    ) -> list[tuple[NodeSet, MsgTreeElem]]:
        """Restart services in batches, removing the host from all the affected services first.

        Arguments:
            services: A list of services to act upon.
            svc_to_depool: A list of services (in conftool) to depool.
            batch_size: the batch size for cumin, as an integer. Defaults to 1.
            batch_sleep: the batch sleep between groups of runs.
            verbose: whether to print Cumin's output and progress bars to stdout/stderr.

        Returns:
            What :py:meth:`cumin.transports.BaseWorker.get_results` returns to allow to iterate over the results.

        Raises:
            spicerack.remote.RemoteExecutionError, spicerack.remote.RemoteClusterExecutionError: if the Cumin execution
                returns a non-zero exit code.

        """
        return self._act_on_services(
            services=services,
            svc_to_depool=svc_to_depool,
            what="restart",
            batch_size=batch_size,
            batch_sleep=batch_sleep,
            verbose=verbose,
        )

    def reload_services(
        self,
        services: list[str],
        svc_to_depool: list[str],
        *,
        batch_size: int = 1,
        batch_sleep: Optional[float] = None,
        verbose: bool = True,
    ) -> list[tuple[NodeSet, MsgTreeElem]]:
        """Reload services in batches, removing the host from all the affected services first.

        Arguments:
            services: A list of services to act upon.
            svc_to_depool: A list of services (in conftool) to depool.
            batch_size: the batch size for cumin, as an integer.Defaults to 1
            batch_sleep: the batch sleep between groups of runs.
            verbose: whether to print Cumin's output and progress bars to stdout/stderr.

        Returns:
            What :py:meth:`cumin.transports.BaseWorker.get_results` returns to allow to iterate over the results.

        Raises:
            spicerack.remote.RemoteExecutionError, spicerack.remote.RemoteClusterExecutionError: if the Cumin execution
                returns a non-zero exit code.

        """
        return self._act_on_services(
            services=services,
            svc_to_depool=svc_to_depool,
            what="reload",
            batch_size=batch_size,
            batch_sleep=batch_sleep,
            verbose=verbose,
        )

    def _act_on_services(  # pylint: disable=too-many-arguments
        self,
        *,
        services: list[str],
        svc_to_depool: list[str],
        what: str,
        batch_size: int,
        batch_sleep: Optional[float] = None,
        verbose: bool = True,
    ) -> list[tuple[NodeSet, MsgTreeElem]]:
        """Act on services in batches, depooling the servers first.

        Arguments:
            services: A list of services to act upon.
            svc_to_depool: A list of services (in conftool) to depool.
            what: Action to perform. restart by default.
            batch_size: the batch size for cumin, as an integer.
            batch_sleep: the batch sleep between groups of runs.
            verbose: whether to print Cumin's output and progress bars to stdout/stderr.

        Returns:
            What :py:meth:`cumin.transports.BaseWorker.get_results` returns to allow to iterate over the results.

        Raises:
            spicerack.remote.RemoteExecutionError, spicerack.remote.RemoteClusterExecutionError: if the Cumin execution
                returns a non-zero exit code.

        """
        commands = [f'systemctl {what} "{svc}"' for svc in services]
        return self.run(
            *commands,
            svc_to_depool=svc_to_depool,
            batch_size=batch_size,
            batch_sleep=batch_sleep,
            is_safe=False,
            print_output=verbose,
            print_progress_bars=verbose,
        )


class Remote:
    """Remote class to interact with Cumin."""

    def __init__(self, config: str, dry_run: bool = True) -> None:
        """Initialize the instance.

        Arguments:
            config: the path of Cumin's configuration file.
            dry_run: whether this is a DRY-RUN.

        """
        self._config = Config(config)
        self._dry_run = dry_run

    def query(self, query_string: str, use_sudo: bool = False) -> "RemoteHosts":
        """Execute a Cumin query and return the matching hosts.

        Arguments:
            query_string: the Cumin query string to execute.
            use_sudo: If True will prepend 'sudo -i' to every command.

        """
        # TODO: Revisit the current implementation of sudo once Cumin has native support for it.
        try:
            hosts = query.Query(self._config).execute(query_string)
        except CuminError as e:
            raise RemoteError("Failed to execute Cumin query") from e

        return RemoteHosts(self._config, hosts, dry_run=self._dry_run, use_sudo=use_sudo)

    def query_confctl(self, conftool: ConftoolEntity, **tags: str) -> LBRemoteCluster:
        """Execute a conftool node query and return the matching hosts.

        Arguments:
            conftool: the conftool instance for the node type objects.
            tags: Conftool tags for node type objects as keyword arguments.

        Raises:
            spicerack.remote.RemoteError: if unable to query the hosts.

        """
        # get the list of hosts from confctl
        try:
            hosts_conftool = [obj.name for obj in conftool.get(**tags)]
            query_string = ",".join(hosts_conftool)
        except SpicerackError as e:
            raise RemoteError("Failed to execute the conftool query") from e

        remote_hosts = self.query(query_string)
        host_diff = set(hosts_conftool) - set(remote_hosts.hosts)
        if host_diff:  # pragma: no cover | This should never happen with a direct backend.
            logger.warning("Hosts present in conftool but not in puppet: %s", ",".join(host_diff))
        return LBRemoteCluster(self._config, remote_hosts, conftool)


class RemoteHosts:
    """Class to execute remote commands on hosts. The instances are also iterable."""

    def __init__(self, config: Config, hosts: NodeSet, dry_run: bool = True, use_sudo: bool = False) -> None:
        """Initialize the instance.

        Arguments:
            config: the configuration for Cumin.
            hosts: the hosts to target for the remote execution.
            dry_run: whether this is a DRY-RUN.
            use_sudo: if True will prepend ``sudo -i`` to every command.

        Raises:
            spicerack.remote.RemoteError: if no hosts were provided.

        """
        if not hosts:
            raise RemoteError("No hosts provided")

        self._config = config
        self._hosts = hosts
        self._dry_run = dry_run
        self._use_sudo = use_sudo

    @property
    def dry_run(self) -> bool:
        """Getter for know if it was instantiated with DRY-RUN or not. Useful for RemoteHostsAdapter instances."""
        return self._dry_run

    @property
    def hosts(self) -> NodeSet:
        """Returns a copy of the current hosts targeted."""
        return self._hosts.copy()

    def __str__(self) -> str:
        """String representation of the instance.

        Returns:
            the hosts of the current instance in ``NodeSet`` notation.

        """
        return str(self._hosts)

    def __len__(self) -> int:
        """Returns the number of hosts targeted."""
        return len(self._hosts)

    def __iter__(self) -> Iterator["RemoteHosts"]:
        """Iterate over all remote hosts.

        Yields:
            spicerack.remote.RemoteHosts: an instance for each host.

        """
        yield from self.split(len(self))

    def split(self, n_slices: int) -> Iterator["RemoteHosts"]:
        """Split the current remote in n_slices RemoteHosts instances.

        Arguments:
            n_slices: the number of slices to slice the remote in.

        Yields:
            spicerack.remote.RemoteHosts: the instances for the subset of nodes.

        """
        for nodeset in self._hosts.split(n_slices):
            yield RemoteHosts(self._config, nodeset, dry_run=self._dry_run, use_sudo=self._use_sudo)

    def get_subset(self, subset: NodeSet) -> "RemoteHosts":
        """Return a new RemoteHosts instance with a subset of the existing set of hosts.

        Arguments:
            subset: the subset of hosts to select. They must all be part of the current set.

        Raises:
            spicerack.remote.RemoteError: if any host in the subset is not part of the instance hosts.

        Returns:
            a new instance with only the subset hosts.

        """
        if not self._hosts.issuperset(subset):
            raise RemoteError(f"The provided set {subset} is not a subset of the current set {self._hosts}")

        return RemoteHosts(self._config, subset, dry_run=self._dry_run, use_sudo=self._use_sudo)

    @staticmethod
    def _prepend_sudo(command: Union[str, Command]) -> Union[str, Command]:
        if isinstance(command, str):
            return "sudo -i " + command

        return Command(
            "sudo -i " + command.command,
            timeout=command.timeout,
            ok_codes=command.ok_codes,
        )

    def run_async(
        self,
        *commands: Union[str, Command],
        success_threshold: float = 1.0,
        batch_size: Optional[Union[int, str]] = None,
        batch_sleep: Optional[float] = None,
        is_safe: bool = False,
        print_output: bool = True,
        print_progress_bars: bool = True,
    ) -> Iterator[tuple[NodeSet, MsgTreeElem]]:
        """Execute commands on hosts matching a query via Cumin in async mode and return its results.

        Arguments:
            *commands: arbitrary number of commands to execute on the target hosts.
            success_threshold: to consider the execution successful, must be between 0.0 and 1.0.
            batch_size: the batch size for cumin, either as percentage (e.g. ``25%``) or absolute number (e.g. ``5``).
            batch_sleep: the batch sleep in seconds to use in Cumin before scheduling the next host.
            is_safe: whether the command is safe to run also in dry-run mode because it's a read-only command that
                doesn't modify the state.
            print_output: whether to print Cumin's output to stdout.
            print_progress_bars: whether to print Cumin's progress bars to stderr.

        Raises:
            spicerack.remote.RemoteExecutionError: if the Cumin execution returns a non-zero exit code.

        """
        return self._execute(
            list(commands),
            mode="async",
            success_threshold=success_threshold,
            batch_size=batch_size,
            batch_sleep=batch_sleep,
            is_safe=is_safe,
            print_output=print_output,
            print_progress_bars=print_progress_bars,
        )

    def run_sync(
        self,
        *commands: Union[str, Command],
        success_threshold: float = 1.0,
        batch_size: Optional[Union[int, str]] = None,
        batch_sleep: Optional[float] = None,
        is_safe: bool = False,
        print_output: bool = True,
        print_progress_bars: bool = True,
    ) -> Iterator[tuple[NodeSet, MsgTreeElem]]:
        """Execute commands on hosts matching a query via Cumin in sync mode and returns its results.

        Arguments:
            *commands: arbitrary number of commands to execute on the target hosts.
            success_threshold: to consider the execution successful, must be between 0.0 and 1.0.
            batch_size: the batch size for cumin, either as percentage (e.g. ``25%``) or absolute number (e.g. ``5``).
            batch_sleep: the batch sleep in seconds to use in Cumin before scheduling the next host.
            is_safe: whether the command is safe to run also in dry-run mode because it's a read-only command that
                doesn't modify the state.
            print_output: whether to print Cumin's output to stdout.
            print_progress_bars: whether to print Cumin's progress bars to stderr.

        Raises:
            spicerack.remote.RemoteExecutionError: if the Cumin execution returns a non-zero exit code.

        """
        return self._execute(
            list(commands),
            mode="sync",
            success_threshold=success_threshold,
            batch_size=batch_size,
            batch_sleep=batch_sleep,
            is_safe=is_safe,
            print_output=print_output,
            print_progress_bars=print_progress_bars,
        )

    def reboot(self, batch_size: int = 1, batch_sleep: Optional[float] = 180.0) -> None:
        """Reboot hosts.

        Arguments:
            batch_size: how many hosts to reboot in parallel.
            batch_sleep: how long to sleep between one reboot and the next.

        """
        if len(self._hosts) == 1:  # Temporary workaround until T213296 is fixed.
            batch_sleep = None

        logger.info(
            "Rebooting %d hosts in batches of %d with %.1fs of sleep in between: %s",
            len(self._hosts),
            batch_size,
            batch_sleep if batch_sleep is not None else 0.0,
            self._hosts,
        )

        self.run_sync(
            transports.Command("reboot-host", timeout=30),
            batch_size=batch_size,
            batch_sleep=batch_sleep,
        )

    @retry(
        tries=240,
        delay=timedelta(seconds=10),
        backoff_mode="constant",
        exceptions=(RemoteCheckError,),
    )
    def wait_reboot_since(self, since: datetime, print_progress_bars: bool = True) -> None:
        """Poll the host until is reachable and has an uptime lower than the provided datetime.

        Arguments:
            since: the time after which the host should have booted.
            print_progress_bars: whether to print Cumin's progress bars to stderr.

        Raises:
            spicerack.remote.RemoteCheckError: if unable to connect to the host or the uptime is higher than expected.
                When in DRY-RUN mode, it will raise only if unable to connect.

        """
        delta = (datetime.utcnow() - since).total_seconds()
        try:
            uptimes = self.uptime(print_progress_bars=print_progress_bars)
        except (RemoteExecutionError, RemoteError) as e:
            if self._dry_run:
                raise RemoteCheckError(f"Reboot for {self._hosts} not found: unable to get uptime") from e
            raise RemoteCheckError(
                f"Reboot for {self._hosts} not found yet, keep polling for it: unable to get uptime"
            ) from e

        for nodeset, uptime in uptimes:
            if uptime >= delta:
                msg = f"uptime {round(uptime, 2)} > threshold {round(delta, 2)}"
                if self._dry_run:
                    logger.info(
                        "Reboot for %s not found - expected in dry run mode, host not rebooted: %s", nodeset, msg
                    )
                else:
                    raise RemoteCheckError(f"Reboot for {nodeset} not found yet, keep polling for it: {msg}")

        if not self._dry_run:
            logger.info("Found reboot since %s for hosts %s", since, self._hosts)

    def uptime(self, print_progress_bars: bool = True) -> list[tuple[NodeSet, float]]:
        """Get current uptime.

        Arguments:
            print_progress_bars: whether to print Cumin's progress bars to stderr.

        Returns:
            A list of 2-element :py:class:`tuple` instances with hosts :py:class:`ClusterShell.NodeSet.NodeSet`
            as first item and :py:class:`float` uptime as second item.

        Raises:
            spicerack.remote.RemoteError: if unable to parse the output as an uptime.

        """
        results = self.run_sync(
            transports.Command("cat /proc/uptime", timeout=10),
            is_safe=True,
            print_output=False,
            print_progress_bars=print_progress_bars,
        )
        logger.debug("Got uptime for hosts %s", self._hosts)
        # Callback to extract the uptime from /proc/uptime (i.e. getting 12345.67 from '12345.67 123456789.00').
        return RemoteHosts.results_to_list(results, callback=lambda output: float(output.split()[0]))

    @staticmethod
    def results_to_list(
        results: Iterator[tuple[NodeSet, MsgTreeElem]],
        callback: Optional[Callable] = None,
    ) -> list[tuple[NodeSet, Any]]:
        """Extract execution results into a list converting them with an optional callback.

        Todo:
            move it directly into Cumin.

        Arguments:
            results: generator returned by run_sync() and run_async() to iterate over the results.
            callback: an optional callable to apply to each result output (it can be multiline).
                The callback will be called with a the string output as the only parameter and must return the
                extracted value. The return type can be chosen freely.

        Returns:
            A list of 2-element tuples with hosts :py:class:`ClusterShell.NodeSet.NodeSet` as first item and the
            extracted outputs :py:class:`str` as second. This is because NodeSet are not hashable.

        Raises:
            spicerack.remote.RemoteError: if unable to run the callback.

        """
        extracted = []
        for nodeset, output in results:
            result = output.message().decode().strip()
            if callback is not None:
                try:
                    result = callback(result)
                except Exception as e:
                    raise RemoteError(
                        f"Unable to extract data with {callback.__name__} for {nodeset} from: {result}"
                    ) from e

            extracted.append((nodeset, result))

        return extracted

    def _execute(  # pylint: disable=too-many-arguments
        self,
        commands: Sequence[Union[str, Command]],
        *,
        mode: str = "sync",
        success_threshold: float = 1.0,
        batch_size: Optional[Union[int, str]] = None,
        batch_sleep: Optional[float] = None,
        is_safe: bool = False,
        print_output: bool = True,
        print_progress_bars: bool = True,
    ) -> Iterator[tuple[NodeSet, MsgTreeElem]]:
        """Lower level Cumin's execution of commands on the target nodes and return its results.

        Arguments:
            commands: the list of commands to execute on the target hosts, either a list of commands or a list
                of cumin.transports.Command instances.
            mode: the Cumin's mode of execution. Accepted values: sync, async.
            success_threshold: to consider the execution successful, must be between 0.0 and 1.0.
            batch_size: the batch size for cumin, either as percentage (e.g. ``25%``) or absolute number (e.g. ``5``).
            batch_sleep: the batch sleep in seconds to use in Cumin before scheduling the next host.
            is_safe: whether the command is safe to run also in dry-run mode because it's a read-only command that
                doesn't modify the state.
            print_output: whether to print Cumin's output to stdout.
            print_progress_bars: whether to print Cumin's progress bars to stderr.

        Raises:
            spicerack.remote.RemoteExecutionError: if the Cumin execution returns a non-zero exit code.

        """
        if batch_size is None:
            parsed_batch_size = {"value": None, "ratio": None}
        else:
            parsed_batch_size = target_batch_size(str(batch_size))

        if self._use_sudo:
            commands = [self._prepend_sudo(command) for command in commands]

        target = transports.Target(
            self._hosts,
            batch_size=parsed_batch_size["value"],
            batch_size_ratio=parsed_batch_size["ratio"],
            batch_sleep=batch_sleep,
        )
        worker = transport.Transport.new(self._config, target)
        worker.commands = commands
        worker.handler = mode
        worker.success_threshold = success_threshold
        worker.progress_bars = print_progress_bars
        if print_output:
            worker.reporter = TqdmReporter
        else:
            worker.reporter = NullReporter

        logger.debug(
            "Executing commands %s on %d hosts: %s",
            commands,
            len(target.hosts),
            str(target.hosts),
        )

        if self._dry_run and not is_safe:
            return iter(())  # Empty generator

        ret = worker.execute()

        if ret != 0 and not self._dry_run:
            raise RemoteExecutionError(ret, "Cumin execution failed", worker.get_results())

        return worker.get_results()
