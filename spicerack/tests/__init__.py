"""Tests package for Spicerack."""
import os

import pytest

from pkg_resources import get_distribution, parse_version


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

require_requests_mock = pytest.mark.skipif(  # pylint: disable=invalid-name
    parse_version(get_distribution('requests_mock').version) < parse_version(REQUESTS_MOCK_MIN_VERSION),
    reason='Requires requests-mock fixture')

require_caplog = pytest.mark.skipif(  # pylint: disable=invalid-name
    parse_version(pytest.__version__) < parse_version(CAPLOG_MIN_VERSION), reason='Requires caplog fixture')

min_elasticsearch = pytest.mark.skipif(  # pylint: disable=invalid-name
    parse_version(get_distribution('elasticsearch').version) < parse_version(ELASTICSEARCH_MIN_VERSION),
    reason='Requires more recent elasticsearch module')
