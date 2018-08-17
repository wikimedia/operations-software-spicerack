"""Config module."""
import logging
import os

import yaml

from spicerack.exceptions import SpicerackError


logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


def get_config(config_dir, raises=True):
    """Parse a YAML config file and return it, without failing on error.

    Arguments:
        config_dir (str): the directory where to look for the configuration file to load.
        raises (bool, optional): whether to raise exception if unable to load the config.

    Returns:
        dict: the parsed config or an empty dictionary as a fallback.

    Raises:
        SpicerackError: if unable to load the configuration and ``raises`` is ``True``.

    """
    config_file = os.path.join(config_dir, 'config.yaml')
    config = {}
    try:
        with open(config_file, 'r') as fh:
            config = yaml.safe_load(fh)

    except Exception as e:  # pylint: disable=broad-except
        message = "Could not load config file %s: %s"
        if raises:
            raise SpicerackError(repr(e)) from e

        logger.debug(message, config_file, e)

    if config is None:
        config = {}

    return config


def get_global_config(config_dir='/etc/spicerack'):
    """Return the global configuration.

    Arguments:
        config_dir (str, optional): the directory where to look for the configuration file to load.

    Returns:
        dict: the parsed config or an empty dictionary as a fallback.

    """
    return get_config(config_dir)
