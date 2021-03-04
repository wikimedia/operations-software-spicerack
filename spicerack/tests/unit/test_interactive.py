"""Interactive module tests."""
from unittest import mock

import pytest

from spicerack import interactive
from spicerack.exceptions import SpicerackError


def test_get_management_password_in_env(monkeypatch):
    """Should return the MGMT_PASSWORD environment variable value, if set."""
    monkeypatch.setenv("MGMT_PASSWORD", "env_password")
    assert interactive.get_management_password() == "env_password"


@mock.patch("wmflib.interactive.getpass")
def test_get_management_password_interactive(mocked_getpass, monkeypatch):
    """Should ask for the password the MGMT_PASSWORD environment variable value, if set."""
    monkeypatch.delenv("MGMT_PASSWORD", raising=False)
    mocked_getpass.getpass.return_value = "interactive_password"
    assert interactive.get_management_password() == "interactive_password"
    mocked_getpass.getpass.assert_called_once_with(prompt="Management Password: ")


def test_get_management_password_empty(monkeypatch):
    """Should raise SpicerackError if the password is empty."""
    monkeypatch.setenv("MGMT_PASSWORD", "")
    with pytest.raises(SpicerackError, match="Empty Management Password"):
        interactive.get_management_password()
