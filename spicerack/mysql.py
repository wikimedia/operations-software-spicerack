"""MySQL shell module."""

import logging
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from pathlib import Path
from time import sleep
from typing import Any, Optional, Union

from ClusterShell.MsgTree import MsgTreeElem
from cumin import NodeSet
from cumin.transports import Command
from pymysql.connections import Connection
from pymysql.cursors import DictCursor
from wmflib.constants import CORE_DATACENTERS
from wmflib.interactive import ask_confirmation

from spicerack.constants import WMF_CA_BUNDLE_PATH
from spicerack.decorators import retry
from spicerack.exceptions import SpicerackError
from spicerack.remote import Remote, RemoteExecutionError, RemoteHosts, RemoteHostsAdapter

REPLICATION_ROLES: tuple[str, ...] = ("master", "slave", "standalone")
"""Valid replication roles."""
CORE_SECTIONS: tuple[str, ...] = (
    "s6",
    "s5",
    "s2",
    "s7",
    "s3",
    "s8",
    "s4",
    "s1",
    "x1",
    "es6",
    "es7",
)
"""Valid MySQL RW core sections (external storage RO, parser cache, x2 and misc sections are not included here).
They are ordered from less impactful if anything goes wrong to most impactful.
"""

logger = logging.getLogger(__name__)


class MysqlError(SpicerackError):
    """Custom exception class for errors of this module."""


class MysqlReplagError(MysqlError):
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


class MysqlClient:
    """Connect to Mysql instances with a native Mysql client (pymysql).

    Caution:
        This class only has DRY-RUN support for DML sql operations.

    """

    def __init__(self, *, dry_run: bool = True) -> None:
        """Initialize the instance.

        Arguments:
            dry_run: whether this is a DRY-RUN.

        """
        self._dry_run = dry_run

    @contextmanager
    def connect(self, *, read_only: bool = False, **kwargs: Any) -> Generator:
        """Context-manager for a mysql connection to a remote host.

        Caution:
            Read-only support is limited to DML sql operations.

        Important:
            * By default autocommit is off and the commit of changes is the caller's responsibility.
            * The caller should also take care of rolling back transactions on error as appropriate.

        Arguments:
            read_only: True if this connection should use read-only transactions. **Note**: This parameter has no
                effect if DRY-RUN is set, it will be forced to True.
            **kwargs: Options passed directly to :py:class:`pymysql.connections.Connection`. If not set some settings
                will be set to default values:

                    * read_default_file: ``~/.my.cnf``. Set to :py:data:`None` to disable it.
                    * read_default_group: If not specified, it will be set to ``client`` or ``labsdbclient`` based on
                      the hostname.
                    * ssl: uses the puppet CA. Set to ``{}`` to disable.
                    * cursorclass: :py:class:`pymysql.cursors.DictCursor`

        Yields:
            :py:class:`pymysql.connections.Connection`: a context-managed mysql connection.

        Raises:
            pymysql.err.MySQLError: if unable to create the connection or set the connection to read only.

        """
        default_group = "client"
        if kwargs.get("host", "").startswith("clouddb"):
            default_group = "clientlabsdb"

        params: dict[str, Any] = {
            "charset": "utf8mb4",
            "cursorclass": DictCursor,
            "read_default_file": str(Path("~/.my.cnf").expanduser()),
            "read_default_group": default_group,
            "ssl": {"ca": WMF_CA_BUNDLE_PATH},
        }
        params.update(kwargs)

        conn = Connection(**params)

        if read_only or self._dry_run:
            # FIXME: read-only support is limited to DML sql statements.
            # https://phabricator.wikimedia.org/T254756 is needed to do this better.
            with conn.cursor() as cursor:
                _ = cursor.execute("SET SESSION TRANSACTION READ ONLY")

        try:
            yield conn
        # Not catching exceptions and rolling back, as that restricts the client code
        # in how it does error handling.
        finally:
            conn.close()


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
        self._mysql = MysqlClient(dry_run=host.dry_run)
        self._primary = ""
        self._mysql_bin = "/usr/local/bin/mysql"

        if self.name:
            self._sock = f"/run/mysqld/mysqld.{self.name}.sock"
            self._service = f"mariadb@{self.name}.service"
            self._data_dir = f"/srv/sqldata.{self.name}"
        else:
            self._sock = "/run/mysqld/mysqld.sock"
            self._service = "mariadb.service"
            self._data_dir = "/srv/sqldata"

    def __str__(self) -> str:
        """Return a string representation of the instance.

        Returns:
            the FQDN and name of the instance, when present.

        """
        name = self.name if self.name else "single-instance"
        return f"{self.host} ({name})"

    @contextmanager
    def cursor(self, **kwargs: Any) -> Generator:
        """Context manager to get an open connection and cursor against the current instance.

        Caution:
            DRY-RUN and read-only support is limited to DML sql operations.

        Examples:
            * Iterate directly the cursor
              ::

                >>> with instance.cursor(database="mydb") as (connection, cursor):
                >>>     count = cursor.execute("SELECT * FROM mytable WHERE a = %s and b = %s", ("value", 10))
                >>>     for row in cursor:
                >>>         # example row: {'a': 'value', 'b': 10, 'c': 1}
                >>>
                >>>     instance.check_warnings(cursor)

            * Get all the results
              ::

                >>> with instance.cursor(database="mydb") as (connection, cursor):
                >>>     count = cursor.execute("SELECT * FROM mytable WHERE a = %s and b = %s", ("value", 10))
                >>>     results = cursor.fetchall()
                >>>     instance.check_warnings(cursor)
                >>>
                >>> count
                2
                >>> results
                [{'a': 'value', 'b': 10, 'c': 1}, {'a': 'value', 'b': 10, 'c': 2}]

        Arguments:
            **kwargs: arbitrary arguments that are passed to the :py:class:`spicerack.mysql.MysqlClient.connect`
                method. See its documentation for the available arguments and their default values.

        Yields:
            A two-element tuple with the :py:class:`pymysql.connections.Connection` as first element and the cursor
            object as second element. The cursor object is one of :py:mod:`pymysql.cursors`.

        Raises:
            pymysql.err.MySQLError: or any more specific exception that inherits from this one on error.

        """
        # TODO: make the Instance class be aware of the port to use to connect to mysql, ideally allowing to use the
        # admin port if needed.
        kwargs["host"] = str(self.host)
        with self._mysql.connect(**kwargs) as connection:
            with connection.cursor() as cursor:
                yield connection, cursor

    def check_warnings(self, cursor: DictCursor) -> None:
        """It will check if there is any warning in the cursor for the last query and ask the user what to do.

        If any warning is found they will be logged to console and logfile and the user will be prompted what to do.

        Arguments:
            cursor: the cursor object with which the last query was made.

        """
        num_warnings = cursor.execute("SHOW WARNINGS")
        if not num_warnings:
            return

        warnings = cursor.fetchall()
        for warning in warnings:
            logger.warning("[%s] %s: %s", warning["Level"], warning["Code"], warning["Message"])

        ask_confirmation("The above warnings were raised during the last query, do you want to proceed anyway?")

    def execute(
        self,
        query: str,
        query_parameters: Union[None, tuple, list, dict] = None,
        *,
        is_safe: bool = False,
        **kwargs: Any,
    ) -> int:
        """Execute a query that returns no data without giving access to the connection or cursor objects.

        Caution:
            DRY-RUN and read-only support is limited to DML sql operations when ``is_safe`` is set to :py:data:`True`.

        Note:
            If any warning is issued by the database they will be logged and the user prompted what to do.

        Examples:
            ::

                >>> query = "INSERT INTO mytable VALUES (%(a)s, %(b)s)"
                >>> params = {"a": "value", "b": 10}
                >>> num_rows = instance.execute(query, params, database="mydb")

        Arguments:
            query: the query to execute, with eventual placeholders (``%s`` or ``%(name)s``).
            query_parameters: the query parameters to inject into the query, a :py:class:`tuple` or :py:class:`list` in
                case ``%s`` placeholders were used or a :py:class:`dict` in case ``%(name)s`` placeholders were used.
                Leave the default value :py:data:`None` if there are no placeholders in the query.
            is_safe: set to :py:data:`True` if the query can be safely run also in DRY-RUN mode. By default all queries
                are considered unsafe. If :py:data:`False` the query will not be run in DRY-RUN mode and the return
                value will be 0.
            **kwargs: arbitrary arguments that are passed to the :py:class:`spicerack.mysql.MysqlClient.connect`
                method. See its documentation for the available arguments and their default values.

        Returns:
            the number of affected rows.

        Raises:
            spicerack.mysql.MysqlError: if the query returned more than one row.
            pymysql.err.MySQLError: on query errors.

        """
        with self.cursor(**kwargs) as (_connection, cursor):
            if self.host.dry_run and not is_safe:
                effective_query = cursor.mogrify(query, query_parameters)
                logger.info("Would have executed on host %s the query: %s", self, effective_query)
                return 0

            num_rows = cursor.execute(query, query_parameters)
            self.check_warnings(cursor)
            return num_rows

    def fetch_one_row(
        self,
        query: str,
        query_parameters: Union[None, tuple, list, dict] = None,
        **kwargs: Any,
    ) -> dict:
        """Execute the given query and returns one row. It sets the connection as read only unless forced explicitly.

        Caution:
            DRY-RUN and read-only support is limited to DML sql operations. By default all queries are considered
            read-only due to the nature of the method (retrieve one row).

        Note:
            If any warning is issued by the database they will be logged and the user prompted what to do.

        Examples:
            ::

                >>> query = "SELECT * FROM mytable WHERE a = %(a)s and b = %(b)s"
                >>> params = {"a": "value", "b": 10}
                >>> row = instance.fetch_one_row(query, params, database="mydb")
                >>> row
                {'a': 'value', 'b': 10, 'c': 1}
                >>> row = instance.fetch_one_row("SELECT 1 WHERE 2 > 1", database="mydb")
                >>> row
                {}

        Arguments:
            query: the query to execute, with eventual placeholders (``%s`` or ``%(name)s``).
            query_parameters: the query parameters to inject into the query, a :py:class:`tuple` or :py:class:`list` in
                case ``%s`` placeholders were used or a :py:class:`dict` in case ``%(name)s`` placeholders were used.
                Leave the default value :py:data:`None` if there are no placeholders in the query.
            **kwargs: arbitrary arguments that are passed to the :py:class:`spicerack.mysql.MysqlClient.connect`
                method. See its documentation for the available arguments and their default values.

        Returns:
            the fetched row or :py:data:`None` if the query returned no rows.

        Raises:
            spicerack.mysql.MysqlError: if the query returned more than one row.
            pymysql.err.MySQLError: on query errors.

        """
        kwargs["read_only"] = kwargs.get("read_only", True)  # Set RO to true unless explicitly specified
        with self.cursor(**kwargs) as (_connection, cursor):
            num_rows = cursor.execute(query, query_parameters)
            if num_rows != 1:
                self.check_warnings(cursor)
                if num_rows == 0:
                    return {}

                raise MysqlError(f"Expected query to return zero or one row, got {num_rows} instead.")

            row = cursor.fetchone()
            self.check_warnings(cursor)

            return row

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
        command = f'{self._mysql_bin} --socket {self._sock} --batch --execute "{query}" {database}'.strip()
        kwargs.setdefault("print_progress_bars", False)
        kwargs.setdefault("print_output", False)
        try:
            return self.host.run_sync(command, **kwargs)
        except RemoteExecutionError as e:
            raise MysqlError(f"Failed to run '{query}' on {self.host}") from e

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
            According to :py:meth:`spicerack.mysql.Instance.run_query`.

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

    def is_running(self) -> bool:
        """Check if the systemd service for the instance is active and running.

        Returns:
            True if the service is active and running, False otherwise.

        """
        command = f"/usr/bin/systemctl show -p ActiveState -p SubState {self._service}"

        result = self.host.run_sync(command, is_safe=True)
        output = list(result)[0][1].message().decode("utf-8").strip()

        return "ActiveState=active" in output and "SubState=running" in output

    def stop_slave(self) -> None:
        """Stops mariadb replication."""
        self.execute("STOP SLAVE")

    def start_slave(self) -> None:
        """Starts mariadb replication and sleeps for 1 second afterwards."""
        self.execute("START SLAVE")
        sleep(1)

    def show_slave_status(self) -> dict:
        """Returns the output of show slave status formatted as a dict.

        Returns:
            the current slave status for the instance.

        """
        query = "SHOW SLAVE STATUS"
        with self.cursor() as (_connection, cursor):
            num_rows = cursor.execute(query)
            if not num_rows:
                raise MysqlError(f"{query} seems to have been executed on a master.")

            if num_rows > 1:
                raise NotImplementedError(f"Multisource setup are not implemented. Got {num_rows} rows.")

            return cursor.fetchone()

    def show_master_status(self) -> dict:
        """Returns the output of show master status formatted as a dict.

        Returns:
            the current master status for the instance.

        """
        query = "SHOW MASTER STATUS"
        status = self.fetch_one_row(query)
        if not status:
            raise MysqlError(f"{query} seems to have been executed on a host with binlog disabled.")

        return status

    def set_master_use_gtid(self, setting: MasterUseGTID) -> None:
        """Runs MASTER_USE_GTID with the given value."""
        if not isinstance(setting, MasterUseGTID):
            raise MysqlError(f"Only instances of MasterUseGTID are accepted, got: {type(setting)}")

        # Not using placeholder replacements ad MariaDB requires it to be a syntax word and raises if it's quoted
        self.execute(f"CHANGE MASTER TO MASTER_USE_GTID={setting.value}")

    def stop_mysql(self) -> Iterator[tuple[NodeSet, MsgTreeElem]]:
        """Stops mariadb service.

        Returns:
            The results of the remote status command.

        """
        return self.host.run_sync(f"/usr/bin/systemctl stop {self._service}")

    def status_mysql(self) -> Iterator[tuple[NodeSet, MsgTreeElem]]:
        """Stops mariadb service.

        Returns:
            The results of the remote status command. It does not raise on exit codes different from zero.

        """
        return self.host.run_sync(Command(f"/usr/bin/systemctl status {self._service}", ok_codes=[]), is_safe=True)

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
            raise MysqlError(f"Could not find the replication position: {info}")

        logger.debug("Replication info for %s: %s", self.host, info)
        return info

    @property
    def data_dir(self) -> str:
        """Get the data directory of this instance.

        Returns:
            the data directory path for mariadb for this specific instance.

        """
        return self._data_dir

    @property
    def socket(self) -> str:
        """Getter for the socket path of the instance.

        Returns:
            the instance specific socket path to use.

        """
        return self._sock

    @property
    def primary(self) -> str:
        """Retrieves the replication source of this cluster.

        Raises:
            spicerack.mysql.MysqlError: if unable to find the master host of the current instance.

        """
        if not self._primary:
            try:
                self._primary = self.show_slave_status()["Master_Host"]
            except (KeyError, MysqlError) as e:
                raise MysqlError("Unable to retrieve master host") from e

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
        self.execute(
            (
                "CHANGE MASTER TO master_host=%(primary)s, "
                "master_port=%(port)s, "
                "master_ssl=1, "
                "master_log_file=%(binlog)s, "
                "master_log_pos=%(position)s, "
                "master_user=%(user)s, "
                "master_password=%(password)s"
            ),
            {
                "primary": replication_info.primary,
                "port": replication_info.port,
                "binlog": replication_info.binlog,
                "position": replication_info.position,
                "user": user,
                "password": password,
            },
        )

    def post_clone_reset_with_slave_stopped(self) -> None:
        """Prepares the MySQL instance for the first pooling operation."""
        self.host.run_sync(
            f"chown -R mysql:mysql {self._data_dir}",
            '/usr/bin/systemctl set-environment MYSQLD_OPTS="--skip-slave-start"',
        )
        self.start_mysql()
        self.stop_slave()
        self.execute("RESET SLAVE ALL")

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
        exceptions=(MysqlReplagError,),
    )
    def wait_for_replication(self, threshold: Union[float, Decimal] = Decimal("1.0")) -> None:
        """Waits for replication to catch up.

        Arguments:
            threshold: the replication lag threshold in seconds under which the replication is considered in sync.

        Raises:
            spicerack.mysql.MysqlReplagError: if the replication lag is still too high after all the
                retries.

        """
        replag = self.replication_lag()
        if replag > threshold:
            raise MysqlReplagError(f"Replication lag higher than the threshold ({threshold}s): {replag}s")

    def replication_lag(self) -> Decimal:
        """Retrieves the current replication lag.

        Returns:
            The replication lag in seconds.

        Raises:
            spicerack.mysql.MysqlError: if no lag information is present or unable to parse the it.

        """
        query = (
            "SELECT greatest(0, TIMESTAMPDIFF(MICROSECOND, max(ts), UTC_TIMESTAMP(6)) - 500000)/1000000 AS lag "
            "FROM heartbeat ORDER BY ts LIMIT 1"
        )
        row = self.fetch_one_row(query, database="heartbeat")
        if not row:
            raise MysqlError("The replication lag query returned no data")

        if "lag" not in row or row["lag"] is None:
            raise MysqlError(f"Unable to get lag information from: {row}")

        return row["lag"]


class MysqlRemoteHosts(RemoteHostsAdapter):
    """Custom RemoteHosts class for executing MySQL queries."""

    def __iter__(self) -> Iterator["MysqlRemoteHosts"]:
        """Iterate over all remote hosts in this instance.

        Yields:
            spicerack.mysql.MysqlRemoteHosts: an new instance for each host.

        """
        yield from self.split(len(self))

    def split(self, n_slices: int) -> Iterator["MysqlRemoteHosts"]:
        """Split the current MySQL remote hosts instance into ``n_slices`` instances.

        Arguments:
            n_slices: the number of slices to slice the MySQL remote hosts into.

        Yields:
            spicerack.mysql.MysqlRemoteHosts: the instances for the subset of nodes.

        """
        for remote_hosts in self.remote_hosts.split(n_slices):
            yield MysqlRemoteHosts(remote_hosts)

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

        # First check for multi-instance configs
        conf_files = list(
            self._remote_hosts.run_sync(
                # Exclude non-readable directories to avoid spurious error messages, select only .cnf files and
                # print their name without the path.
                r'/usr/bin/find /etc ! -readable -prune -o -path "/etc/mysql/mysqld.conf.d/*.cnf" -printf "%f\n"',
                is_safe=True,
                print_output=False,
                print_progress_bars=False,
            )
        )
        if conf_files:  # Multi-instance
            for conf_file in conf_files[0][1].message().decode().splitlines():
                instances.append(Instance(self._remote_hosts, name=conf_file[:-4]))  # Remove .cnf extension
        else:  # Check for single instance
            try:
                self._remote_hosts.run_sync(
                    r"/usr/bin/grep -q '^\[mysqld\]$' '/etc/my.cnf'",
                    is_safe=True,
                    print_output=False,
                    print_progress_bars=False,
                )
                instances.append(Instance(self._remote_hosts))
            except RemoteExecutionError:  # No my.cnf or no mysqld section found - no instances present
                pass

        return instances


class Mysql:
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

    def get_dbs(self, query: str) -> MysqlRemoteHosts:
        """Get a MysqlRemoteHosts instance for the matching hosts.

        Arguments:
            query: the Remote query to use to fetch the DB hosts.

        """
        return MysqlRemoteHosts(self._remote.query(query))

    def get_core_dbs(
        self,
        *,
        datacenter: Optional[str] = None,
        section: Optional[str] = None,
        replication_role: Optional[str] = None,
        excludes: tuple[str, ...] = (),
    ) -> MysqlRemoteHosts:
        """Get an instance to operated on the core databases matching the parameters.

        Arguments:
            datacenter: the name of the datacenter to filter for, accepted values are those specified in
                :py:data:`spicerack.constants.CORE_DATACENTERS`.
            replication_role: the repication role to filter for, accepted values are those specified in
                :py:data:`spicerack.mysql.REPLICATION_ROLES`.
            section: a specific section to filter for, accepted values are those specified in
                :py:data:`spicerack.mysql.CORE_SECTIONS`.
            excludes: sections to exclude from getting.

        Raises:
            spicerack.mysql.MysqlError: on invalid data or unexpected matching hosts.

        """
        query_parts = ["A:db-core"]
        dc_multipler = len(CORE_DATACENTERS)
        section_multiplier = len(CORE_SECTIONS)

        if datacenter is not None:
            dc_multipler = 1
            if datacenter not in CORE_DATACENTERS:
                raise MysqlError(f"Got invalid datacenter {datacenter}, accepted values are: {CORE_DATACENTERS}")

            query_parts.append("A:" + datacenter)

        for exclude in excludes:
            if exclude not in CORE_SECTIONS:
                raise MysqlError(f"Got invalid excludes {exclude}, accepted values are: {CORE_SECTIONS}")
            section_multiplier -= 1
            query_parts.append(f"not A:db-section-{exclude}")

        if section is not None:
            section_multiplier = 1
            if section not in CORE_SECTIONS:
                raise MysqlError(f"Got invalid section {section}, accepted values are: {CORE_SECTIONS}")

            query_parts.append(f"A:db-section-{section}")

        if replication_role is not None:
            if replication_role not in REPLICATION_ROLES:
                raise MysqlError(
                    f"Got invalid replication_role {replication_role}, accepted values are: {REPLICATION_ROLES}"
                )

            query_parts.append(f"A:db-role-{replication_role}")

        mysql_hosts = MysqlRemoteHosts(self._remote.query(" and ".join(query_parts)))

        # Sanity check of matched hosts in case of master selection
        if replication_role == "master" and len(mysql_hosts) != dc_multipler * section_multiplier:
            raise MysqlError(f"Matched {len(mysql_hosts)} masters, expected {dc_multipler * section_multiplier}")

        return mysql_hosts

    def set_core_masters_readonly(self, datacenter: str) -> None:
        """Set the core masters in read-only.

        Arguments:
            datacenter: the name of the datacenter to filter for.

        Raises:
            spicerack.remote.RemoteExecutionError: on Remote failures.
            spicerack.mysql.MysqlError: on failing to verify the modified value.

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
            spicerack.mysql.MysqlError: on failing to verify the modified value.

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
            spicerack.mysql.MysqlError: on failure.

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
            raise MysqlError(f"Verification failed that core DB masters in {datacenter} have read-only={is_read_only}")

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
            spicerack.mysql.MysqlError: on failure to gather the heartbeat or convert it into a datetime.

        """
        heartbeats = {}
        for section in CORE_SECTIONS:
            core_dbs = self.get_core_dbs(datacenter=datacenter, section=section, replication_role="master")
            heartbeats[section] = Mysql._get_heartbeat(core_dbs, section, heartbeat_dc)

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
            spicerack.mysql.MysqlError: on failure to gather the heartbeat or convert it into a datetime.

        """
        for section, heartbeat in heartbeats.items():
            self._check_core_master_in_sync(datacenter, heartbeat_dc, section, heartbeat)

    @retry(exceptions=(MysqlError,))
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
            spicerack.mysql.MysqlError: on failure to gather the heartbeat or convert it into a datetime
                or not yet in sync.

        """
        core_dbs = self.get_core_dbs(datacenter=datacenter, section=section, replication_role="master")
        local_heartbeat = Mysql._get_heartbeat(core_dbs, section, heartbeat_dc)

        # The check requires that local_heartbeat is stricly greater than parent_heartbeat because heartbeat writes also
        # when the DB is in read-only mode and has a granularity of 1s (as of 2018-09), meaning that an event could have
        # been written after the last heartbeat but before the DB was set in read-only mode and that event could not
        # have been replicated, hence checking the next heartbeat to ensure they are in sync.
        if local_heartbeat <= parent_heartbeat:
            delta = (local_heartbeat - parent_heartbeat).total_seconds()
            raise MysqlError(
                f"Heartbeat from master {core_dbs} for section {section} not yet in sync: "
                f"{local_heartbeat} <= {parent_heartbeat} (delta={delta})"
            )

    @staticmethod
    def _get_heartbeat(mysql_hosts: MysqlRemoteHosts, section: str, heartbeat_dc: str) -> datetime:
        """Get the heartbeat from the remote host for a given DC.

        Arguments:
            mysql_hosts: the instance for the target DB to query.
            section: the DB section for which to get the heartbeat.
            heartbeat_dc: the name of the datacenter for which to filter the heartbeat query.

        Raises:
            spicerack.mysql.MysqlError: on failure to gather the heartbeat or convert it into a datetime.

        """
        query = Mysql.heartbeat_query.format(dc=heartbeat_dc, section=section)

        for _, output in mysql_hosts.run_query(query, is_safe=True):
            try:
                heartbeat_str = output.message().decode()
                heartbeat = datetime.strptime(heartbeat_str, "%Y-%m-%dT%H:%M:%S.%f")
                break
            except (TypeError, ValueError) as e:
                raise MysqlError(f"Unable to convert heartbeat '{heartbeat_str}' into datetime") from e
        else:
            raise MysqlError(f"Unable to get heartbeat from master {mysql_hosts} for section {section}")

        return heartbeat
