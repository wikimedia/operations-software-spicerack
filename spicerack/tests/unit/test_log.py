"""Interactive module tests."""
import logging
import os
import uuid

from unittest import mock

from spicerack import log
from spicerack.tests import require_caplog


GENERIC_LOG_RECORD = logging.LogRecord('module', logging.DEBUG, '/source/file.py', 1, 'message', [], None)
CUMIN_LOG_RECORD = logging.LogRecord('cumin.module', logging.DEBUG, '/cumin/source/file.py', 1, 'message', [], None)
logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


def _assert_match_in_tmpdir(match, tmp_dir):
    """Given a match string, assert that it's present in all files in tmp_dir."""
    tmp_dir = str(tmp_dir)  # Newer versions pass a LocalPath, older a string.
    for logfile in os.listdir(tmp_dir):
        with open(os.path.join(tmp_dir, logfile), 'r') as f:
            assert match in f.read()


def test_irc_socket_handler_init():
    """An instance of IRCSocketHandler should set the address for the socket and the user."""
    handler = log.IRCSocketHandler('host', 123, 'user')
    assert handler.addr == ('host', 123)
    assert handler.username == 'user'


@mock.patch('spicerack.log.socket')
def test_irc_socket_handler_emit_ok(mocked_socket):
    """Calling emit() on an IRCSocketHandler instance should send the message to the socket."""
    handler = log.IRCSocketHandler('host', 123, 'user')

    handler.emit(GENERIC_LOG_RECORD)

    mocked_socket.assert_has_calls([
        mock.call.socket().connect(('host', 123)), mock.call.socket().close()], any_order=True)


@mock.patch('spicerack.log.socket')
def test_irc_socket_handler_emit_ko(mocked_socket):
    """If an error occur while calling emit() on an IRCSocketHandler instance, it should call ."""
    handler = log.IRCSocketHandler('host', 123, 'user')
    handler.handleError = mock.MagicMock()
    mocked_socket.socket.side_effect = OSError

    handler.emit(GENERIC_LOG_RECORD)

    assert mock.call.socket().connect(('host', 123)) not in mocked_socket.mock_calls
    assert mock.call.socket().close() not in mocked_socket.mock_calls
    handler.handleError.assert_called_once_with(GENERIC_LOG_RECORD)


def test_cumin_filter_pass():
    """The FilterOutCumin filter() method should let a normal log record pass."""
    log_filter = log.FilterOutCumin()
    ret = log_filter.filter(GENERIC_LOG_RECORD)
    assert ret == 1


def test_cumin_filter_blocks_cumin():
    """The FilterOutCumin filter() method should block a Cumin's log record."""
    log_filter = log.FilterOutCumin()
    ret = log_filter.filter(CUMIN_LOG_RECORD)
    assert ret == 0


@require_caplog
def test_setup_logging_no_irc(tmpdir, caplog):
    """Calling setup_logging() should setup all the handlers of the root logger."""
    log.setup_logging(tmpdir.strpath, 'task', 'user')
    message = str(uuid.uuid4())
    logger.info(message)
    assert message in caplog.text
    _assert_match_in_tmpdir(message, tmpdir.strpath)


@require_caplog
@mock.patch('spicerack.log.socket')
def test_setup_logging_with_irc(mocked_socket, tmpdir, caplog):
    """Calling setup_logging() with host and port should also setup the IRC logger."""
    log.setup_logging(tmpdir.strpath, 'task', 'user', host='host', port=123, dry_run=False)
    message = str(uuid.uuid4())
    log.irc_logger.info(message)

    assert mock.call.socket().connect(('host', 123)) in mocked_socket.mock_calls
    assert message in caplog.text
    _assert_match_in_tmpdir(message, tmpdir.strpath)


@require_caplog
def test_setup_logging_dry_run(capsys, tmpdir, caplog):
    """Calling setup_logging() when in dry run mode should setup all the handlers and the stdout with DEBUG level."""
    log.setup_logging(tmpdir.strpath, 'task', 'user', dry_run=True)
    message = str(uuid.uuid4())
    logger.info(message)

    _, err = capsys.readouterr()
    assert message in err
    assert 'DRY-RUN' in err
    assert message in caplog.text
    _assert_match_in_tmpdir(message, tmpdir.strpath)


@require_caplog
def test_log_task_start(capsys, tmpdir, caplog):
    """Calling log_task_start() should log a START message for the task to both loggers."""
    log.setup_logging(tmpdir.strpath, 'task', 'user')
    message = str(uuid.uuid4())
    log.log_task_start(message)

    logged_message = 'START - ' + message
    _, err = capsys.readouterr()
    assert logged_message in err
    assert logged_message in caplog.text
    _assert_match_in_tmpdir(logged_message, tmpdir.strpath)


@require_caplog
def test_log_task_start_dry_run(capsys, tmpdir, caplog):
    """Calling log_task_start() in dry-run mode should not print a START message for the task to the IRC logger."""
    log.setup_logging(tmpdir.strpath, 'task', 'user', dry_run=True)
    message = str(uuid.uuid4())
    log.log_task_start(message)

    logged_message = 'START - ' + message
    _, err = capsys.readouterr()
    assert logged_message in err
    assert logged_message in caplog.text
    _assert_match_in_tmpdir(logged_message, tmpdir.strpath)


@require_caplog
def test_log_task_end(capsys, tmpdir, caplog):
    """Calling log_task_end() should print an END message for the task."""
    log.setup_logging(tmpdir.strpath, 'task', 'user', dry_run=False)
    message = str(uuid.uuid4())
    log.log_task_end('success', message)

    logged_message = 'END (success) - ' + message
    _, err = capsys.readouterr()
    assert logged_message in err
    assert logged_message in caplog.text
    _assert_match_in_tmpdir(logged_message, tmpdir.strpath)
