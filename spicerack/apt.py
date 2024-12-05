"""APT module."""

import logging
from collections.abc import Iterator
from typing import Any

from ClusterShell.MsgTree import MsgTreeElem
from ClusterShell.NodeSet import NodeSet

from spicerack.exceptions import SpicerackError
from spicerack.remote import RemoteHostsAdapter

logger = logging.getLogger(__name__)
APT_GET_ENVS: tuple[str, ...] = ("DEBIAN_FRONTEND=noninteractive",)
"""The environment variables used for all ``apt-get`` commands."""
APT_GET_INSTALL_OPTIONS: tuple[str, ...] = (
    "--quiet",
    "--yes",
    '--option Dpkg::Options::="--force-confdef"',
    '--option Dpkg::Options::="--force-confold"',
)
"""The CLI arguments passed to all ``apt-get`` commands."""
APT_GET_BASE_COMMAND: str = " ".join((*APT_GET_ENVS, "/usr/bin/apt-get", *APT_GET_INSTALL_OPTIONS))
"""The base ``apt-get`` command to execute."""


class AptGetError(SpicerackError):
    """Custom base exception class for errors in the AptGetHosts class."""


class AptGetHosts(RemoteHostsAdapter):
    """Class to manage packages via apt-get.

    Examples:
        ::

                >>> hosts = spicerack.remote().query('A:myalias')
                >>> apt_get = spicerack.apt_get(hosts)

    """

    def update(self, **kwargs: Any) -> Iterator[tuple[NodeSet, MsgTreeElem]]:
        """Update the list of available packages known to apt-get.

        Warnings:
            This can fail if unable to get the apt lock on the host because other apt operations are ongoing, including
            but not limited to, the periodic Puppet run that performs ``apt-get update`` before every run.
            Consider wrapping it in a :py:func:`wmflib.interactive.confirm_on_failure` call.

        Examples:
            ::

                >>> hosts = spicerack.remote().query('A:myalias')
                >>> apt_get = spicerack.apt_get(hosts)
                >>> apt_get.update()
                >>> # Optionally pass any argument accepted by run_sync()
                >>> apt_get.update(batch_size=2, print_progress_bars=False)

        Arguments:
            **kwargs: optional keyword arguments to be passed to the :py:meth:`spicerack.remote.RemoteHosts.run_sync`
                method.

        Returns:
            The result of the update operations, see :py:meth:`spicerack.remote.RemoteHosts.run_sync`.

        """
        logger.info("Running apt-get update")
        return self.run("update", **kwargs)

    def install(self, *packages: str, **kwargs: Any) -> Iterator[tuple[NodeSet, MsgTreeElem]]:
        """Apt-get install the provided packages.

        Install the provided packages keeping the existing configuration files (typically managed by Puppet) in a
        non-interactive way that confirms the installation of new additional binary packages (which e.g. can happen if
        a package pulls in a new dependency).

        Warnings:
            This can fail if unable to get the apt lock on the host because other apt operations are ongoing, including
            but not limited to, the periodic Puppet run that performs ``apt-get update`` before every run.
            Consider wrapping it in a :py:func:`wmflib.interactive.confirm_on_failure` call.

        Notes:
            Downgrades of package versions are not supported as they need the ``--force-yes`` CLI argument to be passed
            to ``apt-get`` and that's deemed unsafe for the possibility of unwanted results.

        Examples:
            ::

                >>> hosts = spicerack.remote().query('A:myalias')
                >>> apt_get = spicerack.apt_get(hosts)
                >>> apt_get.install('package1', 'package2')
                >>> # Optionally pass any argument accepted by run_sync()
                >>> apt_get.install('package1', 'package2', batch_size=2, print_progress_bars=False)

        Arguments:
            *packages: packages to install as positional arguments.
            **kwargs: optional keyword arguments to be passed to the :py:meth:`spicerack.remote.RemoteHosts.run_sync`
                method.

        Returns:
            The result of the installation operations, see :py:meth:`spicerack.remote.RemoteHosts.run_sync`.

        """
        if not packages:
            raise AptGetError("No packages to install were provided.")

        logger.info("Running apt-get install for the following packages: %s", packages)
        return self.run(" ".join(["install", *packages]), **kwargs)

    def run(self, apt_get_command: str, **kwargs: Any) -> Iterator[tuple[NodeSet, MsgTreeElem]]:
        """Execute the given apt-get command on the current hosts.

        Warnings:
            This can fail if unable to get the apt lock on the host because other apt operations are ongoing, including
            but not limited to, the periodic Puppet run that performs ``apt-get update`` before every run.
            Consider wrapping it in a :py:func:`wmflib.interactive.confirm_on_failure` call.

        Examples:
            ::

                >>> hosts = spicerack.remote().query('A:myalias')
                >>> apt_get = spicerack.apt_get(hosts)
                >>> apt_get.run('autoclean')
                >>> # Optionally pass any argument accepted by run_sync()
                >>> apt_get.run('purge package1', batch_size=2, print_progress_bars=False)

        Arguments:
            apt_get_command: the command part after apt-get to be executed (e.g. ``update``).
            **kwargs: optional keyword arguments to be passed to the :py:meth:`spicerack.remote.RemoteHosts.run_sync`
                method.

        Returns:
            The result of the update operations, see :py:meth:`spicerack.remote.RemoteHosts.run_sync`.

        """
        command = f"{APT_GET_BASE_COMMAND} {apt_get_command}"
        logger.info("Running apt-get command: %s", command)
        return self._remote_hosts.run_sync(command, **kwargs)
