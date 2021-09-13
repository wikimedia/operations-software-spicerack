"""Confctl module to abstract Conftool."""
import logging
import re
from contextlib import contextmanager
from typing import Dict, Iterable, Iterator, Union

from conftool import configuration, kvobject, loader
from conftool.drivers import BackendError

from spicerack.exceptions import SpicerackError

logger = logging.getLogger(__name__)


class ConfctlError(SpicerackError):
    """Custom exception class for errors of this module."""


class Confctl:
    """Confctl class to abstract conftool operations."""

    def __init__(
        self,
        config: str = "/etc/conftool/config.yaml",
        schema: str = "/etc/conftool/schema.yaml",
        dry_run: bool = True,
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

    def entity(self, entity_name: str) -> "ConftoolEntity":
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
            selectors[tag] = re.compile(f"^{expr}$")

        obj = None
        for obj in self._entity.query(selectors):
            yield obj

        if obj is None:
            raise ConfctlError("No match found")

    def update(self, changed: Dict[str, Union[bool, str, int, float]], **tags: str) -> None:
        """Updates the value of conftool objects corresponding to the selection done with tags.

        Arguments:
            changed (dict): the new values to set for the selected objects.
            **tags: arbitrary Conftool tags as keyword arguments.

        Raises:
            spicerack.confctl.ConfctlError: on etcd or Conftool errors.

        Examples:
            >>> confctl.update({'pooled': 'no'}, service='appservers-.*', name='eqiad')

        """
        logger.debug("Updating conftool matching tags: %s", tags)
        self.update_objects(changed, self._select(tags))

    def get(self, **tags: str) -> Iterator[kvobject.Entity]:
        """Generator that yields conftool objects corresponding to the selection.

        Arguments:
            **tags: arbitrary Conftool tags as keyword arguments.

        Yields:
            conftool.kvobject.Entity: the selected object.

        """
        for obj in self._select(tags):
            logger.debug("Selected conftool object: %s", obj)
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
        logger.info("Setting %s=%s for tags: %s", key, value, tags)
        self.update({key: value}, **tags)

        for obj in self.get(**tags):  # Verify the changes were applied
            new = getattr(obj, key)
            if new != value and not self._dry_run:
                raise ConfctlError(f"Conftool key {key} has value '{new}', expecting '{value}' for tags: {tags}")

    def filter_objects(
        self, filter_expr: Dict[str, Union[bool, str, int, float]], **tags: str
    ) -> Iterator[kvobject.Entity]:
        """Filters objects coming from conftool based on values.

        A generator will be returned which will contain only objects that match all filters.

        Arguments:
           filter_expr (dict): a set of desired field names and values.
           **tags: arbitrary Conftool tags as keyword arguments.

        Yields:
            conftool.kvobject.Entity: the selected object.

        Raises:
            spicerack.confctl.ConfctlError: if no object corresponds to the tags

        """
        for obj in self._select(tags):
            matching = True
            for key, desired in filter_expr.items():
                try:
                    value = getattr(obj, key)
                except AttributeError as e:
                    raise ConfctlError(f'Could not find property "{key}" in object {obj.pprint()}') from e
                if value != desired:
                    matching = False
            if matching:
                yield obj

    def update_objects(
        self,
        changed: Dict[str, Union[bool, str, int, float]],
        objects: Iterable[kvobject.Entity],
    ) -> None:
        """Updates the value of the provided conftool objects.

        Arguments:
            changed (dict): the new values to set for the selected objects.
            query (iterator(kvobject.Entity)): an iterator of conftool objects

        Raises:
            spicerack.confctl.ConfctlError: on etcd or Conftool errors.

        Examples:
            >>> inactive = confctl.filter_objects({'pooled': 'inactive'}, service='appservers-.*', name='eqiad')
            >>> confctl.update_objects({'pooled': 'no'}, inactive)

        """
        # TODO: make the api nicer by returning an EntitiesCollection from filter_objects so we can allow to write
        # >>> inactive.update({'pooled': 'no'})
        if self._dry_run:
            message_prefix = "Skipping conftool update on dry-run mode"
        else:
            message_prefix = "Updating conftool"

        for obj in objects:
            logger.debug("%s: %s -> %s", message_prefix, obj, changed)
            if self._dry_run:
                continue

            try:
                obj.update(changed)
            except BackendError as e:
                raise ConfctlError("Error writing to etcd") from e
            except Exception as e:
                raise ConfctlError("Generic error in conftool") from e

    @contextmanager
    def change_and_revert(
        self, field: str, original: Union[bool, str, int, float], changed: Union[bool, str, int, float], **tags: str
    ) -> Iterator[Iterable[kvobject.Entity]]:
        """Context manager to perform actions with a changed value in conftool.

        This method will only act on objects that had the original value.

        Warning:
            If the code executed within the contextmanager raises an unhandled
            exception, the original state of the objects will NOT be restored.

        Arguments:
            field (str): The field to change the value of
            original (bool, str, int, float): original value
            changed (bool, str, int, float): changed value
            tags: Appropriate conftool tags for the chosen entity to select objects

        Yields:
            generator: conftool.kvObject.Entity the objects that were acted upon

        """
        objects = list(self.filter_objects({field: original}, **tags))
        self.update_objects({field: changed}, objects)
        yield objects
        self.update_objects({field: original}, objects)
