"""Log module."""
import logging
import os
import socket


root_logger = logging.getLogger()  # pylint: disable=invalid-name
irc_logger = logging.getLogger('spicerack_irc_announce')  # pylint: disable=invalid-name


class IRCSocketHandler(logging.Handler):
    """Log handler for logmsgbot on #wikimedia-operation.

    Sends log events to a tcpircbot server for relay to an IRC channel.
    """

    def __init__(self, host, port, username):
        """Initialize the IRC socket handler.

        Arguments:
            host (str): tcpircbot hostname.
            port (int): tcpircbot listening port.
            username (str): the user to refer in the IRC messages.
        """
        super().__init__()
        self.addr = (host, port)
        self.username = username
        self.level = logging.INFO

    def emit(self, record):
        """According to Python logging.Handler interface.

        See https://docs.python.org/3/library/logging.html#handler-objects
        """
        message = '!log {msg} ({user}@{host})'.format(
            msg=record.getMessage(), user=self.username, host=socket.gethostname())
        sock = None

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1.0)
            sock.connect(self.addr)
            sock.sendall(message.encode('utf-8'))
        except OSError:
            self.handleError(record)
        finally:
            if sock is not None:
                sock.close()


class FilterOutCumin(logging.Filter):
    """A logging output filter to filter out Cumin's logs."""

    def filter(self, record):
        """Filter out Cumin's log messages.

        Arguments:
            record (logging.LogRecord):

        Returns:
            int: 0 if the record should be filtered out, non-zero if it should be included. According to Python's
            logging interface, see: https://docs.python.org/3/library/logging.html#filter-objects

        """
        if record.name == 'cumin' or record.name.startswith('cumin.'):
            return 0  # Filter it out

        return 1


def setup_logging(base_path, name, user, dry_run=True, host=None, port=0):
    """Setup the root logger instance.

    Arguments:
        base_path (str, path-like object): the base path where to save the logs.
        name (str): the name of log file to use without extension.
        dry_run (bool, optional): whether this is a dry-run.
        host (str, optional): the tcpircbot hostname for the IRC logging.
        port (int, optional): the tcpircbot port for the IRC logging.
    """
    base_path = str(base_path)  # Since Python 3.6 it could be a path-like object
    os.makedirs(base_path, mode=0o755, exist_ok=True)

    # Default INFO logging
    formatter = logging.Formatter(fmt='%(asctime)s [%(levelname)s] %(message)s')
    handler = logging.FileHandler(os.path.join(base_path, '{name}.log'.format(name=name)))
    handler.setFormatter(formatter)
    handler.setLevel(logging.INFO)

    # Extended logging for detailed debugging
    formatter_extended = logging.Formatter(
        fmt='%(asctime)s [%(levelname)s %(filename)s:%(lineno)s in %(funcName)s] %(message)s')
    handler_extended = logging.FileHandler(os.path.join(base_path, '{name}-extended.log'.format(name=name)))
    handler_extended.setFormatter(formatter_extended)
    handler_extended.setLevel(logging.DEBUG)

    # Stderr logging
    output_handler = logging.StreamHandler()
    if dry_run:
        output_handler.setFormatter(logging.Formatter(fmt='DRY-RUN: %(message)s'))
        output_handler.setLevel(logging.DEBUG)
    else:
        output_handler.setLevel(logging.INFO)
    output_handler.addFilter(FilterOutCumin())

    root_logger.addHandler(handler)
    root_logger.addHandler(handler_extended)
    root_logger.addHandler(output_handler)
    root_logger.raiseExceptions = False
    root_logger.setLevel(logging.DEBUG)

    if not dry_run and host is not None and port > 0:
        irc_logger.addHandler(IRCSocketHandler(host, port, user))
        irc_logger.setLevel(logging.INFO)

    # Silence external noisy loggers
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)


def log_task_start(message):
    """Log the start of a task both on the logs and IRC.

    Arguments:
        message (str): the message to be logged.
    """
    irc_logger.info('START - %s', message)


def log_task_end(status, message):
    """Log the start of a task both on the logs and IRC.

    Arguments:
        status (str): the final status of the task.
        message (str): the message to be logged.
    """
    irc_logger.info('END (%s) - %s', status, message)
