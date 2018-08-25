"""Initialization tests."""
import logging

from unittest import mock

from spicerack import Spicerack
from spicerack.confctl import ConftoolEntity
from spicerack.dnsdisc import Discovery
from spicerack.mediawiki import MediaWiki
from spicerack.mysql import Mysql
from spicerack.remote import Remote

from spicerack.tests import SPICERACK_TEST_PARAMS


@mock.patch('spicerack.remote.Remote.query')
def test_spicerack(mocked_remote_query, monkeypatch):
    """An instance of Spicerack should allow to access all the library features."""
    monkeypatch.setenv('SUDO_USER', 'user1')
    verbose = True
    dry_run = False
    spicerack = Spicerack(verbose=verbose, dry_run=dry_run, **SPICERACK_TEST_PARAMS)

    assert spicerack.verbose is verbose
    assert spicerack.dry_run is dry_run
    assert spicerack.user == 'user1'
    assert isinstance(spicerack.irc_logger, logging.Logger)
    assert isinstance(spicerack.remote(), Remote)
    assert isinstance(spicerack.confctl('discovery'), ConftoolEntity)
    assert isinstance(spicerack.confctl('mwconfig'), ConftoolEntity)
    assert isinstance(spicerack.discovery('discovery-record'), Discovery)
    assert isinstance(spicerack.mediawiki(), MediaWiki)
    assert isinstance(spicerack.mysql(), Mysql)

    assert mocked_remote_query.called
