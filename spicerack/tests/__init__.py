"""Tests package for Spicerack."""

import os


TESTS_BASE_PATH = os.path.realpath(os.path.dirname(__file__))


def get_fixture_path(*paths):
    """Return the absolute path of the given fixture.

    Arguments:
        *paths: arbitrary positional arguments used to compose the absolute path to the fixture.
    """
    return os.path.join(TESTS_BASE_PATH, 'fixtures', *paths)
