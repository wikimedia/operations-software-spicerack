"""Config module."""
import logging

from configparser import ConfigParser
from typing import Dict

import yaml

from spicerack.exceptions import SpicerackError


logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


def load_yaml_config(config_file: str, raises: bool = True) -> Dict:
    """Parse a YAML config file and return it, optionally not failing on error.

    Arguments:
        config_file (str): the path of the configuration file.
        raises (bool, optional): whether to raise exception if unable to load the config.

    Returns:
        dict: the parsed config or an empty dictionary as a fallback when ``raises`` is ``False``.

    Raises:
        SpicerackError: if unable to load the configuration and ``raises`` is ``True``.

    """
    config = {}  # type: ignore
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


def load_ini_config(config_file: str) -> ConfigParser:
    """Parse an INI config file and return it.

    Arguments:
        config_file (str): the path of the configuration file.

    Returns:
        configparser.ConfigParser: the parsed config.

    """
    config = ConfigParser()
    config.read(config_file)

    return config
