"""Dbctl module tests."""

from unittest import mock

import pytest
from conftool import configuration, kvobject
from conftool.tests.unit import MockBackend

from spicerack import dbctl
from spicerack.tests import get_fixture_path


class TestDbctl:
    """Dbctl test class."""

    def setup_method(self):
        """Setup a Dbctl instance with a mocked conftool backend and driver."""
        # pylint: disable=attribute-defined-outside-init
        self.conftool_backend = MockBackend({})
        kvobject.KVObject.backend = self.conftool_backend
        kvobject.KVObject.config = configuration.Config(driver="")
        self.config = get_fixture_path("confctl", "config.yaml")
        self.schema = get_fixture_path("confctl", "schema.yaml")
        with mock.patch("spicerack.confctl.kvobject.KVObject.setup"):
            self.dbctl = dbctl.Dbctl(config=self.config, schema=self.schema, dry_run=False)

    @pytest.mark.parametrize(
        "property_name, instance",
        (
            ("config", dbctl.DbConfig),
            ("instance", dbctl.Instance),
            ("section", dbctl.Section),
        ),
    )
    def test_init(self, property_name, instance):
        """It should give access to the dbconfig instances for the various type of objects."""
        assert isinstance(getattr(self.dbctl, property_name), instance)
