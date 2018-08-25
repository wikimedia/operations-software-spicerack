"""Remote module to execute commands on hosts via Cumin."""
import logging

from cumin import Config, CuminError, query, transport, transports
from cumin.cli import target_batch_size

from spicerack.exceptions import SpicerackError


logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


class RemoteError(SpicerackError):
    """Custom exception class for errors of this module."""


class RemoteExecutionError(RemoteError):
    """Custom exception class for remote execution errors."""

    def __init__(self, retcode, message):
        """Override parent constructor to add the return code attribute."""
        super().__init__('{msg} (exit_code={ret})'.format(msg=message, ret=retcode))
        self.retcode = retcode


class Remote:
    """Remote class to interact with Cumin."""

    def __init__(self, config, dry_run=True):
        """Initialize the instance.

        Arguments:
            config (str): the path of Cumin's configuration file.
            dry_run (bool, optional): whether this is a DRY-RUN.
        """
        self._config = Config(config)
        self._dry_run = dry_run

    def query(self, query_string, remote_hosts_factory=None):
        """Execute a Cumin query and return the matching hosts.

        Arguments:
            query_string (str): the Cumin query string to execute.
            remote_hosts_factory (function, optional): a function(config, hosts, dry_run=True) to be used instead of
                `spicerack.remote.default_remote_hosts_factory` to instantiate the target returned by the remote query.
                It must return an instance of `spicerack.remote.RemoteHosts` or any derived class.

        Returns:
            spicerack.remote.RemoteHosts: already initialized with Cumin's configuration and the target hosts.

        """
        try:
            hosts = query.Query(self._config).execute(query_string)
        except CuminError as e:
            raise RemoteError('Failed to execute Cumin query') from e

        if remote_hosts_factory is None:
            remote_hosts_factory = default_remote_hosts_factory

        return remote_hosts_factory(self._config, hosts, dry_run=self._dry_run)


class RemoteHosts:
    """Remote Executor class.

    This class can be extended to customize the interaction with remote hosts passing a custom factory function to
    `spicerack.remote.Remote.query`.
    """

    def __init__(self, config, hosts, dry_run=True):
        """Initiliaze the instance.

        Arguments:
            config (cumin.Config): the configuration for Cumin.
            hosts (cumin.NodeSet): the hosts to target for the remote execution.
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
    def hosts(self):
        """Getter for the hosts property.

        Returns:
            cumin.NodeSet: a copy of the targeted hosts.

        """
        return self._hosts.copy()

    def run_async(self, *commands, success_threshold=1.0, batch_size=None, batch_sleep=None, is_safe=False):
        """Execute commands on hosts matching a query via Cumin in async mode.

        Arguments:
            *commands (str, cumin.transports.Command): arbitrary number of commands to execute on the target hosts.
            success_threshold (float, optional): to consider the execution successful, must be between 0.0 and 1.0.
            batch_size (int, str, optional): the batch size for cumin, either as percentage (i.e. '25%')
                or absolute number (i.e. 5).
            batch_sleep (float, optional): the batch sleep in seconds to use in Cumin before scheduling the next host.
            is_safe (bool, optional): whether the command is safe to run also in dry-run mode because it's a read-only
                command that doesn't modify the state.

        Returns:
            generator: cumin.transports.BaseWorker.get_results to allow to iterate over the results.

        Raises:
            RemoteExecutionError: if the Cumin execution returns a non-zero exit code.

        """
        return self._execute(commands, mode='async', success_threshold=success_threshold, batch_size=batch_size,
                             batch_sleep=batch_sleep, is_safe=is_safe)

    def run_sync(self, *commands, success_threshold=1.0, batch_size=None, batch_sleep=None, is_safe=False):
        """Execute commands on hosts matching a query via Cumin in sync mode.

        Arguments:
            *commands (str, cumin.transports.Command): arbitrary number of commands to execute on the target hosts.
            success_threshold (float, optional): to consider the execution successful, must be between 0.0 and 1.0.
            batch_size (int, str, optional): the batch size for cumin, either as percentage (i.e. '25%')
                or absolute number (i.e. 5).
            batch_sleep (float, optional): the batch sleep in seconds to use in Cumin before scheduling the next host.
            is_safe (bool, optional): whether the command is safe to run also in dry-run mode because it's a read-only
                command that doesn't modify the state.

        Returns:
            generator: cumin.transports.BaseWorker.get_results to allow to iterate over the results.

        Raises:
            RemoteExecutionError: if the Cumin execution returns a non-zero exit code.

        """
        return self._execute(commands, mode='sync', success_threshold=success_threshold, batch_size=batch_size,
                             batch_sleep=batch_sleep, is_safe=is_safe)

    def _execute(self, commands, mode='sync', success_threshold=1.0,  # pylint: disable=too-many-arguments
                 batch_size=None, batch_sleep=None, is_safe=False):
        """Lower level Cumin's execution of commands on the target nodes.

        Arguments:
            commands (list): the list of commands to execute on the target hosts.
            mode (str, optional): the Cumin's mode of execution. Accepted values: sync, async.
            success_threshold (float, optional): to consider the execution successful, must be between 0.0 and 1.0.
            batch_size (int, str, optional): the batch size for cumin, either as percentage (i.e. '25%')
                or absolute number (i.e. 5).
            batch_sleep (float, optional): the batch sleep in seconds to use in Cumin before scheduling the next host.
            is_safe (bool, optional): whether the command is safe to run also in dry-run mode because it's a read-only
                command that doesn't modify the state.

        Returns:
            generator: cumin.transports.BaseWorker.get_results to allow to iterate over the results.

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
        worker.commands = list(commands)
        worker.handler = mode
        worker.success_threshold = success_threshold

        logger.debug('Executing commands %s on %d hosts: %s', commands, len(target.hosts), str(target.hosts))

        if self._dry_run and not is_safe:
            return iter(())  # Empty generator

        ret = worker.execute()

        if ret != 0 and not self._dry_run:
            raise RemoteExecutionError(ret, 'Cumin execution failed')

        return worker.get_results()


def default_remote_hosts_factory(config, hosts, dry_run=True):
    """Default remote hosts factory function used in `Remote.query()`.

    Arguments:
        config (cumin.Config): the configuration for Cumin.
        hosts (cumin.NodeSet): the hosts to target for the remote execution.
        dry_run (bool, optional): whether this is a DRY-RUN.

    Returns:
        spicerack.remote.RemoteHosts: an initialized instance.

    """
    return RemoteHosts(config, hosts, dry_run=dry_run)
