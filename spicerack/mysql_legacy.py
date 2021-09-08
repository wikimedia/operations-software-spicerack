"""MySQL module (legacy).

Todo:
    replace with a proper MySQL module that uses a Python MySQL client, preferably in a parallel way.

"""
import logging
from datetime import datetime
from typing import Dict, Iterator, Optional, Tuple, Union

from ClusterShell.MsgTree import MsgTreeElem
from cumin import NodeSet

from spicerack.constants import CORE_DATACENTERS
from spicerack.decorators import retry
from spicerack.exceptions import SpicerackError
from spicerack.remote import Remote, RemoteHostsAdapter

REPLICATION_ROLES: Tuple[str, ...] = ("master", "slave", "standalone")
"""tuple: list of valid replication roles."""
CORE_SECTIONS: Tuple[str, ...] = (
    "s1",
    "s2",
    "s3",
    "s4",
    "s5",
    "s6",
    "s7",
    "s8",
    "x1",
    "x2",
    "es4",
    "es5",
)
"""tuple: list of valid MySQL RW section names (external storage RO sections are not included here)."""
ACTIVE_ACTIVE_SECTIONS: Tuple[str] = ("x2",)
"""tuple: active/active sections that should not go read-only"""

logger = logging.getLogger(__name__)


class MysqlLegacyError(SpicerackError):
    """Custom exception class for errors of this module."""


class MysqlLegacyRemoteHosts(RemoteHostsAdapter):
    """Custom RemoteHosts class to execute MySQL queries."""

    def run_query(  # pylint: disable=too-many-arguments
        self,
        query: str,
        database: str = "",
        success_threshold: float = 1.0,
        batch_size: Optional[Union[int, str]] = None,
        batch_sleep: Optional[float] = None,
        is_safe: bool = False,
    ) -> Iterator[Tuple[NodeSet, MsgTreeElem]]:
        """Execute the query via Remote.

        Arguments:
            query (str): the mysql query to be executed. Double quotes must be already escaped.
            database (str, optional): an optional MySQL database to connect to before executing the query.
            success_threshold (float, optional): to consider the execution successful, must be between 0.0 and 1.0.
            batch_size (int, str, optional): the batch size for cumin, either as percentage (e.g. ``25%``) or absolute
                number (e.g. ``5``).
            batch_sleep (float, optional): the batch sleep in seconds to use in Cumin before scheduling the next host.
            is_safe (bool, optional): whether the command is safe to run also in dry-run mode because it's a read-only
                command that doesn't modify the state.

        Returns:
            generator: as returned by :py:meth:`cumin.transports.BaseWorker.get_results`.

        Raises:
            RemoteExecutionError: if the Cumin execution returns a non-zero exit code.

        """
        command = f'mysql --skip-ssl --skip-column-names --batch -e "{query}" {database}'.strip()
        return self._remote_hosts.run_sync(
            command,
            success_threshold=success_threshold,
            batch_size=batch_size,
            batch_sleep=batch_sleep,
            is_safe=is_safe,
        )


class MysqlLegacy:
    """Class to manage MySQL servers."""

    heartbeat_query = (
        "SELECT ts FROM heartbeat.heartbeat WHERE datacenter = '{dc}' and shard = '{section}' "
        "ORDER BY ts DESC LIMIT 1"
    )
    """str: Query pattern to check the heartbeat for a given datacenter and section."""

    def __init__(self, remote: Remote, dry_run: bool = True) -> None:
        """Initialize the instance.

        Arguments:
            remote (spicerack.remote.Remote): the Remote instance.
            dry_run (bool, optional): whether this is a DRY-RUN.

        """
        self._remote = remote
        self._dry_run = dry_run

    def get_dbs(self, query: str) -> MysqlLegacyRemoteHosts:
        """Get a MysqlLegacyRemoteHosts instance for the matching hosts.

        Arguments:
            query (str): the Remote query to use to fetch the DB hosts.

        Returns:
            spicerack.mysql_legacy.MysqlLegacyRemoteHosts: an instance with the remote targets.

        """
        return MysqlLegacyRemoteHosts(self._remote.query(query))

    def get_core_dbs(
        self,
        *,
        datacenter: Optional[str] = None,
        section: Optional[str] = None,
        replication_role: Optional[str] = None,
        excludes: Tuple[str, ...] = (),
    ) -> MysqlLegacyRemoteHosts:
        """Find the core databases matching the parameters.

        Arguments:
            datacenter (str, optional): the name of the datacenter to filter for, accepted values are those specified in
                :py:data:`spicerack.constants.CORE_DATACENTERS`.
            replication_role (str, optional): the repication role to filter for, accepted values are those specified in
                :py:data:`spicerack.mysql_legacy.REPLICATION_ROLES`.
            section (str, optional): a specific section to filter for, accepted values are those specified in
                :py:data:`spicerack.mysql_legacy.CORE_SECTIONS`.
            excludes (Tuple[str, ...]): sections to exclude from getting

        Raises:
            spicerack.mysql_legacy.MysqlLegacyError: on invalid data or unexpected matching hosts.

        Returns:
            spicerack.mysql_legacy.MysqlLegacyRemoteHosts: an instance with the remote targets.

        """
        query_parts = ["A:db-core"]
        dc_multipler = len(CORE_DATACENTERS)
        section_multiplier = len(CORE_SECTIONS)

        if datacenter is not None:
            dc_multipler = 1
            if datacenter not in CORE_DATACENTERS:
                raise MysqlLegacyError(f"Got invalid datacenter {datacenter}, accepted values are: {CORE_DATACENTERS}")

            query_parts.append("A:" + datacenter)

        for exclude in excludes:
            if exclude not in CORE_SECTIONS:
                raise MysqlLegacyError(f"Got invalid excludes {exclude}, accepted values are: {CORE_SECTIONS}")
            section_multiplier -= 1
            query_parts.append(f"not A:db-section-{exclude}")

        if section is not None:
            section_multiplier = 1
            if section not in CORE_SECTIONS:
                raise MysqlLegacyError(f"Got invalid section {section}, accepted values are: {CORE_SECTIONS}")

            query_parts.append(f"A:db-section-{section}")

        if replication_role is not None:
            if replication_role not in REPLICATION_ROLES:
                raise MysqlLegacyError(
                    f"Got invalid replication_role {replication_role}, accepted values are: {REPLICATION_ROLES}"
                )

            query_parts.append(f"A:db-role-{replication_role}")

        mysql_hosts = MysqlLegacyRemoteHosts(self._remote.query(" and ".join(query_parts)))

        # Sanity check of matched hosts in case of master selection
        if replication_role == "master" and len(mysql_hosts) != dc_multipler * section_multiplier:
            raise MysqlLegacyError(f"Matched {len(mysql_hosts)} masters, expected {dc_multipler * section_multiplier}")

        return mysql_hosts

    def set_core_masters_readonly(self, datacenter: str) -> None:
        """Set the core masters in read-only.

        Arguments:
            datacenter (str): the name of the datacenter to filter for.

        Raises:
            spicerack.remote.RemoteExecutionError: on Remote failures.
            spicerack.mysql_legacy.MysqlLegacyError: on failing to verify the modified value.

        """
        logger.debug("Setting core DB masters in %s to be read-only", datacenter)
        target = self.get_core_dbs(datacenter=datacenter, replication_role="master", excludes=ACTIVE_ACTIVE_SECTIONS)
        target.run_query("SET GLOBAL read_only=1")
        self.verify_core_masters_readonly(datacenter, True)

    def set_core_masters_readwrite(self, datacenter: str) -> None:
        """Set the core masters in read-write.

        Arguments:
            datacenter (str): the name of the datacenter to filter for.

        Raises:
            spicerack.remote.RemoteExecutionError: on Remote failures.
            spicerack.mysql_legacy.MysqlLegacyError: on failing to verify the modified value.

        """
        logger.debug("Setting core DB masters in %s to be read-write", datacenter)
        target = self.get_core_dbs(datacenter=datacenter, replication_role="master", excludes=ACTIVE_ACTIVE_SECTIONS)
        target.run_query("SET GLOBAL read_only=0")
        self.verify_core_masters_readonly(datacenter, False)

    def verify_core_masters_readonly(self, datacenter: str, is_read_only: bool) -> None:
        """Verify that the core masters are in read-only or read-write mode.

        Arguments:
            datacenter (str): the name of the datacenter to filter for.
            is_read_only (bool): whether the read-only mode should be set or not.

        Raises:
            spicerack.mysql_legacy.MysqlLegacyError: on failure.

        """
        logger.debug(
            "Verifying core DB masters in %s have read-only=%d",
            datacenter,
            is_read_only,
        )
        target = self.get_core_dbs(datacenter=datacenter, replication_role="master", excludes=ACTIVE_ACTIVE_SECTIONS)
        expected = str(int(is_read_only))  # Convert it to the returned value from MySQL: 1 or 0.
        failed = False

        for nodeset, output in target.run_query("SELECT @@global.read_only", is_safe=True):
            response = output.message().decode()
            if response != expected:
                logger.error(
                    "Expected output to be '%s', got '%s' for hosts %s",
                    expected,
                    response,
                    str(nodeset),
                )
                failed = True

        if failed and not self._dry_run:
            raise MysqlLegacyError(
                f"Verification failed that core DB masters in {datacenter} have read-only={is_read_only}"
            )

    def check_core_masters_in_sync(self, dc_from: str, dc_to: str) -> None:
        """Check that all core masters in dc_to are in sync with the core masters in dc_from.

        Arguments:
            dc_from (str): the name of the datacenter from where to get the master positions.
            dc_to (str): the name of the datacenter where to check that they are in sync.

        Raises:
            spicerack.remote.RemoteExecutionError: on failure.

        """
        logger.debug("Waiting for the core DB masters in %s to catch up", dc_to)
        heartbeats = self.get_core_masters_heartbeats(dc_from, dc_from)
        self.check_core_masters_heartbeats(dc_to, dc_from, heartbeats)

    def get_core_masters_heartbeats(self, datacenter: str, heartbeat_dc: str) -> Dict[str, datetime]:
        """Get the current heartbeat values from core DB masters in DC for a given heartbeat DC.

        Arguments:
            datacenter (str): the name of the datacenter from where to get the heartbeat values.
            heartbeat_dc (str): the name of the datacenter for which to filter the heartbeat query.

        Returns:
            dict: a dictionary with the section name :py:class:`str` as keys and their heartbeat
            :py:class:`datetime.datetime` as values. For example::

                {'s1': datetime.datetime(2018, 1, 2, 11, 22, 33, 123456)}

        Raises:
            spicerack.mysql_legacy.MysqlLegacyError: on failure to gather the heartbeat or convert it into a datetime.

        """
        heartbeats = {}
        for section in CORE_SECTIONS:
            core_dbs = self.get_core_dbs(datacenter=datacenter, section=section, replication_role="master")
            heartbeats[section] = MysqlLegacy._get_heartbeat(core_dbs, section, heartbeat_dc)

        return heartbeats

    def check_core_masters_heartbeats(
        self, datacenter: str, heartbeat_dc: str, heartbeats: Dict[str, datetime]
    ) -> None:
        """Check the current heartbeat values in the core DB masters in DC are in sync with the provided heartbeats.

        Arguments:
            datacenter (str): the name of the datacenter from where to get the heartbeat values.
            heartbeat_dc (str): the name of the datacenter for which to filter the heartbeat query.
            heartbeats (dict): a dictionary with the section name :py:class:`str` as keys and heartbeat
                :py:class:`datetime.datetime` for each core section as values.

        Raises:
            spicerack.mysql_legacy.MysqlLegacyError: on failure to gather the heartbeat or convert it into a datetime.

        """
        for section, heartbeat in heartbeats.items():
            self._check_core_master_in_sync(datacenter, heartbeat_dc, section, heartbeat)

    @retry(exceptions=(MysqlLegacyError,))
    def _check_core_master_in_sync(
        self,
        datacenter: str,
        heartbeat_dc: str,
        section: str,
        parent_heartbeat: datetime,
    ) -> None:
        """Check and retry that the heartbeat value in a core DB master in DC is in sync with the provided heartbeat.

        Arguments:
            datacenter (str): the name of the datacenter from where to get the heartbeat value.
            heartbeat_dc (str): the name of the datacenter for which to filter the heartbeat query.
            section (str): the section name from where to get the heartbeat value and filter the heartbeat query.
            master_heartbeat (datetime.datetime): the reference heartbeat from the parent master to use to verify this
                master is in sync with it.

        Raises:
            spicerack.mysql_legacy.MysqlLegacyError: on failure to gather the heartbeat or convert it into a datetime
                or not yet in sync.

        """
        core_dbs = self.get_core_dbs(datacenter=datacenter, section=section, replication_role="master")
        local_heartbeat = MysqlLegacy._get_heartbeat(core_dbs, section, heartbeat_dc)

        # The check requires that local_heartbeat is stricly greater than parent_heartbeat because heartbeat writes also
        # when the DB is in read-only mode and has a granularity of 1s (as of 2018-09), meaning that an event could have
        # been written after the last heartbeat but before the DB was set in read-only mode and that event could not
        # have been replicated, hence checking the next heartbeat to ensure they are in sync.
        if local_heartbeat <= parent_heartbeat:
            delta = (local_heartbeat - parent_heartbeat).total_seconds()
            raise MysqlLegacyError(
                f"Heartbeat from master {core_dbs} for section {section} not yet in sync: "
                f"{local_heartbeat} <= {parent_heartbeat} (delta={delta})"
            )

    @staticmethod
    def _get_heartbeat(mysql_hosts: MysqlLegacyRemoteHosts, section: str, heartbeat_dc: str) -> datetime:
        """Get the heartbeat from the remote host for a given DC.

        Arguments:
            mysql_hosts (spicerack.mysql_legacy.MysqlLegacyRemoteHosts): the instance for the target DB to query.
            section (str): the DB section for which to get the heartbeat.
            heartbeat_dc (str): the name of the datacenter for which to filter the heartbeat query.

        Returns:
            datetime.datetime: the converted heartbeat.

        Raises:
            spicerack.mysql_legacy.MysqlLegacyError: on failure to gather the heartbeat or convert it into a datetime.

        """
        query = MysqlLegacy.heartbeat_query.format(dc=heartbeat_dc, section=section)

        for _, output in mysql_hosts.run_query(query, is_safe=True):
            try:
                heartbeat_str = output.message().decode()
                heartbeat = datetime.strptime(heartbeat_str, "%Y-%m-%dT%H:%M:%S.%f")
                break
            except (TypeError, ValueError) as e:
                raise MysqlLegacyError(f"Unable to convert heartbeat '{heartbeat_str}' into datetime") from e
        else:
            raise MysqlLegacyError(f"Unable to get heartbeat from master {mysql_hosts} for section {section}")

        return heartbeat
