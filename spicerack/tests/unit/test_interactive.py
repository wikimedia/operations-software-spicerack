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
