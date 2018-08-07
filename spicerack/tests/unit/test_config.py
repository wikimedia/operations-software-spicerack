"""Interactive module tests."""
from unittest import mock

import pytest

from spicerack import config

from spicerack.tests import get_fixture_path


def test_get_config_empty():
    """Loading an empty config should return an empty dictionary."""
    config_dir = get_fixture_path('config', 'empty')
    config_dict = config.get_config(config_dir)
    assert {} == config_dict


def test_get_config_invalid_raise():
    """Loading an invalid config should raise Exception."""
    config_dir = get_fixture_path('config', 'invalid')
    with pytest.raises(Exception):
        config.get_config(config_dir)
    # TODO: add caplog to test log output once https://github.com/pytest-dev/pytest/issues/3099 is fixed


def test_get_config_invalid():
    """Loading an invalid config with no_raise=True should return an empty dictionary."""
    config_dir = get_fixture_path('config', 'invalid')
    config_dict = config.get_config(config_dir, no_raise=True)
    assert {} == config_dict
    # TODO: add caplog to test log output once https://github.com/pytest-dev/pytest/issues/3099 is fixed


def test_get_config_missing():
    """Loading a non-existent config should raise Exception."""
    config_dir = get_fixture_path('config', 'non-existent')
    with pytest.raises(Exception):
        config.get_config(config_dir)
    # TODO: add caplog to test log output once https://github.com/pytest-dev/pytest/issues/3099 is fixed


def test_get_config_miss_no_raise():
    """Loading a non-existent config with no_raise=True should return an empty dictionary."""
    config_dir = get_fixture_path('config', 'non-existent')
    config_dict = config.get_config(config_dir, no_raise=True)
    assert {} == config_dict
    # TODO: add caplog to test log output once https://github.com/pytest-dev/pytest/issues/3099 is fixed


def test_get_config_valid():
    """Loading a valid config should return its content."""
    config_dir = get_fixture_path('config', 'valid')
    config_dict = config.get_config(config_dir)
    assert 'key' in config_dict


def test_get_global_config():
    """Calling get_global_config() should return the library's config."""
    with mock.patch('spicerack.config.SPICERACK_CONFIG_DIR', get_fixture_path('config', 'valid')):
        config_dict = config.get_global_config()

    assert 'key' in config_dict
