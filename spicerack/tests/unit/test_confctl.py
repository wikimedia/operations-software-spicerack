"""Confctl module tests."""
from unittest import mock

import pytest

from conftool.tests.unit import MockBackend

from spicerack import confctl

from spicerack.tests import get_fixture_path


class TestConfctl:
    """Confctl test class."""

    def setup_method(self):
        """Setup a Confctl instance with a mocked conftool backend and driver."""
        # pylint: disable=attribute-defined-outside-init
        self.conftool_backend = MockBackend({})
        confctl.kvobject.KVObject.backend = self.conftool_backend
        confctl.kvobject.KVObject.config = confctl.configuration.Config(driver='')
        config = get_fixture_path('confctl', 'config.yaml')
        schema = get_fixture_path('confctl', 'schema.yaml')
        with mock.patch('spicerack.confctl.kvobject.KVObject.setup'):
            self.confctl = confctl.Confctl(config=config, schema=schema, dry_run=False)
            self.confctl_dry_run = confctl.Confctl(config=config, schema=schema)
            self.discovery = self.confctl.entity('discovery')
            self.discovery_dry_run = self.confctl_dry_run.entity('discovery')

    def test_init(self):
        """Initializing the class should load the schema."""
        assert self.confctl.schema.entities

    def test_get_existing(self):
        """Calling get() should return the object matched by the tags."""
        self.discovery.entity.query = mock.MagicMock(return_value=[self.discovery.entity('test', 'dnsdisc')])
        for obj in self.discovery.get(dnsdisc='test'):
            assert obj.tags == {'dnsdisc': 'test'}

    def test_get_non_existing(self):
        """Calling get() without matches should not return any object."""
        self.discovery.entity.query = mock.MagicMock(return_value=[])
        assert list(self.discovery.get(dnsdisc='test')) == []

    def test_update_ok(self):
        """Calling update() should update the objects matched by the tags."""
        self.discovery.entity.query = mock.MagicMock(return_value=[self.discovery.entity('test', 'dnsdisc')])
        self.discovery.update({'pooled': True}, dnsdisc='test')
        assert list(self.discovery.get(dnsdisc='test'))[0].pooled

    def test_update_dry_run(self):
        """Calling update() in dry_run mode should not update the objects matched by the tags."""
        self.discovery_dry_run.entity.query = mock.MagicMock(
            return_value=[self.discovery_dry_run.entity('test', 'dnsdisc')])
        list(self.discovery_dry_run.get(dnsdisc='test'))[0].update = mock.MagicMock(side_effect=Exception('test'))
        self.discovery_dry_run.update({'pooled': True}, dnsdisc='test')

    @pytest.mark.parametrize('exc_class, message', (
        (confctl.BackendError, 'Error writing to etcd'),
        (Exception, 'Generic error in conftool'),
    ))
    def test_update_errors(self, exc_class, message):
        """Calling update() should raise ConfctlError if there is an error in the backend."""
        self.discovery.entity.query = mock.MagicMock(return_value=[self.discovery.entity('test', 'dnsdisc')])
        list(self.discovery.get(dnsdisc='test'))[0].update = mock.MagicMock(side_effect=exc_class('test'))

        with pytest.raises(confctl.ConfctlError, match=message):
            self.discovery.update({'pooled': True}, dnsdisc='test')
