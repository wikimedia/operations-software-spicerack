"""Initialization tests."""
import logging

from unittest import mock

from spicerack import Spicerack
from spicerack.administrative import Reason
from spicerack.confctl import ConftoolEntity
from spicerack.dns import Dns
from spicerack.dnsdisc import Discovery
from spicerack.icinga import Icinga
from spicerack.elasticsearch_cluster import ElasticsearchCluster
from spicerack.mediawiki import MediaWiki
from spicerack.mysql import Mysql
from spicerack.redis_cluster import RedisCluster
from spicerack.remote import Remote

from spicerack.tests import SPICERACK_TEST_PARAMS
from spicerack.tests.unit.test_dns import MockedDnsAnswer, MockedDnsTarget, MockedTarget


@mock.patch('spicerack.remote.Remote.query', autospec=True)
def test_spicerack(mocked_remote_query, monkeypatch):
    """An instance of Spicerack should allow to access all the library features."""
    monkeypatch.setenv('SUDO_USER', 'user1')
    verbose = True
    dry_run = False

    spicerack = Spicerack(verbose=verbose, dry_run=dry_run, **SPICERACK_TEST_PARAMS)

    assert spicerack.verbose is verbose
    assert spicerack.dry_run is dry_run
    assert spicerack.username == 'user1'
    assert isinstance(spicerack.irc_logger, logging.Logger)
    assert isinstance(spicerack.remote(), Remote)
    assert isinstance(spicerack.confctl('discovery'), ConftoolEntity)
    assert isinstance(spicerack.confctl('mwconfig'), ConftoolEntity)
    assert isinstance(spicerack.dns(), Dns)
    assert isinstance(spicerack.discovery('discovery-record'), Discovery)
    assert isinstance(spicerack.mediawiki(), MediaWiki)
    assert isinstance(spicerack.mysql(), Mysql)
    assert isinstance(spicerack.redis_cluster('cluster'), RedisCluster)
    assert isinstance(spicerack.elasticsearch_cluster('eqiad'), ElasticsearchCluster)
    assert isinstance(spicerack.admin_reason('Reason message', task_id='T12345'), Reason)

    assert mocked_remote_query.called


@mock.patch('spicerack.gethostname', return_value='test.example.com')
@mock.patch('spicerack.dns.dns.resolver.Resolver', autospec=True)
@mock.patch('spicerack.remote.Remote.query', autospec=True)
def test_spicerack_icinga(mocked_remote_query, mocked_resolver, mocked_hostname, monkeypatch):
    """An instance of Spicerack should allow to get an Icinga instance."""
    monkeypatch.setenv('SUDO_USER', 'user1')
    dns_response = MockedDnsAnswer(ttl=600, rrset=[
        MockedDnsTarget(target=MockedTarget('icinga-server.example.com.'))])
    mocked_resolver.return_value.query.return_value = dns_response

    spicerack = Spicerack(verbose=True, dry_run=False, **SPICERACK_TEST_PARAMS)

    assert isinstance(spicerack.icinga(), Icinga)
    mocked_hostname.assert_called_once_with()
    assert mocked_remote_query.called
