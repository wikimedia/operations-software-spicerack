"""MySQL module (native)."""

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from pymysql.connections import Connection
from pymysql.cursors import DictCursor

from spicerack.constants import PUPPET_CA_PATH


class Mysql:
    """Class to manage MySQL servers.

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
                effect if DRY-RUN is set, it will be forces to True.
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
            "ssl": {"ca": PUPPET_CA_PATH},
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
