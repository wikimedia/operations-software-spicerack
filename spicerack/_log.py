"""Log module."""
import logging
from pathlib import Path
from typing import Optional

from wmflib.irc import SALSocketHandler

root_logger = logging.getLogger()
irc_logger = logging.getLogger("spicerack_irc_announce")


class FilterOutCumin(logging.Filter):
    """A logging output filter to filter out Cumin's logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Filter out Cumin's log messages.

        Arguments:
            record (logging.LogRecord):

        Returns:
            int: :py:data:`False` if the record should be filtered out, :py:data:`True` if it should be included.
            According to Python's logging interface, see: https://docs.python.org/3/library/logging.html#filter-objects

        """
        if record.name == "cumin" or record.name.startswith("cumin."):
            return False  # Filter it out

        return True


def setup_logging(
    base_path: Path,
    name: str,
    user: str,
    dry_run: bool = True,
    host: Optional[str] = None,
    port: int = 0,
) -> None:
    """Setup the root logger instance.

    Arguments:
        base_path (str, pathlib.Path): the base path where to save the logs.
        name (str): the name of log file to use without extension.
        user (str): the username for the IRC logging.
        dry_run (bool, optional): whether this is a dry-run.
        host (str, optional): the tcpircbot hostname for the IRC logging.
        port (int, optional): the tcpircbot port for the IRC logging.

    """
    base_path.mkdir(mode=0o755, parents=True, exist_ok=True)

    if dry_run:
        dry_run_prefix = "DRY-RUN "
    else:
        dry_run_prefix = ""

    # Default INFO logging
    formatter = logging.Formatter(fmt=f"%(asctime)s {dry_run_prefix}{user} %(process)d [%(levelname)s] %(message)s")
    handler = logging.FileHandler(base_path / f"{name}.log")
    handler.setFormatter(formatter)
    handler.setLevel(logging.INFO)

    # Extended logging for detailed debugging
    formatter_extended = logging.Formatter(
        fmt=(
            f"%(asctime)s {dry_run_prefix}{user} %(process)d [%(levelname)s %(filename)s:%(lineno)s in %(funcName)s] "
            "%(message)s"
        )
    )
    handler_extended = logging.FileHandler(base_path / f"{name}-extended.log")
    handler_extended.setFormatter(formatter_extended)
    handler_extended.setLevel(logging.DEBUG)

    # Stderr logging
    output_handler = logging.StreamHandler()
    if dry_run:
        output_handler.setFormatter(logging.Formatter(fmt="DRY-RUN: %(message)s"))
        output_handler.setLevel(logging.DEBUG)
    else:
        output_handler.setLevel(logging.INFO)
    output_handler.addFilter(FilterOutCumin())

    root_logger.addHandler(handler)
    root_logger.addHandler(handler_extended)
    root_logger.addHandler(output_handler)
    root_logger.setLevel(logging.DEBUG)

    if not dry_run and host is not None and port > 0:
        irc_logger.addHandler(SALSocketHandler(host, port, user))
        irc_logger.setLevel(logging.INFO)

    # Silence external noisy loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)

    # Elasticsearch lib is very noisy about HTTP level errors
    # ideally, we'd want to keep it at WARNING level for logs
    # sent to file, but ERROR for the console. Since this is
    # non trivial, let's raise level to ERROR for the moment.
    logging.getLogger("elasticsearch").setLevel(logging.ERROR)


def log_task_start(message: str) -> None:
    """Log the start of a task both on the logs and IRC.

    Arguments:
        message (str): the message to be logged.

    """
    irc_logger.info("START - %s", message)


def log_task_end(status: str, message: str) -> None:
    """Log the start of a task both on the logs and IRC.

    Arguments:
        status (str): the final status of the task.
        message (str): the message to be logged.

    """
    irc_logger.info("END (%s) - %s", status, message)
