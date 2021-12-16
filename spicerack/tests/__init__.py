"""Tests package for Spicerack."""
from pathlib import Path

TESTS_BASE_PATH = Path(__file__).parent.resolve()


def get_fixture_path(*paths):
    """Return the absolute path of the given fixture.

    Arguments:
        *paths: arbitrary positional arguments used to compose the absolute path to the fixture.

    Returns:
        str: the absolute path of the selected fixture.

    """
    return Path(TESTS_BASE_PATH, "fixtures", *paths)


SPICERACK_TEST_PARAMS = {
    "cumin_config": get_fixture_path("remote", "config.yaml"),
    "cumin_installer_config": get_fixture_path("remote", "config_installer.yaml"),
    "conftool_config": get_fixture_path("confctl", "config.yaml"),
    "conftool_schema": get_fixture_path("confctl", "schema.yaml"),
    "debmonitor_config": get_fixture_path("debmonitor", "config.ini"),
    "spicerack_config_dir": get_fixture_path(),
}
