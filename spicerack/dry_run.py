"""Dry-run module."""
import os


DRY_RUN_ENV = 'SPICERACK_DRY_RUN'


def is_dry_run():
    """Check if the current run must be considered a dry-run.

    Returns:
        bool: True if the dry-run environment variable is properly set.

    """
    return os.getenv(DRY_RUN_ENV) == '1'
