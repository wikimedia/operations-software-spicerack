"""Interactive module tests."""
from unittest import mock

import pytest

from spicerack import interactive
from spicerack.exceptions import SpicerackError


@mock.patch('builtins.input')
def test_ask_confirmation_ok(mocked_input, capsys):
    """Calling ask_confirmation() should not raise if the correct answer is provided."""
    mocked_input.return_value = 'done'
    message = 'Test message'
    interactive.ask_confirmation(message)
    out, _ = capsys.readouterr()
    assert message in out


@mock.patch('builtins.input')
def test_ask_confirmation_ko(mocked_input, capsys):
    """Calling ask_confirmation() should raise if the correct answer is not provided."""
    mocked_input.return_value = 'invalid'
    message = 'Test message'
    with pytest.raises(SpicerackError, match='Too many invalid confirmation answers'):
        interactive.ask_confirmation(message)

    out, _ = capsys.readouterr()
    assert message in out
    assert out.count('Invalid response') == 3


def test_get_user_no_env(monkeypatch):
    """Calling get_user() if no env variable is set should return '-'."""
    monkeypatch.delenv('USER', raising=False)
    monkeypatch.delenv('SUDO_USER', raising=False)
    assert interactive.get_user() == '-'


def test_get_user_root(monkeypatch):
    """Calling get_user() when unable to detect the real user should return 'root'."""
    monkeypatch.setenv('USER', 'root')
    monkeypatch.delenv('SUDO_USER', raising=False)
    assert interactive.get_user() == 'root'


def test_get_user_ok(monkeypatch):
    """Calling get_user() from a normal user with sudo should return the user's name."""
    monkeypatch.setenv('USER', 'root')
    monkeypatch.setenv('SUDO_USER', 'user')
    assert interactive.get_user() == 'user'


@mock.patch('spicerack.interactive.os.isatty')
def test_ensure_shell_is_durable_interactive(mocked_isatty):
    """Should raise SpicerackError if in an interactive shell."""
    mocked_isatty.return_value = True
    with pytest.raises(SpicerackError, match='Must be run in non-interactive mode or inside a screen or tmux.'):
        interactive.ensure_shell_is_durable()

    assert mocked_isatty.called


@mock.patch('spicerack.interactive.os.isatty')
def test_ensure_shell_is_durable_non_interactive(mocked_isatty):
    """Should raise SpicerackError if in an interactive shell."""
    mocked_isatty.return_value = False
    interactive.ensure_shell_is_durable()
    assert mocked_isatty.called


@mock.patch('spicerack.interactive.os.isatty')
@pytest.mark.parametrize('env_name, env_value', (
    ('STY', '12345.pts-1.host'),
    ('TMUX', '/tmux-1001/default,12345,0'),
    ('TERM', 'screen-example'),
))
def test_ensure_shell_is_durable_sty(mocked_isatty, env_name, env_value, monkeypatch):
    """Should not raise if in an interactive shell with STY set, TMUX set or a screen-line TERM."""
    mocked_isatty.return_value = True
    monkeypatch.setenv(env_name, env_value)
    interactive.ensure_shell_is_durable()
    assert mocked_isatty.called
