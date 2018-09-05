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
            self.entity = self.confctl._schema.entities['discovery']  # pylint: disable=protected-access

        self.entity.query = mock.MagicMock(return_value=[self.entity('test', 'dnsdisc')])
        self.discovery = confctl.ConftoolEntity(self.entity, dry_run=False)
        self.discovery_dry_run = confctl.ConftoolEntity(self.entity)

    def test_get_existing(self):
        """Calling get() should return the object matched by the tags."""
        for obj in self.discovery.get(dnsdisc='test'):
            assert obj.tags == {'dnsdisc': 'test'}

    def test_get_non_existing(self):
        """Calling get() without matches should raise ConfctlError."""
        self.entity.query.return_value = []
        with pytest.raises(confctl.ConfctlError, match='No match found'):
            list(self.discovery.get(dnsdisc='non-existing'))

    def test_update_ok(self):
        """Calling update() should update the objects matched by the tags."""
        self.discovery.update({'pooled': True}, dnsdisc='test')
        assert list(self.discovery.get(dnsdisc='test'))[0].pooled

    def test_update_dry_run(self):
        """Calling update() in dry_run mode should not update the objects matched by the tags."""
        list(self.discovery_dry_run.get(dnsdisc='test'))[0].update = mock.MagicMock(side_effect=Exception('test'))
        self.discovery_dry_run.update({'pooled': True}, dnsdisc='test')

    @pytest.mark.parametrize('exc_class, message', (
        (confctl.BackendError, 'Error writing to etcd'),
        (Exception, 'Generic error in conftool'),
    ))
    def test_update_errors(self, exc_class, message):
        """Calling update() should raise ConfctlError if there is an error in the backend."""
        list(self.discovery.get(dnsdisc='test'))[0].update = mock.MagicMock(side_effect=exc_class('test'))

        with pytest.raises(confctl.ConfctlError, match=message):
            self.discovery.update({'pooled': True}, dnsdisc='test')

    def test_set_and_verify_ok(self):
        """It should update the objects matched by the tags and check them."""
        self.discovery.set_and_verify('pooled', True, dnsdisc='test')
        assert list(self.discovery.get(dnsdisc='test'))[0].pooled

    def test_set_and_verify_fail(self):
        """It should raise ConfctlError if failing to check the modified objects."""
        list(self.discovery.get(dnsdisc='test'))[0].update = mock.MagicMock()  # Don't allow to update the record
        with pytest.raises(confctl.ConfctlError, match="Conftool key pooled has value 'False', expecting 'True'"):
            self.discovery.set_and_verify('pooled', True, dnsdisc='test')

    def test_set_and_verify_dry_run(self):
        """In dry_run mode it should not update the objects and not raise on failure to check them."""
        self.discovery_dry_run.set_and_verify('pooled', True, dnsdisc='test')
        assert not list(self.discovery.get(dnsdisc='test'))[0].pooled
