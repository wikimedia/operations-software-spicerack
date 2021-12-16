"""MySQL module (native)."""

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Generator, Optional

from pymysql.connections import Connection

from spicerack.constants import PUPPET_CA_PATH
from spicerack.exceptions import SpicerackError


class MysqlError(SpicerackError):
    """Custom exception class for errors of this module."""


class Mysql:
    """Class to manage MySQL servers.

    Caution:
        This class only has DRY-RUN support for DML sql operations.

    """

    def __init__(self, *, dry_run: bool = True) -> None:
        """Initialize the instance.

        Arguments:
            dry_run (bool, optional): whether this is a DRY-RUN.

        """
        self._dry_run = dry_run

    @contextmanager
    def connect(
        self,
        *,
        read_only: bool = False,
        charset: str = "utf8mb4",
        read_default_file: Optional[str] = "",
        read_default_group: Optional[str] = None,
        ssl: Optional[Dict] = None,
        **kwargs: Any
    ) -> Generator:
        """Context-manager for a mysql connection to a remote host.

        Caution:
            Read-only support is limited to DML sql operations.

        Important:
            - This does not commit changes, that is the caller's responsibility.
            - The caller should also take care of rolling back transactions on error
              as appropriate.

        Arguments:
            read_only (bool, optional): True if this connection should use read-only
                transactions. **Note**: This parameter has no effect if DRY-RUN is set.
            charset (str, optional): Query charset to use.
            read_default_file (str, optional): ``my.cnf``-format file to read from. Defaults
                to ``~/.my.cnf``. Set to :py:data:`None` to disable.
            read_default_group: Section of read_default_file to use. If not specified, it
                will be set based on the target hostname.
            ssl (dict, optional): SSL configuration to use. Defaults to using the
                puppet CA. Set to ``{}`` to disable.
            **kwargs: Options passed directly to :py:class:`pymysql.connections.Connection`.

        Yields:
            :py:class:`pymysql.connections.Connection`: a context-managed mysql connection.

        """
        # FIXME(kormat): read-only support is limited to DML sql statements.
        # https://phabricator.wikimedia.org/T254756 is needed to do this better.
        read_only = read_only or self._dry_run

        if read_default_file == "":
            read_default_file = str(Path("~/.my.cnf").expanduser())
        if read_default_file and not read_default_group:
            read_default_group = "client"
            if kwargs.get("host", "").startswith("labsdb"):
                read_default_group += "labsdb"
        if ssl is None:
            ssl = {"ca": PUPPET_CA_PATH}

        conn = Connection(
            charset=charset,
            read_default_file=read_default_file,
            read_default_group=read_default_group,
            ssl=ssl,
            **kwargs,
        )
        if read_only:
            conn.query("SET SESSION TRANSACTION READ ONLY")
        try:
            yield conn
        # Not catching exceptions and rolling back, as that restricts the client code
        # in how it does error handling.
        finally:
            conn.close()
