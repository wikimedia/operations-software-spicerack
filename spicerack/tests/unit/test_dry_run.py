"""Dry-run module tests."""
from spicerack.dry_run import DRY_RUN_ENV, is_dry_run


def test_is_dry_run_not_set(monkeypatch):
    """If the enviroment variable is not set it should return False."""
    monkeypatch.delenv(DRY_RUN_ENV, raising=False)
    assert not is_dry_run()


def test_is_dry_run_set_empty(monkeypatch):
    """If the enviroment variable is set to an empty string it should return False."""
    monkeypatch.setenv(DRY_RUN_ENV, '')
    assert not is_dry_run()


def test_is_dry_run_set_wrong(monkeypatch):
    """If the enviroment variable is set to an unrecognized string it should return False."""
    monkeypatch.setenv(DRY_RUN_ENV, 'invalid')
    assert not is_dry_run()


def test_is_dry_run_set_ok(monkeypatch):
    """If the enviroment variable is set to 1 it should return True."""
    monkeypatch.setenv(DRY_RUN_ENV, '1')
    assert is_dry_run()
