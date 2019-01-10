"""Tests package for Spicerack."""
import os

from pkg_resources import get_distribution, parse_version

import pytest


TESTS_BASE_PATH = os.path.realpath(os.path.dirname(__file__))
CAPLOG_MIN_VERSION = '3.3.0'
REQUESTS_MOCK_MIN_VERSION = '1.5.0'
ELASTICSEARCH_MIN_VERSION = '5.0.0'


def get_fixture_path(*paths):
    """Return the absolute path of the given fixture.

    Arguments:
        *paths: arbitrary positional arguments used to compose the absolute path to the fixture.

    Returns:
        str: the absolute path of the selected fixture.

    """
    return os.path.join(TESTS_BASE_PATH, 'fixtures', *paths)


SPICERACK_TEST_PARAMS = {
    'cumin_config': get_fixture_path('remote', 'config.yaml'),
    'conftool_config': get_fixture_path('confctl', 'config.yaml'),
    'conftool_schema': get_fixture_path('confctl', 'schema.yaml'),
    'debmonitor_config': get_fixture_path('debmonitor', 'config.ini'),
    'spicerack_config_dir': get_fixture_path(),
}


def caplog_not_available():
    """Check if the caplog fixture is not available.

    Returns:
        bool: True if the caplog fixture is not available, False otherwise.

    """
    return parse_version(pytest.__version__) < parse_version(CAPLOG_MIN_VERSION)


def requests_mock_not_available():
    """Check if the requests_mock fixture is not available.

    Returns:
        bool: True if the requests_mock fixture is not available, False otherwise.

    """
    return parse_version(get_distribution('requests_mock').version) < parse_version(REQUESTS_MOCK_MIN_VERSION)


def elasticsearch_too_old():
    """Check if elasticsearch version is less than 5.0.0

    Returns:
        bool: True if elasticsearch version is less 5.0.0, False if otherwise

    """
    return parse_version(get_distribution('elasticsearch').version) < parse_version(ELASTICSEARCH_MIN_VERSION)
