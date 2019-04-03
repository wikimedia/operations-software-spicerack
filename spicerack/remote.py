"""Remote module to execute commands on hosts via Cumin."""
import logging
import os

from datetime import datetime, timedelta
from typing import Any, Callable, Iterator, List, Optional, Sequence, Tuple, Union

from ClusterShell.MsgTree import MsgTreeElem
from cumin import Config, CuminError, NodeSet, query, transport, transports
from cumin.cli import target_batch_size
from cumin.transports import Command

from spicerack.decorators import retry
from spicerack.exceptions import SpicerackCheckError, SpicerackError


logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


class RemoteError(SpicerackError):
    """Custom exception class for errors of this module."""


class RemoteCheckError(SpicerackCheckError):
    """Custom exception class for check errors of this module."""


class RemoteExecutionError(RemoteError):
    """Custom exception class for remote execution errors."""

    def __init__(self, retcode: int, message: str) -> None:
        """Override parent constructor to add the return code attribute."""
        super().__init__('{msg} (exit_code={ret})'.format(msg=message, ret=retcode))
        self.retcode = retcode


class RemoteHostsAdapter:
    """Base adapter to write classes that expand the capabilities of RemoteHosts.

    This adapter class is a helper class to reduce duplication when writing classes that needs to add capabilities to a
    RemoteHosts instance. The goal is to not extend the RemoteHosts but instead delegate to its instances.
    This class fits when a single RemoteHosts instance is enough, but for more complex cases, in which multiple
    RemoteHosts instances should be orchestrated, it's ok to not extend this class and create a standalone one.
    """

    def __init__(self, remote_hosts: 'RemoteHosts') -> None:
        """Initialize the instance.

        Arguments:
            remote_hosts (spicerack.remote.RemoteHosts): the instance to act on the remote hosts.
        """
        self._remote_hosts = remote_hosts

    def __str__(self) -> str:
        """String representation of the instance.

        Returns:
            str: the string representation of the target hosts.

        """
        return str(self._remote_hosts)

    def __len__(self) -> int:
        """Length of the instance.

        Returns:
            int: the number of target hosts.

        """
        return len(self._remote_hosts)


class Remote:
    """Remote class to interact with Cumin."""

    def __init__(self, config: str, dry_run: bool = True) -> None:
        """Initialize the instance.

        Arguments:
            config (str): the path of Cumin's configuration file.
            dry_run (bool, optional): whether this is a DRY-RUN.
        """
        self._config = Config(config)
        self._dry_run = dry_run

    def query(self, query_string: str) -> 'RemoteHosts':
        """Execute a Cumin query and return the matching hosts.

        Arguments:
            query_string (str): the Cumin query string to execute.

        Returns:
            spicerack.remote.RemoteHosts: RemoteHosts instance matching the given query.

        """
        try:
            hosts = query.Query(self._config).execute(query_string)
        except CuminError as e:
            raise RemoteError('Failed to execute Cumin query') from e

        return RemoteHosts(self._config, hosts, dry_run=self._dry_run)


class RemoteHosts:
    """Remote Executor class.

    This class can be extended to customize the interaction with remote hosts passing a custom factory function to
    `spicerack.remote.Remote.query`.
    """

    def __init__(self, config: Config, hosts: NodeSet, dry_run: bool = True) -> None:
        """Initialize the instance.

        Arguments:
            config (cumin.Config): the configuration for Cumin.
            hosts (ClusterShell.NodeSet.NodeSet): the hosts to target for the remote execution.
            dry_run (bool, optional): whether this is a DRY-RUN.

        Raises:
            spicerack.remote.RemoteError: if no hosts were provided.

        """
        if not hosts:
            raise RemoteError('No hosts provided')

        self._config = config
        self._hosts = hosts
        self._dry_run = dry_run

    @property
    def hosts(self) -> NodeSet:
        """Getter for the hosts property.

        Returns:
            ClusterShell.NodeSet.NodeSet: a copy of the targeted hosts.

        """
        return self._hosts.copy()

    def __str__(self) -> str:
        """String representation of the instance.

        Returns:
            str: the string representation of the target hosts.

        """
        return str(self._hosts)

    def __len__(self) -> int:
        """Length of the instance.

        Returns:
            int: the number of target hosts.

        """
        return len(self._hosts)

    def run_async(
        self,
        *commands: Union[str, Command],
        success_threshold: float = 1.0,
        batch_size: Optional[Union[int, str]] = None,
        batch_sleep: Optional[float] = None,
        is_safe: bool = False
    ) -> Iterator[Tuple[NodeSet, MsgTreeElem]]:
        """Execute commands on hosts matching a query via Cumin in async mode.

        Arguments:
            *commands (str, cumin.transports.Command): arbitrary number of commands to execute on the target hosts.
            success_threshold (float, optional): to consider the execution successful, must be between 0.0 and 1.0.
            batch_size (int, str, optional): the batch size for cumin, either as percentage (e.g. ``25%``)
                or absolute number (e.g. ``5``).
            batch_sleep (float, optional): the batch sleep in seconds to use in Cumin before scheduling the next host.
            is_safe (bool, optional): whether the command is safe to run also in dry-run mode because it's a read-only
                command that doesn't modify the state.

        Returns:
            generator: cumin.transports.BaseWorker.get_results to allow to iterate over the results.

        Raises:
            RemoteExecutionError: if the Cumin execution returns a non-zero exit code.

        """
        return self._execute(list(commands), mode='async', success_threshold=success_threshold, batch_size=batch_size,
                             batch_sleep=batch_sleep, is_safe=is_safe)

    def run_sync(
        self,
        *commands: Union[str, Command],
        success_threshold: float = 1.0,
        batch_size: Optional[Union[int, str]] = None,
        batch_sleep: Optional[float] = None,
        is_safe: bool = False
    ) -> Iterator[Tuple[NodeSet, MsgTreeElem]]:
        """Execute commands on hosts matching a query via Cumin in sync mode.

        Arguments:
            *commands (str, cumin.transports.Command): arbitrary number of commands to execute on the target hosts.
            success_threshold (float, optional): to consider the execution successful, must be between 0.0 and 1.0.
            batch_size (int, str, optional): the batch size for cumin, either as percentage (e.g. ``25%``)
                or absolute number (e.g. ``5``).
            batch_sleep (float, optional): the batch sleep in seconds to use in Cumin before scheduling the next host.
            is_safe (bool, optional): whether the command is safe to run also in dry-run mode because it's a read-only
                command that doesn't modify the state.

        Returns:
            generator: cumin.transports.BaseWorker.get_results to allow to iterate over the results.

        Raises:
            RemoteExecutionError: if the Cumin execution returns a non-zero exit code.

        """
        return self._execute(list(commands), mode='sync', success_threshold=success_threshold, batch_size=batch_size,
                             batch_sleep=batch_sleep, is_safe=is_safe)

    def reboot(self, batch_size: int = 1, batch_sleep: Optional[float] = 180.0) -> None:
        """Reboot hosts.

        Arguments:
            batch_size (int, optional): how many hosts to reboot in parallel.
            batch_sleep (float, optional): how long to sleep between one reboot and the next.
        """
        if len(self._hosts) == 1:  # Temporary workaround until T213296 is fixed.
            batch_sleep = None

        logger.info('Rebooting %d hosts in batches of %d with %.1fs of sleep in between: %s',
                    len(self._hosts),
                    batch_size,
                    batch_sleep if batch_sleep is not None else 0.0,
                    self._hosts)

        self.run_sync(transports.Command('reboot-host', timeout=30), batch_size=batch_size, batch_sleep=batch_sleep)

    @retry(tries=25, delay=timedelta(seconds=10), backoff_mode='linear',
           exceptions=(RemoteExecutionError, RemoteCheckError))
    def wait_reboot_since(self, since: datetime) -> None:
        """Poll the host until is reachable and has an uptime lower than the provided datetime.

        Arguments:
            since (datetime.datetime): the time after which the host should have booted.

        Raises:
            spicerack.remote.RemoteCheckError: if unable to connect to the host or the uptime is higher than expected.

        """
        remaining = self.hosts
        delta = (datetime.utcnow() - since).total_seconds()
        for nodeset, uptime in self.uptime():
            if uptime >= delta:
                raise RemoteCheckError('Uptime for {hosts} higher than threshold: {uptime} > {delta}'.format(
                    hosts=nodeset, uptime=uptime, delta=delta))

            remaining.difference_update(nodeset)

        if remaining:
            raise RemoteCheckError('Unable to check uptime from {num} hosts: {hosts}'.format(
                num=len(remaining), hosts=remaining))

        logger.info('Found reboot since %s for hosts %s', since, self._hosts)

    def uptime(self) -> List[Tuple[NodeSet, float]]:
        """Get current uptime.

        Returns:
            list: a list of 2-element :py:class:`tuple` instances with hosts :py:class:`ClusterShell.NodeSet.NodeSet`
            as first item and :py:class:`float` uptime as second item.

        """
        results = self.run_sync(transports.Command('cat /proc/uptime', timeout=10), is_safe=True)
        # Callback to extract the uptime from /proc/uptime (i.e. getting 12345.67 from '12345.67 123456789.00').
        return RemoteHosts.results_to_list(results, callback=lambda output: float(output.split()[0]))

    def init_system(self) -> List[Tuple[NodeSet, str]]:
        """Detect the init system.

        Returns:
            list: a list of 2-element tuples with hosts :py:class:`ClusterShell.NodeSet.NodeSet` as first item and the
            init system :py:class:`str` as second.

        """
        results = self.run_sync(transports.Command('ps --no-headers -o comm 1', timeout=10), is_safe=True)
        return RemoteHosts.results_to_list(results)

    @staticmethod
    def results_to_list(
        results: Iterator[Tuple[NodeSet, MsgTreeElem]],
        callback: Optional[Callable] = None
    ) -> List[Tuple[NodeSet, Any]]:
        """Extract execution results into a list converting them with an optional callback.

        Todo:
            move it directly into Cumin.

        Arguments:
            results (generator): generator returned by run_sync() and run_async() to iterate over the results.
            callback (callable, optional): an optional callable to apply to each result output (it can be multiline).
                The callback will be called with a the string output as the only parameter and must return the
                extracted value. The return type can be chosen freely.

        Returns:
            list: a list of 2-element tuples with hosts :py:class:`ClusterShell.NodeSet.NodeSet` as first item and the
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
                    raise RemoteError('Unable to extract data with {cb} for {hosts} from: {output}'.format(
                        cb=callback.__name__, hosts=nodeset, output=result)) from e

            extracted.append((nodeset, result))

        return extracted

    def _execute(  # pylint: disable=too-many-arguments
        self,
        commands: Sequence[Union[str, Command]],
        mode: str = 'sync',
        success_threshold: float = 1.0,
        batch_size: Optional[Union[int, str]] = None,
        batch_sleep: Optional[float] = None,
        is_safe: bool = False
    ) -> Iterator[Tuple[NodeSet, MsgTreeElem]]:
        """Lower level Cumin's execution of commands on the target nodes.

        Arguments:
            commands (list): the list of commands to execute on the target hosts, either a list of commands or a list
                of cumin.transports.Command instances.
            mode (str, optional): the Cumin's mode of execution. Accepted values: sync, async.
            success_threshold (float, optional): to consider the execution successful, must be between 0.0 and 1.0.
            batch_size (int, str, optional): the batch size for cumin, either as percentage (e.g. ``25%``) or absolute
                number (e.g. ``5``).
            batch_sleep (float, optional): the batch sleep in seconds to use in Cumin before scheduling the next host.
            is_safe (bool, optional): whether the command is safe to run also in dry-run mode because it's a read-only
                command that doesn't modify the state.

        Returns:
            generator: as returned by :py:meth:`cumin.transports.BaseWorker.get_results` to iterate over the results.

        Raises:
            RemoteExecutionError: if the Cumin execution returns a non-zero exit code.

        """
        if batch_size is None:
            parsed_batch_size = {'value': None, 'ratio': None}
        else:
            parsed_batch_size = target_batch_size(str(batch_size))

        target = transports.Target(
            self._hosts, batch_size=parsed_batch_size['value'], batch_size_ratio=parsed_batch_size['ratio'],
            batch_sleep=batch_sleep)
        worker = transport.Transport.new(self._config, target)
        worker.commands = commands
        worker.handler = mode
        worker.success_threshold = success_threshold

        logger.debug('Executing commands %s on %d hosts: %s', commands, len(target.hosts), str(target.hosts))

        if self._dry_run and not is_safe:
            return iter(())  # Empty generator

        # Temporary workaround until Cumin has full support to suppress output (T212783)
        # and the Colorama issue that slows down the process is fixed (T217038)
        stdout = transports.clustershell.sys.stdout
        stderr = transports.clustershell.sys.stderr
        try:
            with open(os.devnull, 'w') as discard_output:
                transports.clustershell.sys.stdout = discard_output
                transports.clustershell.sys.stderr = discard_output
                ret = worker.execute()
        finally:
            transports.clustershell.sys.stdout = stdout
            transports.clustershell.sys.stderr = stderr

        if ret != 0 and not self._dry_run:
            raise RemoteExecutionError(ret, 'Cumin execution failed')

        return worker.get_results()
