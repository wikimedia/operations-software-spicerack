"""Icinga module."""
import logging

from datetime import timedelta

from spicerack.exceptions import SpicerackError


DOWNTIME_COMMAND = 'icinga-downtime -h "{hostname}" -d {duration} -r {reason}'
ICINGA_DOMAIN = 'icinga.wikimedia.org'
MIN_DOWNTIME_SECONDS = 60  # Minimum time in seconds the downtime can be set
logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


class IcingaError(SpicerackError):
    """Custom exception class for errors of this module."""


class Icinga:
    """Class to interact with the Icinga server."""

    def __init__(self, icinga_host):
        """Initialize the instance.

        Arguments:
            icinga_host (spicerack.remote.RemoteHosts): the RemoteHosts instance for the Icinga server.
        """
        self._icinga_host = icinga_host

    def downtime_hosts(self, hosts, reason, *, duration=timedelta(hours=4)):
        """Downtime hosts on the Icinga server for the given time with a message.

        Arguments:
            hosts (list, cumin.NodeSet): an iterable with the list of hostnames to downtime.
            reason (spicerak.administrative.Reason): the reason to set for the downtime on the Icinga server.
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
