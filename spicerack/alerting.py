"""Alerting module."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta

from spicerack.administrative import Reason
from spicerack.alertmanager import AlertmanagerHosts
from spicerack.icinga import IcingaHosts

logger = logging.getLogger(__name__)


class AlertingHosts:
    """Operate on Alertmanager and Icinga via their APIs."""

    def __init__(
        self,
        alertmanager_hosts: AlertmanagerHosts,
        icinga_hosts: IcingaHosts,
    ) -> None:
        """Initialize the instance.

        Arguments:
            alertmanager_hosts: the Alertmanager hosts to talk to.
            icinga_hosts: the Icinga hosts to talk to.

        """
        self._am = alertmanager_hosts
        self._icinga = icinga_hosts

    @contextmanager
    def downtimed(
        self, reason: Reason, *, duration: timedelta = timedelta(hours=4), remove_on_error: bool = False
    ) -> Iterator[None]:
        """Context manager to perform actions while the hosts are downtimed on Alertmanager and Icinga.

        Arguments:
            reason: the reason to set for the downtime.
            duration: the length of the downtime period.
            remove_on_error: should the downtime be removed even if an exception was raised.

        Yields:
            None: it just yields control to the caller once Alertmanager and Icinga have
            received the downtime and deletes the downtime once getting back the
            control.

        """
        downtime_id = self.downtime(reason, duration=duration)
        try:  # pylint: disable=no-else-raise
            yield
        except BaseException:
            if remove_on_error:
                self.remove_downtime(downtime_id)
            raise
        else:
            self.remove_downtime(downtime_id)

    def downtime(self, reason: Reason, *, duration: timedelta = timedelta(hours=4)) -> str:
        """Issue a new downtime.

        Arguments:
            reason: the downtime reason.
            duration: how long to downtime for.

        Returns:
            The alertmanager downtime ID.

        Raises:
            spicerack.alertmanager.AlertmanagerError: if none of the ``alertmanager_urls`` API returned a success.
            spicerack.icinga.IcingaError: if there is a problem downtiming the hosts on Icinga.

        """
        self._icinga.downtime(reason, duration=duration)
        return self._am.downtime(reason, duration=duration)

    def remove_downtime(self, downtime_id: str) -> None:
        """Remove a downtime.

        Arguments:
            downtime_id: the alertmanager downtime ID to remove.

        """
        self._icinga.remove_downtime()
        return self._am.remove_downtime(downtime_id)
