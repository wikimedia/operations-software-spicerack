"""Config module."""
import logging
import os

import yaml

from spicerack.exceptions import SpicerackError


SPICERACK_CONFIG_DIR = os.environ.get('SPICERACK_CONFIG_DIR', '/etc/spicerack')
logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


def get_config(config_dir, no_raise=False):
    """Parse a YAML config file and return it, without failing on error.

    Arguments:
        config_dir (str): the directory where to look for the configuration file to load.
        no_raise (bool): whether to raise if unable to load the config.

    Returns:
        dict: the parsed config or an empty dictionary as a fallback.

    Raises:
        SpicerackError: if unable to load the configuration and ``no_raise`` is ``False``.

    """
    config_file = os.path.join(config_dir, 'config.yaml')
    config = {}
    try:
        with open(config_file, 'r') as fh:
            config = yaml.safe_load(fh)

    except Exception as e:  # pylint: disable=broad-except
        message = "Could not load config file %s: %s"
        if no_raise:
            logger.debug(message, config_file, e)
        else:
            logger.error(message, config_file, e)
            raise SpicerackError(repr(e)) from e

    if config is None:
        config = {}

    return config


def get_global_config():
    """Return the global configuration.

    Returns:
        dict: the parsed config or an empty dictionary as a fallback.

    """
    return get_config(SPICERACK_CONFIG_DIR)
