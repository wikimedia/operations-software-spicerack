"""Alerting module."""
import logging
from contextlib import contextmanager
from datetime import timedelta
from typing import Iterator

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
            alertmanager_hosts (spicerack.alertmanager.AlertmanagerHosts): the Alertmanager hosts to talk to.
            icinga_hosts (spicerack.icinga.IcingaHosts): the Icinga hosts to talk to.

        """
        self._am = alertmanager_hosts
        self._icinga = icinga_hosts

    @contextmanager
    def downtimed(
        self, reason: Reason, *, duration: timedelta = timedelta(hours=4), remove_on_error: bool = False
    ) -> Iterator[None]:
        """Context manager to perform actions while the hosts are downtimed on Alertmanager and Icinga.

        Arguments:
            reason (spicerack.administrative.Reason): the reason to set for the downtime.
            duration (datetime.timedelta, optional): the length of the downtime period.
            remove_on_error: should the downtime be removed even if an exception was raised.

        Yields:
            None: it just yields control to the caller once Alertmanager and Icinga have
            received the downtime and deletes the downtime once getting back the
            control.

        """
        downtime_id = self.downtime(reason, duration=duration)
        try:
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
            reason (spicerack.administrative.Reason): the downtime reason.
            duration (datetime.timedelta): how long to downtime for.

        Returns:
            str: the downtime ID.

        Raises:
            AlertmanagerError: if none of the `alertmanager_urls` API returned a success.
            IcingaError: if there is a problem downtiming the hosts in Icinga.

        """
        self._icinga.downtime(reason, duration=duration)
        return self._am.downtime(reason, duration=duration)

    def remove_downtime(self, downtime_id: str) -> None:
        """Remove a downtime.

        Arguments:
            downtime_id (str): the downtime ID to remove.

        """
        self._icinga.remove_downtime()
        return self._am.remove_downtime(downtime_id)
