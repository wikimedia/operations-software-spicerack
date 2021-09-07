"""Initialization tests."""
import logging
from unittest import mock

import pytest
from requests import Session
from wmflib.actions import ActionsDict
from wmflib.dns import Dns
from wmflib.phabricator import Phabricator
from wmflib.prometheus import Prometheus

from spicerack import Spicerack, puppet
from spicerack.administrative import Reason
from spicerack.confctl import ConftoolEntity
from spicerack.debmonitor import Debmonitor
from spicerack.dhcp import DHCP
from spicerack.dnsdisc import Discovery
from spicerack.elasticsearch_cluster import ElasticsearchClusters
from spicerack.ganeti import Ganeti
from spicerack.icinga import IcingaHosts
from spicerack.ipmi import Ipmi
from spicerack.management import Management
from spicerack.mediawiki import MediaWiki
from spicerack.mysql import Mysql
from spicerack.mysql_legacy import MysqlLegacy
from spicerack.netbox import Netbox, NetboxServer
from spicerack.redis_cluster import RedisCluster
from spicerack.remote import Remote, RemoteHosts
from spicerack.tests import SPICERACK_TEST_PARAMS, get_fixture_path
from spicerack.toolforge.etcdctl import EtcdctlController


@mock.patch("spicerack.remote.Remote.query", autospec=True)
@mock.patch("wmflib.dns.resolver", autospec=True)
def test_spicerack(mocked_dns_resolver, mocked_remote_query, monkeypatch):
    """An instance of Spicerack should allow to access all the library features."""
    monkeypatch.setenv("SUDO_USER", "user1")
    verbose = True
    dry_run = False
    proxy = "http://proxy.example.com:8080"
    spicerack = Spicerack(verbose=verbose, dry_run=dry_run, http_proxy=proxy, **SPICERACK_TEST_PARAMS)

    assert spicerack.verbose is verbose
    assert spicerack.dry_run is dry_run
    assert spicerack.username == "user1"
    assert spicerack.config_dir == get_fixture_path()
    assert spicerack.http_proxy == proxy
    assert spicerack.requests_proxies == {"http": proxy, "https": proxy}
    assert isinstance(spicerack.irc_logger, logging.Logger)
    assert isinstance(spicerack.actions, ActionsDict)
    assert isinstance(spicerack.remote(), Remote)
    assert isinstance(spicerack.remote(installer=True), Remote)
    assert isinstance(spicerack.confctl("discovery"), ConftoolEntity)
    assert isinstance(spicerack.confctl("mwconfig"), ConftoolEntity)
    assert isinstance(spicerack.dns(), Dns)
    assert isinstance(spicerack.discovery("discovery-record"), Discovery)
    assert isinstance(spicerack.mediawiki(), MediaWiki)
    assert isinstance(spicerack.mysql(), Mysql)
    assert isinstance(spicerack.mysql_legacy(), MysqlLegacy)
    assert isinstance(spicerack.redis_cluster("cluster"), RedisCluster)
    assert isinstance(
        spicerack.elasticsearch_clusters("search_eqiad", ("some_core_dc",)),
        ElasticsearchClusters,
    )
    assert isinstance(spicerack.admin_reason("Reason message", task_id="T12345"), Reason)
    assert isinstance(spicerack.puppet(mock.MagicMock(spec_set=RemoteHosts)), puppet.PuppetHosts)
    assert isinstance(
        spicerack.phabricator(get_fixture_path("phabricator", "valid.conf")),
        Phabricator,
    )
    assert isinstance(spicerack.prometheus(), Prometheus)
    assert isinstance(spicerack.debmonitor(), Debmonitor)
    assert isinstance(spicerack.management(), Management)
    assert isinstance(spicerack.ganeti(), Ganeti)
    assert isinstance(spicerack.requests_session("name"), Session)
    assert isinstance(
        spicerack.etcdctl(remote_host=mock.MagicMock(spec_set=RemoteHosts)),
        EtcdctlController,
    )
    assert mocked_remote_query.called
    assert mocked_dns_resolver.Resolver.called


def test_spicerack_http_proxy():
    """An instance of Spicerack by default should not set any HTTP proxy."""
    spicerack = Spicerack(**SPICERACK_TEST_PARAMS)
    assert spicerack.http_proxy == ""
    assert spicerack.requests_proxies is None


@mock.patch("spicerack.gethostname", return_value="test.example.com")
@mock.patch("spicerack.Dns", autospec=True)
@mock.patch("spicerack.remote.Remote.query", autospec=True)
@mock.patch("spicerack.icinga.CommandFile", autospec=True)
def test_spicerack_icinga(mocked_command_file, mocked_remote_query, mocked_dns, mocked_hostname, monkeypatch):
    """An instance of Spicerack should allow to get an Icinga and IcingaHosts instances."""
    monkeypatch.setenv("SUDO_USER", "user1")
    icinga_server = mock.MagicMock(spec_set=RemoteHosts)
    icinga_server.hosts = "icinga-server.example.com"
    icinga_server.__len__.return_value = 1
    mocked_remote_query.return_value = icinga_server
    mocked_dns.return_value.resolve_cname.return_value = "icinga-server.example.com"
    mocked_command_file.return_value = "/var/lib/icinga/rw/icinga.cmd"

    spicerack = Spicerack(verbose=True, dry_run=False, **SPICERACK_TEST_PARAMS)

    assert spicerack.icinga_master_host.hosts == "icinga-server.example.com"
    assert isinstance(spicerack.icinga_hosts(["host1", "host2"]), IcingaHosts)
    mocked_hostname.assert_called_once_with()


@mock.patch("spicerack.get_puppet_ca_hostname", return_value="puppetmaster.example.com")
@mock.patch("spicerack.remote.Remote.query", autospec=True)
def test_spicerack_puppet_master(mocked_remote_query, mocked_get_puppet_ca_hostname):
    """An instance of Spicerack should allow to get a PuppetMaster instance."""
    host = mock.MagicMock(spec_set=RemoteHosts)
    host.__len__.return_value = 1
    mocked_remote_query.return_value = host
    spicerack = Spicerack(verbose=True, dry_run=False, **SPICERACK_TEST_PARAMS)

    assert isinstance(spicerack.puppet_master(), puppet.PuppetMaster)
    mocked_get_puppet_ca_hostname.assert_called_once_with()
    assert mocked_remote_query.called


def test_spicerack_ipmi(monkeypatch):
    """Should instantiate an instance of Ipmi."""
    monkeypatch.setenv("MGMT_PASSWORD", "env_password")
    spicerack = Spicerack(verbose=True, dry_run=False, **SPICERACK_TEST_PARAMS)
    assert isinstance(spicerack.ipmi("test-mgmt.example.com"), Ipmi)


def test_spicerack_ipmi_cached(monkeypatch):
    """Should instantiate an instance of Ipmi only the first time and re-use the cached instance after."""
    monkeypatch.setenv("MGMT_PASSWORD", "first_password")
    expected_cached = {"IPMITOOL_PASSWORD": "first_password"}
    spicerack = Spicerack(verbose=True, dry_run=False, **SPICERACK_TEST_PARAMS)
    assert spicerack.ipmi("test-mgmt.example.com").env == expected_cached
    monkeypatch.setenv("MGMT_PASSWORD", "second_password")

    assert spicerack.ipmi("test-mgmt.example.com").env == expected_cached


@pytest.mark.parametrize(
    "read_write, token",
    (
        (False, "ro_token"),
        (True, "rw_token"),
    ),
)
@mock.patch("spicerack.Dns", autospec=True)
@mock.patch("spicerack.remote.Remote.query", autospec=True)
@mock.patch("pynetbox.api")
def test_spicerack_netbox(mocked_pynetbox, mocked_remote_query, mocked_dns, read_write, token):
    """Test instantiating Netbox abstraction."""
    netbox_server = mock.MagicMock(spec_set=RemoteHosts)
    netbox_server.hosts = "netbox-server.example.com"
    mocked_remote_query.return_value = netbox_server
    mocked_dns.return_value.resolve_cname.return_value = "netbox-server.example.com"
    mocked_pynetbox.reset_mock()

    spicerack = Spicerack(verbose=True, dry_run=False, **SPICERACK_TEST_PARAMS)

    assert isinstance(spicerack.netbox(read_write=read_write), Netbox)
    # Values from fixtures/netbox/config.yaml
    mocked_pynetbox.assert_called_once_with("https://netbox.example.com", token=token)
    assert spicerack.netbox_master_host.hosts == "netbox-server.example.com"

    mocked_pynetbox.reset_mock()
    mocked_pynetbox.return_value.dcim.devices.get.return_value.device_role.slug = "server"
    assert isinstance(spicerack.netbox_server("host1"), NetboxServer)


def test_spicerack_dhcp():
    """Test spicerack.dhcp. It should succeed if a host list with more than one member is passed."""
    mock_hosts = mock.MagicMock()
    mock_hosts.__len__.return_value = 1

    spicerack = Spicerack(verbose=True, dry_run=False, **SPICERACK_TEST_PARAMS)
    assert isinstance(spicerack.dhcp(mock_hosts), DHCP)
