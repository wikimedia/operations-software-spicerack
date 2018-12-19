"""Interactive module tests."""
from unittest import mock

import pytest

from spicerack import interactive
from spicerack.exceptions import SpicerackError


@mock.patch('builtins.input')
@mock.patch('spicerack.interactive.sys.stdout.isatty')
def test_ask_confirmation_ok(mocked_isatty, mocked_input, capsys):
    """Calling ask_confirmation() should not raise if the correct answer is provided."""
    mocked_isatty.return_value = True
    mocked_input.return_value = 'done'
    message = 'Test message'
    interactive.ask_confirmation(message)
    out, _ = capsys.readouterr()
    assert message in out


@mock.patch('builtins.input')
@mock.patch('spicerack.interactive.sys.stdout.isatty')
def test_ask_confirmation_ko(mocked_isatty, mocked_input, capsys):
    """Calling ask_confirmation() should raise if the correct answer is not provided."""
    mocked_isatty.return_value = True
    mocked_input.return_value = 'invalid'
    message = 'Test message'
    with pytest.raises(SpicerackError, match='Too many invalid confirmation answers'):
        interactive.ask_confirmation(message)

    out, _ = capsys.readouterr()
    assert message in out
    assert out.count('Invalid response') == 3


@mock.patch('spicerack.interactive.sys.stdout.isatty')
def test_ask_confirmation_no_tty(mocked_isatty):
    """It should raise SpicerackError if not in a TTY."""
    mocked_isatty.return_value = False
    with pytest.raises(SpicerackError, match='Not in a TTY, unable to ask for confirmation'):
        interactive.ask_confirmation('message')


def test_get_username_no_env(monkeypatch):
    """If no env variable is set should return '-'."""
    monkeypatch.delenv('USER', raising=False)
    monkeypatch.delenv('SUDO_USER', raising=False)
    assert interactive.get_username() == '-'


def test_get_username_root(monkeypatch):
    """When unable to detect the real user should return 'root'."""
    monkeypatch.setenv('USER', 'root')
    monkeypatch.delenv('SUDO_USER', raising=False)
    assert interactive.get_username() == 'root'


def test_get_username_ok(monkeypatch):
    """As a normal user with sudo should return the user's name."""
    monkeypatch.setenv('USER', 'root')
    monkeypatch.setenv('SUDO_USER', 'user')
    assert interactive.get_username() == 'user'


@mock.patch('spicerack.interactive.sys.stdout.isatty')
def test_ensure_shell_is_durable_interactive(mocked_isatty):
    """Should raise SpicerackError if in an interactive shell."""
    mocked_isatty.return_value = True
    with pytest.raises(SpicerackError, match='Must be run in non-interactive mode or inside a screen or tmux.'):
        interactive.ensure_shell_is_durable()

    assert mocked_isatty.called


@mock.patch('spicerack.interactive.sys.stdout.isatty')
def test_ensure_shell_is_durable_non_interactive(mocked_isatty):
    """Should raise SpicerackError if in an interactive shell."""
    mocked_isatty.return_value = False
    interactive.ensure_shell_is_durable()
    assert mocked_isatty.called


@mock.patch('spicerack.interactive.sys.stdout.isatty')
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


def test_get_management_password_in_env(monkeypatch):
    """Should return the MGMT_PASSWORD environment variable value, if set."""
    monkeypatch.setenv('MGMT_PASSWORD', 'env_password')
    assert interactive.get_management_password() == 'env_password'


@mock.patch('spicerack.interactive.getpass')
def test_get_management_password_interactive(mocked_getpass, monkeypatch):
    """Should ask for the password the MGMT_PASSWORD environment variable value, if set."""
    monkeypatch.delenv('MGMT_PASSWORD', raising=False)
    mocked_getpass.getpass.return_value = 'interactive_password'
    assert interactive.get_management_password() == 'interactive_password'
    mocked_getpass.getpass.assert_called_once_with(prompt='Management Password: ')


def test_get_management_password_empty(monkeypatch):
    """Should raise SpicerackError if the password is empty."""
    monkeypatch.setenv('MGMT_PASSWORD', '')
    with pytest.raises(SpicerackError, match='Empty Management Password'):
        interactive.get_management_password()
