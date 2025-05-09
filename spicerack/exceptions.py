"""Exceptions module."""


class SpicerackError(Exception):
    """Parent exception class for all Spicerack exceptions."""


class SpicerackCheckError(SpicerackError):
    """Parent exception class for all Spicerack exceptions regarding checks.

    Particularly useful when some write action is performed and then checked but in dry-run mode, as in this mode the
    write action will not actually change anything and the check will then fail, but should be catchable separately
    from the other potential exceptions that could be raised.
    """


class RunCookbookError(SpicerackError):
    """Exception raised when running :py:meth:`spicerack.Spicerack.run_cookbook`.

    When the method is called setting its ``raises`` argument to :py:data:`True` and the cookbook run exit with a
    non-zero exit code.
    """
