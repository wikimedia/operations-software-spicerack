"""Tests package for Spicerack."""

import os


TESTS_BASE_PATH = os.path.realpath(os.path.dirname(__file__))


def get_fixture_path(path):
    """Return the absolute path of the given fixture.

    Arguments:
        path: the relative path to the test's fixture directory.
    """
    return os.path.join(TESTS_BASE_PATH, 'fixtures', path)
