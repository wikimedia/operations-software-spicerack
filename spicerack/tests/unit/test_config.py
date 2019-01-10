"""Interactive module tests."""
import configparser

from logging import DEBUG

import pytest

from spicerack.config import load_ini_config, load_yaml_config
from spicerack.exceptions import SpicerackError
from spicerack.tests import get_fixture_path, caplog_not_available


def test_load_yaml_config_empty():
    """Loading an empty config should return an empty dictionary."""
    config_dict = load_yaml_config(get_fixture_path('config', 'empty.yaml'))
    assert {} == config_dict


@pytest.mark.parametrize('name, message', (
    ('invalid.yaml', 'ParserError'),
    ('non-existent.yaml', 'FileNotFoundError'),
))
def test_load_yaml_config_raise(name, message):
    """Loading an invalid config should raise Exception."""
    with pytest.raises(SpicerackError, match=message):
        load_yaml_config(get_fixture_path('config', name))


@pytest.mark.skipif(caplog_not_available(), reason='Requires caplog fixture')
@pytest.mark.parametrize('name', ('invalid.yaml', 'non-existent.yaml'))
def test_load_yaml_config_no_raise(caplog, name):
    """Loading an invalid config with raises=False should return an empty dictionary."""
    with caplog.at_level(DEBUG):
        config_dict = load_yaml_config(get_fixture_path('config', name), raises=False)

    assert {} == config_dict
    assert 'DEBUG    Could not load config file' in caplog.text


def test_load_yaml_config_valid():
    """Loading a valid config should return its content."""
    config_dir = get_fixture_path('config', 'valid.yaml')
    config_dict = load_yaml_config(config_dir)
    assert 'key' in config_dict


def test_load_ini_config():
    """Loading a INI config should return a configparser.ConfigParser object."""
    config = load_ini_config(get_fixture_path('config', 'config.ini'))
    assert isinstance(config, configparser.ConfigParser)
    assert config.defaults()['key'] == 'value'
