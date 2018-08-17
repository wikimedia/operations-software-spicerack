"""Initialization tests."""
from spicerack import Spicerack
from spicerack.remote import Remote
from spicerack.confctl import ConftoolEntity

from spicerack.tests import SPICERACK_TEST_PARAMS


def test_spicerack(monkeypatch):
    """An instance of Spicerack should allow to access all the library features."""
    monkeypatch.setenv('SUDO_USER', 'user1')
    verbose = True
    dry_run = False
    spicerack = Spicerack(verbose=verbose, dry_run=dry_run, **SPICERACK_TEST_PARAMS)

    assert spicerack.verbose is verbose
    assert spicerack.dry_run is dry_run
    assert spicerack.user == 'user1'
    assert isinstance(spicerack.remote(), Remote)
    assert isinstance(spicerack.confctl('discovery'), ConftoolEntity)
    assert isinstance(spicerack.confctl('mwconfig'), ConftoolEntity)
