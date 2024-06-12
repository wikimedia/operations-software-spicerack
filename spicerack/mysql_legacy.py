"""MySQL shell module."""  # noqa

import logging
import re
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any, Optional, Union

from ClusterShell.MsgTree import MsgTreeElem
from cumin import NodeSet
from wmflib.constants import CORE_DATACENTERS
from wmflib.interactive import ask_confirmation

from spicerack.decorators import retry
from spicerack.exceptions import SpicerackError
from spicerack.remote import Remote, RemoteHosts, RemoteHostsAdapter

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
    "es4",
    "es5",
)
"""Valid MySQL RW section names (external storage RO sections are not included here)."""

logger = logging.getLogger(__name__)


class MysqlLegacyError(SpicerackError):
    """Custom exception class for errors of this module."""


class MysqlLegacyReplagError(MysqlLegacyError):
    """Custom exception class for errors related to replag in this module."""


class InstanceBase:
    """Class to manage Single MariaDB Instances."""

    def __init__(self, host: RemoteHosts) -> None:
        """Initialize the instance.

        Arguments:
            host: the RemoteHosts instance that contains this MariaDB SingleInstance.

        """
        if len(host) > 1:
            msg = "InstanceBase and InstanceMulti are - yet - meant to be"
            msg = f"{msg} implemented with a single host in its private host attribute"
            raise NotImplementedError(msg)
        self.host: RemoteHosts = host
        self._primary: str = ""
        self.mysql: str = "mysql"
        self.sock: str = "/run/mysqld/mysqld.sock"
        self.service: str = "mariadb"
        self.data_dir: str = "/srv/sqldata"
        self._stop_mysql: str = f"systemctl stop {self.service}"
        self._start_mysql: str = f"systemctl start {self.service}"
        self._status_mysql: str = f"systemctl status {self.service}"
        self._restart_mysql: str = f"systemctl restart {self.service}"
        self._mysql_clean_data_dir: str = f"rm -rf {self.data_dir}"
        self._mysql_upgrade: str = "mysql_upgrade --force"

    def run_command(self, command: str) -> Iterator[tuple[NodeSet, MsgTreeElem]]:
        """Execute the command via Remote.

        Arguments:
            command: the mysql query to be executed. Double quotes must be already escaped.

        Raises:
            spicerack.remote.RemoteExecutionError: if the Cumin execution returns a non-zero exit code.

        """
        return self.host.run_sync(command)

    def run_query(self, query: str) -> Any:
        """Execute the query via Remote.

        Arguments:
            command: the mysql query to be executed. Double quotes must be already escaped.

        Raises:
            spicerack.remote.RemoteExecutionError: if the Cumin execution returns a non-zero exit code.

        """
        return self.host.run_sync(f'{self.mysql} -e "{query}"')

    def stop_slave(self) -> list:
        """Stops mariadb replication."""
        return self.run_query("STOP SLAVE;")

    def start_slave(self) -> list:
        """Starts mariadb replication."""
        return self.run_query("START SLAVE;")

    def show_slave_status(self) -> dict:
        """Returns the output of show slave status formatted as a dict."""
        result = {}
        rows: int = 0
        sql = "SHOW SLAVE STATUS\\G"
        response = self.run_query(sql)
        for line in list(response)[0][1].message().decode("utf8").splitlines():
            if "***************************" in line:
                rows += 1
                continue
            if rows > 1:
                raise NotImplementedError("Multimaster context, not implemented.")
            key, value = line.split(":", 2)
            result[key.strip()] = value.strip()
        return result

    def stop_mysql(self) -> Iterator[tuple[NodeSet, MsgTreeElem]]:
        """Stops mariadb service."""
        return self.run_command(self._stop_mysql)

    def status_mysql(self) -> Iterator[tuple[NodeSet, MsgTreeElem]]:
        """Stops mariadb service."""
        return self.run_command(self._status_mysql)

    def use_gtid(self) -> Iterator[tuple[NodeSet, MsgTreeElem]]:
        """Runs SQL to use GTID."""
        return self.run_command("CHANGE MASTER TO MASTER_USE_GTID=Slave_pos;")  # noqa E702,E231  # ignores ";"

    def start_mysql(self, skip_slave_start: bool = True) -> Iterator[tuple[NodeSet, MsgTreeElem]]:
        """Starts mariadb service."""
        if not skip_slave_start:
            # TODO double check that this would be the proper way
            self.run_command('systemctl set-environment MYSQLD_OPTS=""')
        return self.run_command(self._start_mysql)

    def restart_mysql(self) -> Iterator[tuple[NodeSet, MsgTreeElem]]:
        """Restarts mariadb service."""
        return self.run_command(self._restart_mysql)

    def clean_data_dir(self, no_confirm: bool = False) -> None:
        """Removes everything contained in the data directory."""
        if no_confirm:
            self.run_command(self._mysql_clean_data_dir)
        else:
            confmsg = f"This will run {self._mysql_clean_data_dir}, OK?"
            ask_confirmation(confmsg)
            self.run_command(self._mysql_clean_data_dir)

    def upgrade(self) -> Iterator[tuple[NodeSet, MsgTreeElem]]:
        """Runs the relevant mysql_upgrade command to upgrade the instance content."""
        return self.run_command(self._mysql_upgrade)

    def get_repl_info(self) -> tuple[str, str]:
        """Check replication status to send to the target node."""
        binlog_file: str = ""
        repl_position: str = ""
        replication_status = self.show_slave_status()
        binlog = replication_status["Master_Log_File"]
        pos = replication_status["Exec_Master_Log_Pos"]

        if not binlog or not pos:
            logger.error("Cloud not find the replication position aborting")
            raise RuntimeError
        binlog_file = binlog[0]
        repl_position = pos[0]
        msg = f"binlog_file: {binlog_file}, repl_position: {repl_position}"
        logger.debug(msg)
        return binlog_file, repl_position

    @property
    def primary(self) -> str:
        """Retrieves the replication source of this cluster."""
        if not self._primary:
            try:
                self._primary = self.show_slave_status()["Master_Host"]
            except KeyError as e:
                raise MysqlLegacyError("Unable to retrieve master host") from e
        return self._primary

    def prep_src_for_cloning(self) -> dict[str, str]:
        """Helper that prepares source instance to be cloned."""
        self.stop_slave()
        binlog_file, repl_position = self.get_repl_info()
        primary = self.primary
        self.stop_mysql()
        return {"binlog_file": binlog_file, "repl_position": repl_position, "primary": primary}

    def set_replication_parameters(
        self, binlog_file: str, repl_position: str, primary_host: str, user: str, password: str
    ) -> None:
        """Sets the replication parameters for the MySQL instance."""
        sql = (
            f"CHANGE MASTER TO master_host='{primary_host}', "
            f"master_port=3306, "
            f"master_ssl=1, master_log_file='{binlog_file}', "
            f"master_log_pos={repl_position}, master_user='{user}', "
            f"master_password='{password}';"  # noqa E702,E231  # ignores ";"
        )
        sql = sql.replace('"', '\\"')
        self.run_query(sql)

    def post_clone_reset_with_slave_stopped(self) -> None:
        """Prepares the MySQL instance for the first pooling operation."""
        self.run_command(f"chown -R mysql:mysql {self.data_dir}")
        self.run_command('systemctl set-environment MYSQLD_OPTS="--skip-slave-start"')
        self.start_mysql()
        self.stop_slave()
        self.run_query("RESET SLAVE ALL;")

    def post_asymmetrical_clone_fix(self, source_instance_data_dir: str, target_instance_data_dir: str) -> None:
        """Fixes issues after an asymmetrical clone operation."""
        self.run_command(f"mv {source_instance_data_dir}/* {target_instance_data_dir}")
        self.run_command(f"chown -R mysql:mysql {self.data_dir}")

    def resume_replication(self) -> None:
        """Resumes replication on the source MySQL instance."""
        self.run_command('systemctl set-environment MYSQLD_OPTS="--skip-slave-start"')
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
    def wait_for_replication(self) -> None:
        """Waits for replication to catch up."""
        replag = self.get_replication()
        if (replag is None) or (replag > 1.0):
            raise MysqlLegacyReplagError("Replag is still too high.")

    def get_replication(self) -> float:
        """Retrieves the current replication lag."""
        query = (
            "SELECT greatest(0, TIMESTAMPDIFF(MICROSECOND, max(ts), UTC_TIMESTAMP(6)) - 500000)/1000000"
            " FROM heartbeat.heartbeat"
            " ORDER BY ts LIMIT 1;"
        )
        query_res = self.run_query(query)
        query_res = query_res[0][1].message().decode("utf-8")
        replag = 1000.0
        for line in query_res.splitlines():
            if not line.strip():
                continue
            count = line.strip()
            try:
                count = float(count)
            except ValueError:
                continue
            replag = count
        return replag


class InstanceMulti(InstanceBase):
    """Class to manage Collocated (aka multiinstances) MariaDB Instances."""

    def __init__(self, host: RemoteHosts, instance_name: str = "") -> None:
        """Initialize the instance.

        Arguments:
            host: the RemoteHosts instance that contains this MariaDB MultiInstance.
            instance_name: The instance name you wish to identify this MultiInstance

        """
        super().__init__(host=host)
        self.instance_name = instance_name
        self.host = host  # noqa
        self.mysql = f"mysql -S {self.sock}"
        self.sock = f"/run/mysqld/mysqld.{self.instance_name}.sock"
        self.data_dir = f"/srv/sqldata.{self.instance_name}"
        self.service = f"mariadb@{self.instance_name}.service"
        self.mysql_upgrade = f"mysql_upgrade -S {self.sock} --force"  # noqa
        # here, noqa skips vulture: unused-attribute 'mysql_upgrade'


def convert_instancebase_to_instancemulti(instance: InstanceBase, instance_name: str) -> InstanceMulti:  # noqa
    """Converts InstanceBase to a named InstanceMulti."""
    converted_instance = InstanceMulti(host=instance.host, instance_name=instance_name)
    return converted_instance
    # here, noqa skips vulture: unused-attribute


def convert_instancemulti_to_instancebase(instance: InstanceMulti) -> InstanceBase:  # noqa
    """Converts InstanceMulti to InstanceBase."""
    converted_instance = InstanceBase(host=instance.host)
    return converted_instance
    # here, noqa skips vulture: unused-attribute


class MysqlLegacyRemoteHosts(RemoteHostsAdapter):
    """Custom RemoteHosts class for executing MySQL queries."""

    def __init__(self, remote_hosts: RemoteHosts) -> None:
        """Initialize the MysqlLegacyRemoteHosts.

        Arguments:
            remote_hosts: a list of remote hosts on which to operate.

        Raises:
            spicerack.remote.RemoteError: if no hosts were provided.

        """
        super().__init__(remote_hosts)
        # self._remote_hosts = remote_hosts
        self.instances: list = []  # noqa FIXME

    def run_query(  # pylint: disable=too-many-arguments
        self,
        query: str,
        database: str = "",
        success_threshold: float = 1.0,
        batch_size: Optional[Union[int, str]] = None,
        batch_sleep: Optional[float] = None,
        is_safe: bool = False,
    ) -> Iterator[tuple[NodeSet, MsgTreeElem]]:
        """Execute the query via Remote.

        Arguments:
            query: the mysql query to be executed. Double quotes must be already escaped.
            database: an optional MySQL database to connect to before executing the query.
            success_threshold: to consider the execution successful, must be between 0.0 and 1.0.
            batch_size: the batch size for cumin, either as percentage (e.g. ``25%``) or absolute number (e.g. ``5``).
            batch_sleep: the batch sleep in seconds to use in Cumin before scheduling the next host.
            is_safe: whether the command is safe to run also in dry-run mode because it's a read-only command that
                doesn't modify the state.

        Raises:
            spicerack.remote.RemoteExecutionError: if the Cumin execution returns a non-zero exit code.

        """
        command = f'mysql --skip-ssl --skip-column-names --batch -e "{query}" {database}'.strip()
        return self._remote_hosts.run_sync(
            command,
            success_threshold=success_threshold,
            batch_size=batch_size,
            batch_sleep=batch_sleep,
            is_safe=is_safe,
        )

    def list_host_instance(self, grouped: bool = False) -> list[InstanceBase]:
        """List MariaDB instances on the host.

        Arguments:
            grouped: whether we want to return a "normal" NodeSet which groups everything

        Raises:
            spicerack.remote.RemoteExecutionError: if the Cumin execution returns a non-zero exit code.
            NotImplementedError: if the replag is not fully caught on.

        """
        if len(self._remote_hosts) > 1:
            raise NotImplementedError("""Not implemented. We need to handle a single host at a time in this context.""")
        if not grouped:
            return self._list_host_instances_no_serial()

        # TODO see this comment:
        # https://gerrit.wikimedia.org/r/c/operations/software/spicerack/+/1005531/comment/7af929a5_6d6184d4/
        # we could use this method to parallelize stuff on instances as well.
        raise NotImplementedError(
            """Not implemented. We need to implement parallelization and grouping/degrouping before anything."""
        )

    def _list_host_instances_no_serial(self) -> list[InstanceBase]:
        """List MariaDB instances on the host.

        Raises:
            spicerack.remote.RemoteExecutionError: if the Cumin execution returns a non-zero exit code.

        """
        maria_multi_re = re.compile(r"mariadb@(\S+).service")
        # will not list EVERYTHING, but enough.
        trivial_systemctl_service_list = "systemctl --no-pager list-units 'mariadb*'"
        mariadb_instances: list[InstanceBase] = []
        service_list = self._remote_hosts.run_sync(trivial_systemctl_service_list, is_safe=True)
        for service in list(service_list)[0][1].message().decode("utf8").splitlines():
            if "mariadb@" in service and maria_multi_re.findall(service) != []:
                instance_name = maria_multi_re.findall(service)[0]
                if instance_name is not None:
                    mariadb_instances.append(InstanceMulti(host=self._remote_hosts, instance_name=instance_name))
        if len(mariadb_instances) > 0:
            return mariadb_instances
        return [InstanceBase(host=self._remote_hosts)]


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
