"""Confctl module to abstract Conftool."""
import logging
import re

from typing import Dict, Iterator, Union

from conftool import configuration, kvobject, loader
from conftool.drivers import BackendError

from spicerack.exceptions import SpicerackError


logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


class ConfctlError(SpicerackError):
    """Custom exception class for errors of this module."""


class Confctl:
    """Confctl class to abstract conftool operations."""

    def __init__(
        self,
        config: str = '/etc/conftool/config.yaml',
        schema: str = '/etc/conftool/schema.yaml',
        dry_run: bool = True
    ) -> None:
        """Initialize the instance.

        Arguments:
            config (str, optional): the path to the configuration file to load.
            schema (str, optional): the path to the Conftool schema to load.
            dry_run (bool, optional): whether this is a DRY-RUN.
        """
        self._dry_run = dry_run
        self._schema = loader.Schema.from_file(schema)
        kvobject.KVObject.setup(configuration.get(config))

    def entity(self, entity_name: str) -> 'ConftoolEntity':
        """Get the Conftool specific entity class.

        Arguments:
            entity_name (str): the name of the entiryself.

        Returns:
            spicerack.confctl.ConftoolEntity: and entity-specific class to perform Conftool operations.

        """
        return ConftoolEntity(self._schema.entities[entity_name], dry_run=self._dry_run)


class ConftoolEntity:
    """ConftoolEntity class to perform operations on a specific Conftool entity."""

    def __init__(self, entity: kvobject.Entity, dry_run: bool = True) -> None:
        """Initialize the instance.

        Arguments:
            entity (conftool.kvobject.Entity): an instance of Conftool entity.
            dry_run (bool, optional): whether this is a DRY-RUN.
        """
        self._entity = entity
        self._dry_run = dry_run

    def _select(self, tags: Dict[str, str]) -> Iterator[kvobject.Entity]:
        """Generator that yields the selected objects based on the provided tags.

        Arguments:
            tags (dict): dictionary with tag: expression pairs of Conftool selectors.

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

    def update(self, changed: Dict[str, Union[bool, str, int, float]], **tags: str) -> None:
        """Updates the value of conftool objects corresponding to the selection done with tags.

        Arguments:
            changed (dict): the new values to set for the selected objects.
            **tags: arbitrary Conftool tags as keyword arguments.

        Raises:
            spicerack.confctl.ConfctlError: on etcd or Conftool errors.

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

    def get(self, **tags: str) -> Iterator[kvobject.Entity]:
        """Generator that yields conftool objects corresponding to the selection.

        Arguments:
            **tags: arbitrary Conftool tags as keyword arguments.

        Yields:
            conftool.kvobject.Entity: the selected object.

        """
        for obj in self._select(tags):
            logger.debug('Selected conftool object: %s', obj)
            yield obj

    def set_and_verify(self, key: str, value: Union[bool, str, int, float], **tags: str) -> None:
        """Set and verify a single Conftool value.

        Arguments:
            key (str): the key in Conftool to modify.
            value (mixed): the value to set.
            **tags: arbitrary Conftool tags as keyword arguments.

        Raises:
            spicerack.confctl.ConfctlError: on etcd or Conftool errors or failing to verify the changes.

        """
        logger.info('Setting %s=%s for tags: %s', key, value, tags)
        self.update({key: value}, **tags)

        for obj in self.get(**tags):  # Verify the changes were applied
            new = getattr(obj, key)
            if new != value and not self._dry_run:
                raise ConfctlError("Conftool key {key} has value '{new}', expecting '{value}' for tags: {tags}".format(
                    key=key, new=new, value=value, tags=tags))
