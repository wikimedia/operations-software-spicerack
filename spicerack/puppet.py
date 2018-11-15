"""Puppet module."""
import logging

from contextlib import contextmanager

from spicerack.remote import RemoteHostsAdapter


logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


class PuppetHosts(RemoteHostsAdapter):
    """Class to manage Puppet on the target hosts."""

    @contextmanager
    def disabled(self, reason):
        """Context manager to perform actions while puppet is disabled.

        Arguments:
            reason (spicerack.administrative.Reason): the reason to set for the Puppet disable and to use for the
                Puppet enable.
        """
        self.disable(reason)
        try:
            yield
        finally:
            self.enable(reason)

    def disable(self, reason):
        """Disable puppet with a specific reason.

        If Puppet was already disabled on a host with a different reason, the reason will not be overriden, allowing to
        leave Puppet disabled when re-enabling it if it was already disabled.

        Arguments:
            reason (spicerack.administrative.Reason): the reason to set for the Puppet disable.
        """
        logger.info('Disabling Puppet with reason %s on %d hosts: %s', reason.quoted(), len(self), self)
        self._remote_hosts.run_sync('disable-puppet {reason}'.format(reason=reason.quoted()))

    def enable(self, reason):
        """Enable Puppet with a specific reason, it must be the same used to disable it.

        Puppet will be re-enabled only if it was disable with the same reason. If it was disable with a different reason
        it will keep being disabled.

        Arguments:
            reason (spicerack.administrative.Reason): the reason to use for the Puppet enable.
        """
        logger.info('Enabling Puppet with reason %s on %d hosts: %s', reason.quoted(), len(self), self)
        self._remote_hosts.run_sync('enable-puppet {reason}'.format(reason=reason.quoted()))
