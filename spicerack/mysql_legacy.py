"""MySQL shell module."""

import logging
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from textwrap import dedent
from time import sleep
from typing import Any, Optional

from ClusterShell.MsgTree import MsgTreeElem
from cumin import NodeSet
from wmflib.constants import CORE_DATACENTERS
from wmflib.interactive import ask_confirmation

from spicerack.decorators import retry
from spicerack.exceptions import SpicerackError
from spicerack.remote import Remote, RemoteExecutionError, RemoteHosts, RemoteHostsAdapter

REPLICATION_ROLES: tuple[str, ...] = ("master", "slave", "standalone")
"""Valid replication roles."""
CORE_SECTIONS: tuple[str, ...] = (
    "s1",
    "s2",
    "s3",
    "s4",
    "s5",
    "s6",
    "s7",
    "s8",
    "x1",
    "es6",
    "es7",
)
"""Valid MySQL RW core sections (external storage RO, parser cache, x2 and misc sections are not included here)."""

logger = logging.getLogger(__name__)


class MysqlLegacyError(SpicerackError):
    """Custom exception class for errors of this module."""


class MysqlLegacyReplagError(MysqlLegacyError):
    """Custom exception class for errors related to replag in this module."""


# TODO: use StrEnum once on 3.11+
class MasterUseGTID(Enum):
    """Describe the possible values for the MASTER_USE_GTID option.

    See Also:
        https://mariadb.com/kb/en/change-master-to/#master_use_gtid

    """

    CURRENT_POS = "current_pos"
    """Replicate in GTID mode and use gtid_current_pos as the position to start downloading transactions."""
    SLAVE_POS = "slave_pos"
    """Replicate in GTID mode and use gtid_slave_pos as the position to start downloading transactions."""
    NO = "no"
    """Don't replicate in GTID mode."""


@dataclass
class ReplicationInfo:
    """Represent the minimum replication information needed to restore a replication from a given point.

    Arguments:
        primary: the FQDN of the primary host from where to replicate from.
        binlog: the binlog file to replicate from.
        position: the binlog position to replicate from.
        port: the port of the master from where to replicate from.

    """

    primary: str
    binlog: str
    position: int
    port: int


class Instance:
    """Class to manage MariaDB single intances and multiinstances."""

    def __init__(self, host: RemoteHosts, *, name: str = "") -> None:
        """Initialize the instance.

        Arguments:
            host: the RemoteHosts instance that contains this MariaDB SingleInstance.
            name: the name of the instance in a multiinstance context. Leave it empty for single instances.

        """
        if len(host) > 1:
            raise NotImplementedError("Only single hosts are currently supported. Got {len(host)}.")

        self.host = host
        self.name = name
        self._primary = ""
        self._mysql = "/usr/local/bin/mysql"

        if self.name:
            self._sock = f"/run/mysqld/mysqld.{self.name}.sock"
            self._service = f"mariadb@{self.name}.service"
            self._data_dir = f"/srv/sqldata.{self.name}"
        else:
            self._sock = "/run/mysqld/mysqld.sock"
            self._service = "mariadb.service"
            self._data_dir = "/srv/sqldata"

    def run_query(self, query: str, database: str = "", **kwargs: Any) -> Any:
        """Execute the query via Remote.

        Arguments:
            query: the mysql query to be executed. Double quotes must be already escaped.
            database: the optional database to use for the query execution.
            **kwargs: any additional argument is passed to :py:meth:`spicerack.remote.RemoteHosts.run_sync`. By default
                the ``print_progress_bars`` and ``print_output`` arguments are set to :py:data:`False`.

        Returns:
            The result of the remote command execution.

        Raises:
            spicerack.remote.RemoteExecutionError: if the query execution via SSH returns a non-zero exit code.

        """
        command = f'{self._mysql} --socket {self._sock} --batch --execute "{query}" {database}'.strip()
        kwargs.setdefault("print_progress_bars", False)
        kwargs.setdefault("print_output", False)
        try:
            return self.host.run_sync(command, **kwargs)
        except RemoteExecutionError as e:
            raise MysqlLegacyError(f"Failed to run '{query}' on {self.host}") from e

    def run_vertical_query(self, query: str, database: str = "", **kwargs: Any) -> list[dict[str, str]]:
        r"""Run a query with vertical output (terminating it with ``\G``) and parse its results.

        The ``\G`` at the end of the query is automatically added.
        Each returned row is converted to a dictionary with keys that are the column names and values that are
        the column values.

        Warning:
            The parsing of the output of queries from the CLI, even with vertical format (``\G``), is a very brittle
            operation that could fail or have misleading data, for example if any of the values queried are
            multi-lines. This could potentially happen also with a ``SHOW SLAVE STATUS`` query if the replication is
            broken and the last error contains a newline.

        Arguments:
            According to :py:meth:`spicerack.mysql_legacy.Instance.run_query`.

        Returns:
            the parsed query as a list of dictionaries, one per returned row.

        """
        response = list(self.run_query(rf"{query}\G", database, **kwargs))
        if not response:
            return []

        rows = []
        current: dict[str, str] = {}
        for line in response[0][1].message().decode("utf8").splitlines():
            if line.startswith("*" * 20) and f" row {'*' * 20}" in line:  # row separator
                if current:
                    rows.append(current)
                current = {}
                continue

            try:
                key, value = line.split(": ", 1)
            except ValueError:
                logger.error("Failed to parse into key/value for query '%s' this line: %s", query, line)
                continue

            current[key.lstrip()] = value

        if current:
            rows.append(current)

        return rows

    def stop_slave(self) -> None:
        """Stops mariadb replication."""
        self.run_query("STOP SLAVE")

    def start_slave(self) -> None:
        """Starts mariadb replication and sleeps for 1 second afterwards."""
        self.run_query("START SLAVE")
        sleep(1)

    def show_slave_status(self) -> dict:
        """Returns the output of show slave status formatted as a dict.

        Returns:
            the current slave status for the instance.

        """
        sql = "SHOW SLAVE STATUS"
        rows = self.run_vertical_query(sql, is_safe=True)
        if not rows:
            raise MysqlLegacyError(f"{sql} seems to have been executed on a master.")

        if len(rows) > 1:
            raise NotImplementedError(f"Multisource setup are not implemented. Got {len(rows)} rows.")

        return rows[0]  # Only one row at this point

    def show_master_status(self) -> dict:
        """Returns the output of show master status formatted as a dict.

        Returns:
            the current master status for the instance.

        """
        sql = "SHOW MASTER STATUS"
        rows = self.run_vertical_query(sql, is_safe=True)
        if not rows:
            raise MysqlLegacyError(f"{sql} seems to have been executed on a host with binlog disabled.")

        return rows[0]  # SHOW MASTER STATUS can return at most one row

    def set_master_use_gtid(self, setting: MasterUseGTID) -> None:
        """Runs MASTER_USE_GTID with the given value."""
        if not isinstance(setting, MasterUseGTID):
            raise MysqlLegacyError(f"Only instances of MasterUseGTID are accepted, got: {type(setting)}")

        self.run_query(f"CHANGE MASTER TO MASTER_USE_GTID={setting.value}")

    def stop_mysql(self) -> Iterator[tuple[NodeSet, MsgTreeElem]]:
        """Stops mariadb service.

        Returns:
            The results of the remote status command.

        """
        return self.host.run_sync(f"/usr/bin/systemctl stop {self._service}")

    def status_mysql(self) -> Iterator[tuple[NodeSet, MsgTreeElem]]:
        """Stops mariadb service.

        Returns:
            The results of the remote status command.

        """
        return self.host.run_sync(f"/usr/bin/systemctl status {self._service}", is_safe=True)

    def start_mysql(self) -> Iterator[tuple[NodeSet, MsgTreeElem]]:
        """Starts mariadb service.

        Returns:
            The results of the remote start command.

        """
        return self.host.run_sync(f"/usr/bin/systemctl start {self._service}", print_output=True)

    def restart_mysql(self) -> Iterator[tuple[NodeSet, MsgTreeElem]]:
        """Restarts mariadb service.

        Returns:
            The results of the remote restart command.

        """
        return self.host.run_sync(f"/usr/bin/systemctl restart {self._service}")

    def clean_data_dir(self, *, skip_confirmation: bool = False) -> None:
        """Removes everything contained in the data directory.

        Arguments:
            skip_confirmation: execute the operation without any user confirmation.

        """
        command = f"/usr/bin/rm -rf {self._data_dir}"
        if not skip_confirmation:
            ask_confirmation(f"ATTENTION: destructive action for {self.host}: {command}. Are you sure to proceed?")

        self.host.run_sync(command)

    def upgrade(self) -> Iterator[tuple[NodeSet, MsgTreeElem]]:
        """Runs the relevant mysql_upgrade command to upgrade the instance content.

        Returns:
            The results of the remote upgrade command.

        """
        command = f"$(readlink -f /usr/local/bin/mysql_upgrade) --socket {self._sock} --force"
        return self.host.run_sync(command, print_output=True)

    def get_replication_info(self) -> ReplicationInfo:
        """Get the replication information suitable to set a new node's replication.

        Returns:
            The replication information object, useful to setup a new instance's replication to resume from the same
            position.

        """
        replication_status = self.show_slave_status()
        info = ReplicationInfo(
            primary=replication_status.get("Master_Host", ""),
            binlog=replication_status.get("Master_Log_File", ""),
            position=int(replication_status.get("Exec_Master_Log_Pos", -1)),
            port=int(replication_status.get("Master_Port", -1)),
        )
        if not (info.primary and info.binlog and info.position > -1 and info.port > -1):
            raise MysqlLegacyError(f"Could not find the replication position: {info}")

        logger.debug("Replication info for %s: %s", self.host, info)
        return info

    @property
    def primary(self) -> str:
        """Retrieves the replication source of this cluster.

        Raises:
            spicerack.mysql_legacy.MysqlLegacyError: if unable to find the master host of the current instance.

        """
        if not self._primary:
            try:
                self._primary = self.show_slave_status()["Master_Host"]
            except (KeyError, MysqlLegacyError) as e:
                raise MysqlLegacyError("Unable to retrieve master host") from e

        return self._primary

    def prep_src_for_cloning(self) -> ReplicationInfo:
        """Helper that prepares source instance to be cloned.

        Returns:
            The replication information object, useful to setup a new instance's replication to resume from the same
            position.

        """
        self.stop_slave()
        replication_info = self.get_replication_info()
        self.stop_mysql()
        return replication_info

    def set_replication_parameters(self, *, replication_info: ReplicationInfo, user: str, password: str) -> None:
        """Sets the replication parameters for the MySQL instance."""
        query = f"""
            CHANGE MASTER TO master_host='{replication_info.primary}',
            master_port={replication_info.port},
            master_ssl=1,
            master_log_file='{replication_info.binlog}',
            master_log_pos={replication_info.position},
            master_user='{user}',
            master_password='{password}'
        """
        self.run_query(dedent(query).strip())

    def post_clone_reset_with_slave_stopped(self) -> None:
        """Prepares the MySQL instance for the first pooling operation."""
        self.host.run_sync(
            f"chown -R mysql:mysql {self._data_dir}",
            '/usr/bin/systemctl set-environment MYSQLD_OPTS="--skip-slave-start"',
        )
        self.start_mysql()
        self.stop_slave()
        self.run_query("RESET SLAVE ALL")

    def resume_replication(self) -> None:
        """Resumes replication on the source MySQL instance."""
        self.host.run_sync('/usr/bin/systemctl set-environment MYSQLD_OPTS="--skip-slave-start"')
        self.start_mysql()
        self.upgrade()
        self.restart_mysql()
        self.start_slave()

    @retry(
        tries=480,  # We allow up to 8 hours for replication lag to catch up
        delay=timedelta(seconds=60),
        backoff_mode="constant",
        exceptions=(MysqlLegacyReplagError,),
    )
    def wait_for_replication(self, threshold: float = 1.0) -> None:
        """Waits for replication to catch up.

        Arguments:
            threshold: the replication lag threshold in seconds under which the replication is considered in sync.

        Raises:
            spicerack.mysql_legacy.MysqlLegacyReplagError: if the replication lag is still too high after all the
                retries.

        """
        replag = self.replication_lag()
        if replag > threshold:
            raise MysqlLegacyReplagError(f"Replication lag higher than the threshold ({threshold}s): {replag}s")

    def replication_lag(self) -> float:
        """Retrieves the current replication lag.

        Returns:
            The replication lag in seconds.

        Raises:
            spicerack.mysql_legacy.MysqlLegacyError: if no lag information is present or unable to parse the it.

        """
        query = """
            SELECT greatest(0, TIMESTAMPDIFF(MICROSECOND, max(ts), UTC_TIMESTAMP(6)) - 500000)/1000000 AS lag
            FROM heartbeat.heartbeat
            ORDER BY ts LIMIT 1
        """
        query = dedent(query).strip()
        query_res = list(self.run_query(query, is_safe=True))
        if not query_res:
            raise MysqlLegacyError("Got no output from the replication lag query")

        output = ""
        try:
            output = query_res[0][1].message().decode("utf-8").splitlines()
            return float(output[1])
        except (IndexError, ValueError) as e:
            raise MysqlLegacyError(f"Unable to parse replication lag from: {output}") from e


class MysqlLegacyRemoteHosts(RemoteHostsAdapter):
    """Custom RemoteHosts class for executing MySQL queries."""

    # TODO merge this method with Instance.run_query()
    def run_query(self, query: str, database: str = "", **kwargs: Any) -> Iterator[tuple[NodeSet, MsgTreeElem]]:
        """Execute the query via Remote.

        Arguments:
            query: the mysql query to be executed. Double quotes must be already escaped.
            database: an optional MySQL database to connect to before executing the query.
            **kwargs: any additional argument is passed to :py:meth:`spicerack.remote.RemoteHosts.run_sync`. By default
                the ``print_progress_bars`` and ``print_output`` arguments are set to :py:data:`False`.

        Raises:
            spicerack.remote.RemoteExecutionError: if the Cumin execution returns a non-zero exit code.

        """
        command = f'/usr/local/bin/mysql --skip-ssl --skip-column-names --batch -e "{query}" {database}'.strip()
        kwargs.setdefault("print_progress_bars", False)
        kwargs.setdefault("print_output", False)
        return self._remote_hosts.run_sync(command, **kwargs)

    def list_hosts_instances(self, *, group: bool = False) -> list[Instance]:
        """List MariaDB instances on the host.

        Arguments:
            group: not yet implemented feature to allow parallelization.

        Raises:
            spicerack.remote.RemoteExecutionError: if the Cumin execution returns a non-zero exit code.
            NotImplementedError: if the replag is not fully caught on.

        """
        if len(self._remote_hosts) != 1:
            raise NotImplementedError("Only single host are supported at this time.")

        if group:
            # TODO see this comment:
            # https://gerrit.wikimedia.org/r/c/operations/software/spicerack/+/1005531/comment/7af929a5_6d6184d4/
            # we could use this method to parallelize stuff on instances as well.
            raise NotImplementedError("Grouping and parallelization are not supported at this time.")

        return self._list_host_instances()

    def _list_host_instances(self) -> list[Instance]:
        """List MariaDB instances on the host.

        Raises:
            spicerack.remote.RemoteExecutionError: if the Cumin execution returns a non-zero exit code.

        """
        instances: list[Instance] = []
        command = "/usr/bin/systemctl --no-pager --type=service --plain --no-legend  list-units 'mariadb*'"
        service_list = list(
            self._remote_hosts.run_sync(command, is_safe=True, print_progress_bars=False, print_output=False)
        )
        if not service_list:
            return instances

        services = service_list[0][1].message().decode("utf8").splitlines()
        if len(services) == 1 and services[0].split()[0] == "mariadb.service":
            instances.append(Instance(self._remote_hosts))
            return instances

        for service in services:
            service_name = service.split()[0]
            if service_name.startswith("mariadb@") and service_name.endswith(".service"):
                instances.append(Instance(self._remote_hosts, name=service_name[8:-8]))

        return instances


class MysqlLegacy:
    """Class to manage MySQL servers."""

    # FIXME this query could be replaced by the one in _get_replication() as it's the one used in monitoring
    heartbeat_query: str = (
        "SELECT ts FROM heartbeat.heartbeat WHERE datacenter = '{dc}' and shard = '{section}' "
        "ORDER BY ts DESC LIMIT 1"
    )
    """Query pattern to check the heartbeat for a given datacenter and section."""

    def __init__(self, remote: Remote, dry_run: bool = True) -> None:
        """Initialize the instance.

        Arguments:
            remote: the Remote instance.
            dry_run: whether this is a DRY-RUN.

        """
        self._remote = remote
        self._dry_run = dry_run

    def get_dbs(self, query: str) -> MysqlLegacyRemoteHosts:
        """Get a MysqlLegacyRemoteHosts instance for the matching hosts.

        Arguments:
            query: the Remote query to use to fetch the DB hosts.

        """
        return MysqlLegacyRemoteHosts(self._remote.query(query))

    def get_core_dbs(
        self,
        *,
        datacenter: Optional[str] = None,
        section: Optional[str] = None,
        replication_role: Optional[str] = None,
        excludes: tuple[str, ...] = (),
    ) -> MysqlLegacyRemoteHosts:
        """Get an instance to operated on the core databases matching the parameters.

        Arguments:
            datacenter: the name of the datacenter to filter for, accepted values are those specified in
                :py:data:`spicerack.constants.CORE_DATACENTERS`.
            replication_role: the repication role to filter for, accepted values are those specified in
                :py:data:`spicerack.mysql_legacy.REPLICATION_ROLES`.
            section: a specific section to filter for, accepted values are those specified in
                :py:data:`spicerack.mysql_legacy.CORE_SECTIONS`.
            excludes: sections to exclude from getting.

        Raises:
            spicerack.mysql_legacy.MysqlLegacyError: on invalid data or unexpected matching hosts.

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
            datacenter: the name of the datacenter to filter for.

        Raises:
            spicerack.remote.RemoteExecutionError: on Remote failures.
            spicerack.mysql_legacy.MysqlLegacyError: on failing to verify the modified value.

        """
        logger.debug("Setting core DB masters in %s to be read-only", datacenter)
        target = self.get_core_dbs(datacenter=datacenter, replication_role="master")
        target.run_query("SET GLOBAL read_only=1")
        self.verify_core_masters_readonly(datacenter, True)

    def set_core_masters_readwrite(self, datacenter: str) -> None:
        """Set the core masters in read-write.

        Arguments:
            datacenter: the name of the datacenter to filter for.

        Raises:
            spicerack.remote.RemoteExecutionError: on Remote failures.
            spicerack.mysql_legacy.MysqlLegacyError: on failing to verify the modified value.

        """
        logger.debug("Setting core DB masters in %s to be read-write", datacenter)
        target = self.get_core_dbs(datacenter=datacenter, replication_role="master")
        target.run_query("SET GLOBAL read_only=0")
        self.verify_core_masters_readonly(datacenter, False)

    def verify_core_masters_readonly(self, datacenter: str, is_read_only: bool) -> None:
        """Verify that the core masters are in read-only or read-write mode.

        Arguments:
            datacenter: the name of the datacenter to filter for.
            is_read_only: whether the read-only mode should be set or not.

        Raises:
            spicerack.mysql_legacy.MysqlLegacyError: on failure.

        """
        logger.debug(
            "Verifying core DB masters in %s have read-only=%d",
            datacenter,
            is_read_only,
        )
        target = self.get_core_dbs(datacenter=datacenter, replication_role="master")
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
            dc_from: the name of the datacenter from where to get the master positions.
            dc_to: the name of the datacenter where to check that they are in sync.

        Raises:
            spicerack.remote.RemoteExecutionError: on failure.

        """
        logger.debug("Waiting for the core DB masters in %s to catch up", dc_to)
        heartbeats = self.get_core_masters_heartbeats(dc_from, dc_from)
        self.check_core_masters_heartbeats(dc_to, dc_from, heartbeats)

    def get_core_masters_heartbeats(self, datacenter: str, heartbeat_dc: str) -> dict[str, datetime]:
        """Get the current heartbeat values from core DB masters in DC for a given heartbeat DC.

        Arguments:
            datacenter: the name of the datacenter from where to get the heartbeat values.
            heartbeat_dc: the name of the datacenter for which to filter the heartbeat query.

        Returns:
            A dictionary with the section name :py:class:`str` as keys and their heartbeat
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
        self, datacenter: str, heartbeat_dc: str, heartbeats: dict[str, datetime]
    ) -> None:
        """Check the current heartbeat values in the core DB masters in DC are in sync with the provided heartbeats.

        Arguments:
            datacenter: the name of the datacenter from where to get the heartbeat values.
            heartbeat_dc: the name of the datacenter for which to filter the heartbeat query.
            heartbeats: a dictionary with the section name :py:class:`str` as keys and heartbeat
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
            datacenter: the name of the datacenter from where to get the heartbeat value.
            heartbeat_dc: the name of the datacenter for which to filter the heartbeat query.
            section: the section name from where to get the heartbeat value and filter the heartbeat query.
            master_heartbeat: the reference heartbeat from the parent master to use to verify this master is in sync
                with it.

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
            mysql_hosts: the instance for the target DB to query.
            section: the DB section for which to get the heartbeat.
            heartbeat_dc: the name of the datacenter for which to filter the heartbeat query.

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
