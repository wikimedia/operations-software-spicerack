"""Confctl module to abstract Conftool."""
import logging
import re

from conftool import configuration, kvobject, loader
from conftool.drivers import BackendError

from spicerack.exceptions import SpicerackError


logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


class ConfctlError(SpicerackError):
    """Custom exception class for errors of this module."""


class Confctl:
    """Conftl class to abstract conftool operations."""

    def __init__(self, config='/etc/conftool/config.yaml', schema='/etc/conftool/schema.yaml', dry_run=True):
        """Initialize the instance.

        Arguments:
            config (str, optional): the path to the configuration file to load.
            schema (str, optional): the path to the Conftool schema to load.
            dry_run (bool, optional): whether this is a DRY-RUN.
        """
        self._dry_run = dry_run
        self._schema = loader.Schema.from_file(schema)
        kvobject.KVObject.setup(configuration.get(config))

    def entity(self, entity_name):
        """Get the Conftool specific entity class.

        Argumetns:
            entity_name (str): the name of the entiryself.

        Returns:
            spicerack.confctl.ConftoolEntity: and entity-specific class to perform Conftool operations.

        """
        return ConftoolEntity(self._schema.entities[entity_name], dry_run=self._dry_run)


class ConftoolEntity:
    """ConftoolEntity class to perform operations on a specific Conftool entity."""

    def __init__(self, entity, dry_run=True):
        """Initialize the instance.

        Arguments:
            entity (conftool.kvobject.Entity): an instance of Conftool entity.
            dry_run (bool, optional): whether this is a DRY-RUN.
        """
        self._entity = entity
        self._dry_run = dry_run

    def _select(self, tags):
        """Generator that yields the selected objects based on the provided tags.

        Arguments:
            tags (dict): dictionary with tag: expression pairs of selectors.

        Yields:
            conftool.kvobject.Entity: the selected object.

        Raises:
            spicerack.confctl.ConfctlError: if not match is found.

        """
        selectors = {}
        for tag, expr in tags.items():
            selectors[tag] = re.compile('^{}$'.format(expr))

        obj = None
        for obj in self._entity.query(selectors):
            yield obj

        if obj is None:
            raise ConfctlError('No match found')

    def update(self, changed, **tags):
        """Updates the value of conftool objects corresponding to the selection done with tags.

        Arguments:
            changed (dict): the new values to set for the selected objects.
            **tags: arbitrary tags as keyword arguments.

        Raises:
            ConfctlError: on etcd or Conftool errors.

        Examples:
            >>> confctl.update({'pooled': False}, service='appservers-.*', name='eqiad')

        """
        logger.debug('Updating conftool matching tags: %s', tags)
        if self._dry_run:
            message_prefix = 'Skipping conftool update on dry-run mode'
        else:
            message_prefix = 'Updating conftool'

        for obj in self._select(tags):
            logger.debug('%s: %s -> %s', message_prefix, obj, changed)
            if self._dry_run:
                continue

            try:
                obj.update(changed)
            except BackendError as e:
                raise ConfctlError('Error writing to etcd') from e
            except Exception as e:
                raise ConfctlError('Generic error in conftool') from e

    def get(self, **tags):
        """Generator that yields conftool objects corresponding to the selection.

        Arguments:
            **tags: arbitrary tags as keyword arguments.

        Yields:
            conftool.kvobject.Entity: the selected object.

        """
        for obj in self._select(tags):
            logger.debug('Selected conftool object: %s', obj)
            yield obj
