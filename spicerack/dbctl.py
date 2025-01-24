"""dbctl module."""

from typing import Any

from conftool.extensions.dbconfig.config import DbConfig
from conftool.extensions.dbconfig.entities import Instance, Section

from spicerack.confctl import Confctl


class Dbctl(Confctl):
    """Extend the Confctl class to support dbctl actions."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the instance.

        Parameters as required by the parent class.

        """
        super().__init__(*args, **kwargs)
        schema = self._client.schema
        self._mediawiki_config = DbConfig(schema, Instance(schema), Section(schema), self._client.configuration.dbctl())
        self._dbconfig_instance = Instance(schema, self._mediawiki_config.check_instance)
        self._dbconfig_section = Section(schema, self._mediawiki_config.check_section)

    @property
    def config(self) -> DbConfig:
        """Getter for the instance to act like `dbctl config`."""
        return self._mediawiki_config

    @property
    def instance(self) -> Instance:
        """Getter for the instance to act like `dbctl instance`."""
        return self._dbconfig_instance

    @property
    def section(self) -> Section:
        """Getter for the instance to act like `dbctl section`."""
        return self._dbconfig_section
