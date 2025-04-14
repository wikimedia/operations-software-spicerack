"""Interactive module tests."""

import logging
import uuid
from pathlib import Path
from unittest import mock

import pytest
from wmflib import interactive

from spicerack import _log as log

GENERIC_LOG_RECORD = logging.LogRecord("module", logging.DEBUG, "/source/file.py", 1, "message", [], None)
CUMIN_LOG_RECORD = logging.LogRecord("cumin.module", logging.DEBUG, "/cumin/source/file.py", 1, "message", [], None)
logger = logging.getLogger(__name__)


def reset_logging_module():
    """Reset the logging module removing all handlers and filters."""
    for log_logger in (log.root_logger, log.irc_logger, log.sal_logger):
        list(map(log_logger.removeHandler, log_logger.handlers))
        list(map(log_logger.removeFilter, log_logger.filters))

    for handler in log.notify_logger.handlers:
        if not isinstance(handler, logging.NullHandler):
            log.notify_logger.removeHandler(handler)


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


class TestLogModule:
    """Test class for the _log module."""

    def setup_method(self):
        """Initialize the test method."""
        # pylint: disable=attribute-defined-outside-init
        self.message = str(uuid.uuid4())

    def teardown_method(self):
        """Reset python's logging module."""
        reset_logging_module()

    def _assert_match_in_tmpdir(self, match, tmp_dir, negate=False):
        """Given a match string, assert that it's present in all files in tmp_dir."""
        tmp_dir = Path(tmp_dir)  # Newer versions pass a LocalPath, older a string.
        for logfile in tmp_dir.iterdir():
            content = (tmp_dir / logfile).read_text()
            if negate:
                assert match not in content
            else:
                assert match in content

    def test_setup_logging_no_irc(self, tmpdir, caplog):
        """Calling setup_logging() should setup all the handlers of the root logger."""
        log.setup_logging(Path(tmpdir.strpath), "task", "user")
        logger.info(self.message)
        assert self.message in caplog.text
        self._assert_match_in_tmpdir(self.message, tmpdir.strpath)

    @mock.patch("wmflib.irc.socket")
    def test_setup_logging_with_irc(self, mocked_socket, tmpdir, caplog):
        """Calling setup_logging() with host and port should also setup the IRC loggers."""
        log.setup_logging(Path(tmpdir.strpath), "task", "user", dry_run=False, host="host", port=123)
        irc_message = self.message
        sal_message = str(uuid.uuid4())
        log.irc_logger.info(irc_message)
        log.sal_logger.info(sal_message)

        assert mock.call.socket().connect(("host", 123)) in mocked_socket.mock_calls
        assert irc_message in caplog.text
        assert sal_message in caplog.text
        self._assert_match_in_tmpdir(irc_message, tmpdir.strpath)
        self._assert_match_in_tmpdir(sal_message, tmpdir.strpath)

    def test_setup_logging_dry_run(self, capsys, tmpdir, caplog):
        """Calling setup_logging() when in dry run mode should setup all the handlers and the stdout in DEBUG."""
        log.setup_logging(Path(tmpdir.strpath), "task", "user")
        logger.info(self.message)

        _, err = capsys.readouterr()
        assert self.message in err
        assert "DRY-RUN" in err
        assert self.message in caplog.text
        self._assert_match_in_tmpdir(self.message, tmpdir.strpath)
        self._assert_match_in_tmpdir("DRY-RUN", tmpdir.strpath)

    @pytest.mark.parametrize("notify_logger_enabled", (True, False))
    @mock.patch("wmflib.interactive.NOTIFY_AFTER_SECONDS", 0.0)
    @mock.patch("builtins.input", return_value="go")
    @mock.patch("wmflib.interactive.sys.stdout.isatty", return_value=True)
    @mock.patch("wmflib.irc.socket.socket")
    def test_setup_logging_notify_logger_on(  # pylint: disable=too-many-positional-arguments,too-many-arguments
        self, mocked_socket, mocked_isatty, mocked_input, notify_logger_enabled, capsys, tmpdir, caplog
    ):
        """It should setup the wmflib's notify_logger based on the related parameter."""
        log.setup_logging(
            Path(tmpdir.strpath),
            "task",
            "user",
            dry_run=False,
            host="host",
            port=123,
            notify_logger_enabled=notify_logger_enabled,
        )
        awaiting = "is awaiting input"

        interactive.ask_confirmation(self.message)

        out, err = capsys.readouterr()
        assert self.message in out
        assert awaiting not in out
        assert self.message not in err
        assert awaiting not in err
        assert self.message not in caplog.text
        assert awaiting not in caplog.text
        self._assert_match_in_tmpdir(self.message, tmpdir.strpath, negate=True)
        mocked_isatty.assert_called_once_with()
        mocked_input.assert_called_once_with("> ")

        if notify_logger_enabled:
            mocked_socket.assert_called()
            sendall = mocked_socket.return_value.sendall
            sendall.assert_called_once()
            assert awaiting.encode() in sendall.call_args.args[0]
        else:
            mocked_socket.assert_not_called()

    @pytest.mark.parametrize("skip_start_sal", (True, False))
    @mock.patch("wmflib.irc.socket.socket")
    def test_log_task_start(self, mocked_socket, skip_start_sal, capsys, tmpdir, caplog):
        """Calling log_task_start() should log a START message for the task to both loggers based on skip_start_sal."""
        log.setup_logging(Path(tmpdir.strpath), "task", "user", dry_run=False, host="host", port=123)
        log.log_task_start(skip_start_sal=skip_start_sal, message=self.message)

        logged_message = f"START - {self.message}"
        _, err = capsys.readouterr()
        assert logged_message in err
        assert logged_message in caplog.text
        self._assert_match_in_tmpdir(logged_message, tmpdir.strpath)
        if skip_start_sal:
            mocked_socket.assert_not_called()
        else:
            sendall = mocked_socket.return_value.sendall
            sendall.assert_called_once()
            assert logged_message.encode() in sendall.call_args.args[0]

    @pytest.mark.parametrize("skip_start_sal", (True, False))
    @mock.patch("wmflib.irc.socket.socket")
    def test_log_task_start_dry_run(self, mocked_socket, skip_start_sal, capsys, tmpdir, caplog):
        """Calling log_task_start() in dry-run mode should not print a START message for the task to the IRC logger."""
        log.setup_logging(Path(tmpdir.strpath), "task", "user", host="host", port=123)
        log.log_task_start(skip_start_sal=skip_start_sal, message=self.message)

        logged_message = f"START - {self.message}"
        _, err = capsys.readouterr()
        assert logged_message in err
        assert logged_message in caplog.text
        self._assert_match_in_tmpdir(logged_message, tmpdir.strpath)
        self._assert_match_in_tmpdir("DRY-RUN", tmpdir.strpath)
        mocked_socket.assert_not_called()

    @pytest.mark.parametrize("skip_start_sal", (True, False))
    @mock.patch("wmflib.irc.socket.socket")
    def test_log_task_end(self, mocked_socket, skip_start_sal, capsys, tmpdir, caplog):
        """Calling log_task_end() should print an END or DONE message for the task."""
        log.setup_logging(Path(tmpdir.strpath), "task", "user", dry_run=False, host="host", port=123)
        log.log_task_end(skip_start_sal=skip_start_sal, status="success", message=self.message)

        if skip_start_sal:
            prefix = "DONE"
        else:
            prefix = "END"

        logged_message = f"{prefix} (success) - {self.message}"
        _, err = capsys.readouterr()
        assert logged_message in err
        assert logged_message in caplog.text
        self._assert_match_in_tmpdir(logged_message, tmpdir.strpath)
        sendall = mocked_socket.return_value.sendall
        sendall.assert_called_once()
        assert logged_message.encode() in sendall.call_args.args[0]
