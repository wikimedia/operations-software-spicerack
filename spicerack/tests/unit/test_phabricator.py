"""Phabricator module tests."""
from unittest import mock

import pytest

from spicerack import phabricator
from spicerack.tests import get_fixture_path


def test_create_phabricator_ok():
    """It should initialize the instance."""
    phab = phabricator.create_phabricator(get_fixture_path('phabricator', 'valid.conf'))
    assert isinstance(phab, phabricator.Phabricator)


def test_create_phabricator_missing_section():
    """It should raise PhabricatorError if the specified section is missing in the bot config file."""
    with pytest.raises(phabricator.PhabricatorError, match='Unable to find section'):
        phabricator.create_phabricator(get_fixture_path('phabricator', 'valid.conf'), section='nonexistent')


def test_create_phabricator_missing_option():
    """It should raise PhabricatorError if any of the mandatory option is missing in the bot config file."""
    with pytest.raises(phabricator.PhabricatorError, match='Unable to find all required options'):
        phabricator.create_phabricator(get_fixture_path('phabricator', 'invalid.conf'))


@mock.patch('spicerack.phabricator.phabricator.Phabricator', side_effect=RuntimeError)
def test_init_client_raise(mocked_phabricator):
    """It should raise PhabricatorError if unable to instantiate the Phabricator client."""
    with pytest.raises(phabricator.PhabricatorError, match='Unable to instantiate Phabricator client'):
        phabricator.create_phabricator(get_fixture_path('phabricator', 'valid.conf'))

    # Values from the phabricator/valid.conf fixture
    mocked_phabricator.assert_called_once_with(  # nosec
        host='https://phabricator.example.com/api/', username='phab-bot', token='api-12345')


class TestPhabricator:
    """Test class for the Phabricator class."""

    @mock.patch('spicerack.phabricator.phabricator.Phabricator')
    def setup_method(self, _, mocked_phabricator):
        """Setup the test environment."""
        # pylint: disable=attribute-defined-outside-init
        self.mocked_phabricator_client = mocked_phabricator()
        self.phab = phabricator.Phabricator(self.mocked_phabricator_client, dry_run=False)
        self.task_comment_transactions = [{'type': 'comment', 'value': 'new message'}]

    def test_task_comment_ok(self):
        """It should update a task on Phabricator."""
        self.phab.task_comment('T12345', 'new message')
        self.mocked_phabricator_client.maniphest.edit.assert_called_once_with(
            objectIdentifier='T12345', transactions=self.task_comment_transactions)

    def test_task_comment_dry_run(self):
        """It should not update a task on Phabricator when in DRY-RUN mode."""
        phab = phabricator.Phabricator(self.mocked_phabricator_client)
        phab.task_comment('T12345', 'new message')
        assert not self.mocked_phabricator_client.maniphest.edit.called

    def test_task_comment_fail(self):
        """It should raise PhabricatorError if the update operation fails."""
        self.mocked_phabricator_client.maniphest.edit.side_effect = RuntimeError
        with pytest.raises(phabricator.PhabricatorError, match='Unable to update Phabricator task T12345'):
            self.phab.task_comment('T12345', 'new message')

        self.mocked_phabricator_client.maniphest.edit.assert_called_once_with(
            objectIdentifier='T12345', transactions=self.task_comment_transactions)
