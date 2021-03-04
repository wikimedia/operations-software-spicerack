"""Interactive module."""
import logging
import os

from wmflib.interactive import get_secret

from spicerack.exceptions import SpicerackError

logger = logging.getLogger(__name__)


def get_management_password() -> str:
    """Get the management password either from the environment or asking for it.

    Returns:
        str: the password.

    Raises:
        spicerack.exceptions.SpicerackError: if the password is empty.

    """
    password = os.getenv("MGMT_PASSWORD")

    if password is None:
        logger.debug("MGMT_PASSWORD environment variable not found")
        # Ask for a password, raise exception if not a tty
        password = get_secret("Management Password")
    else:
        logger.info("Using Management Password from the MGMT_PASSWORD environment variable")

    if not password:
        raise SpicerackError("Empty Management Password")

    return password
