"""Initialization tests."""

import logging
import sys
from collections import namedtuple
from importlib import import_module
from socket import gethostname
from unittest import mock

import pytest
from git import Repo
from requests import Session
from requests.auth import HTTPBasicAuth
from wmflib.actions import ActionsDict
from wmflib.config import load_yaml_config
from wmflib.dns import Dns
from wmflib.interactive import AbortError
from wmflib.phabricator import Phabricator
from wmflib.prometheus import Prometheus, Thanos

from spicerack import ElasticsearchClusters, Spicerack
from spicerack._cookbook import get_cookbook_callback
from spicerack.administrative import Reason
from spicerack.alerting import AlertingHosts
from spicerack.alertmanager import Alertmanager, AlertmanagerHosts
from spicerack.apiclient import APIClient
from spicerack.apt import AptGetHosts
from spicerack.confctl import ConftoolEntity
from spicerack.dbctl import Dbctl
from spicerack.debmonitor import Debmonitor
from spicerack.dhcp import DHCP
from spicerack.dnsdisc import Discovery
from spicerack.exceptions import RunCookbookError, SpicerackError
from spicerack.ganeti import Ganeti
from spicerack.hosts import Host
from spicerack.icinga import IcingaHosts
from spicerack.ipmi import Ipmi
from spicerack.k8s import Kubernetes
from spicerack.kafka import Kafka
from spicerack.locking import Lock, NoLock
from spicerack.mediawiki import MediaWiki
from spicerack.mysql import Mysql
from spicerack.netbox import Netbox, NetboxServer
from spicerack.orchestrator import Orchestrator
from spicerack.peeringdb import PeeringDB
from spicerack.puppet import PuppetHosts, PuppetMaster, PuppetServer
from spicerack.redfish import RedfishDell, RedfishSupermicro
from spicerack.redis_cluster import RedisCluster
from spicerack.remote import Remote, RemoteError, RemoteHosts
from spicerack.reposync import RepoSync
from spicerack.service import Catalog
from spicerack.tests import SPICERACK_TEST_PARAMS, get_fixture_path
from spicerack.toolforge.etcdctl import EtcdctlController

MockedDnsSrv = namedtuple("MockedDnsSrv", ["target"])
MockedDnsAnswer = namedtuple("MockedDnsAnswer", ["ttl", "rrset"])


@mock.patch("wmflib.dns.resolver", autospec=True)
def test_spicerack(mocked_dns_resolver, monkeypatch):
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
    assert spicerack.current_hostname == gethostname()
    assert spicerack.requests_proxies == {"http": proxy, "https": proxy}
    assert spicerack.authdns_servers == {"authdns1001.example.org": "10.0.0.1", "authdns2001.example.org": "10.0.0.2"}
    assert list(spicerack.authdns_active_hosts.hosts) == ["authdns1001.example.org", "authdns2001.example.org"]
    assert isinstance(spicerack.irc_logger, logging.Logger)
    assert isinstance(spicerack.sal_logger, logging.Logger)
    assert isinstance(spicerack.actions, ActionsDict)
    assert isinstance(spicerack.remote(), Remote)
    assert isinstance(spicerack.remote(installer=True), Remote)
    assert isinstance(spicerack.confctl("discovery"), ConftoolEntity)
    assert isinstance(spicerack.confctl("mwconfig"), ConftoolEntity)
    assert isinstance(spicerack.dbctl(), Dbctl)
    assert isinstance(spicerack.dns(), Dns)
    assert isinstance(spicerack.discovery("discovery-record"), Discovery)
    assert isinstance(spicerack.kubernetes("group", "cluster"), Kubernetes)
    assert isinstance(spicerack.mediawiki(), MediaWiki)
    assert isinstance(spicerack.mysql(), Mysql)
    assert isinstance(spicerack.redis_cluster("cluster"), RedisCluster)
    if sys.version_info < (3, 10):
        assert isinstance(
            spicerack.elasticsearch_clusters("search_eqiad", ("some_core_dc",)),
            ElasticsearchClusters,
        )
    assert isinstance(spicerack.admin_reason("Reason message", task_id="T12345"), Reason)
    assert isinstance(spicerack.puppet(mock.MagicMock(spec_set=RemoteHosts)), PuppetHosts)
    assert isinstance(
        spicerack.phabricator(get_fixture_path("phabricator", "valid.conf")),
        Phabricator,
    )
    assert isinstance(spicerack.prometheus(), Prometheus)
    assert isinstance(spicerack.thanos(), Thanos)
    assert isinstance(spicerack.debmonitor(), Debmonitor)
    assert isinstance(spicerack.ganeti(), Ganeti)
    assert isinstance(spicerack.requests_session("name"), Session)
    assert isinstance(spicerack.api_client("https://api.example.org/v1"), APIClient)
    assert isinstance(
        spicerack.etcdctl(remote_host=mock.MagicMock(spec_set=RemoteHosts)),
        EtcdctlController,
    )
    assert isinstance(spicerack.kafka(), Kafka)

    service_catalog = spicerack.service_catalog()
    assert isinstance(service_catalog, Catalog)
    assert spicerack.service_catalog() is service_catalog  # Returned the cached instance
    service_catalog_new = spicerack.service_catalog(refresh=True)
    assert isinstance(service_catalog_new, Catalog)
    assert service_catalog_new is not service_catalog
    assert spicerack.service_catalog() is service_catalog_new  # Returned the new cached instance

    assert isinstance(spicerack.apt_get(mock.MagicMock(spec_set=RemoteHosts)), AptGetHosts)
    assert isinstance(spicerack.orchestrator(), Orchestrator)
    assert isinstance(spicerack.lock(), NoLock)

    assert mocked_dns_resolver.Resolver.called

    with pytest.raises(AttributeError, match="AttributeError: 'Spicerack' object has no attribute 'nonexistent'"):
        # Test that non-existent accessors raise when there is no extender
        spicerack.nonexistent()


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

    assert spicerack.icinga_master_host().hosts == "icinga-server.example.com"
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

    assert isinstance(spicerack.puppet_master(), PuppetMaster)
    mocked_get_puppet_ca_hostname.assert_called_once_with()
    assert mocked_remote_query.called


@mock.patch("spicerack.get_ca_via_srv_record", return_value="puppetserver1001.example.org")
@mock.patch("spicerack.remote.Remote.query", autospec=True)
def test_spicerack_puppet_server(mocked_remote_query, mocked_get_ca_via_srv_record):
    """An instance of Spicerack should allow to get a PuppetServer instance."""
    host = mock.MagicMock(spec_set=RemoteHosts)
    host.__len__.return_value = 1
    mocked_remote_query.return_value = host
    spicerack = Spicerack(verbose=True, dry_run=False, **SPICERACK_TEST_PARAMS)

    assert isinstance(spicerack.puppet_server(), PuppetServer)
    assert mocked_remote_query.called
    assert mocked_get_ca_via_srv_record.called


@pytest.mark.parametrize(
    "manufacturer, manufacturer_class",
    (
        ("dell", RedfishDell),
        ("supermicro", RedfishSupermicro),
        ("fancy-but-not-supported-yet", None),
    ),
)
@mock.patch("spicerack.Netbox")
def test_spicerack_management_consoles(mocked_netbox, monkeypatch, manufacturer, manufacturer_class):
    """Should instantiate the instances that require the management password."""
    monkeypatch.setenv("MGMT_PASSWORD", "env_password")
    mocked_netbox.return_value.get_server.return_value.virtual = False
    mocked_netbox.return_value.api.ipam.ip_addresses.get.return_value.address = "10.0.0.1/16"
    mocked_netbox.return_value.get_server.return_value.as_dict.return_value = {
        "device_type": {"manufacturer": {"slug": manufacturer}}
    }

    spicerack = Spicerack(verbose=True, dry_run=False, **SPICERACK_TEST_PARAMS)

    assert spicerack.management_password() == "env_password"
    assert isinstance(spicerack.ipmi("test-mgmt.example.com"), Ipmi)
    if manufacturer == "fancy-but-not-supported-yet":
        with pytest.raises(
            SpicerackError, match=f"The manufacturer {manufacturer} set in Netbox for test-mgmt01 is not supported."
        ):
            spicerack.redfish("test-mgmt01")
    else:
        assert isinstance(spicerack.redfish("test-mgmt01"), manufacturer_class)
        assert isinstance(spicerack.redfish("test-mgmt01", "root", "other_password"), manufacturer_class)
        assert mocked_netbox.called


@mock.patch("spicerack.Netbox")
def test_spicerack_redfish_not_physical(mocked_netbox, monkeypatch):
    """Should raise a SpicerackError if trying to get a management console for a non-physical device."""
    monkeypatch.setenv("MGMT_PASSWORD", "env_password")
    mocked_netbox.return_value.get_server.return_value.virtual = True
    spicerack = Spicerack(verbose=True, dry_run=False, **SPICERACK_TEST_PARAMS)

    with pytest.raises(SpicerackError, match="Host test-mgmt01 is not a Physical server, Redfish is not supported"):
        spicerack.redfish("test-mgmt01")

    assert mocked_netbox.called


def test_spicerack_management_password_cached(monkeypatch):
    """Should ask for the management_password only once and cache its result."""
    monkeypatch.setenv("MGMT_PASSWORD", "first_password")
    spicerack = Spicerack(verbose=True, dry_run=False, **SPICERACK_TEST_PARAMS)
    assert spicerack.management_password() == "first_password"
    monkeypatch.setenv("MGMT_PASSWORD", "second_password")
    assert spicerack.management_password() == "first_password"


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
def test_spicerack_netbox_host(mocked_pynetbox, mocked_remote_query, mocked_dns, read_write, token):
    """Test instantiating Netbox abstraction and Host abstraction that depends on Netbox."""
    netbox_server = mock.MagicMock(spec_set=RemoteHosts)
    netbox_server.hosts = "netbox-server.example.com"
    mocked_remote_query.return_value = netbox_server
    mocked_dns.return_value.resolve_cname.return_value = "netbox-server.example.com"
    mocked_pynetbox.reset_mock()

    spicerack = Spicerack(verbose=True, dry_run=False, **SPICERACK_TEST_PARAMS)

    assert isinstance(spicerack.netbox(read_write=read_write), Netbox)
    # Values from fixtures/netbox/config.yaml
    mocked_pynetbox.assert_called_once_with("https://netbox.example.com", token=token, threading=True)
    assert spicerack.netbox_master_host().hosts == "netbox-server.example.com"

    mocked_pynetbox.reset_mock()
    del mocked_pynetbox.return_value.dcim.devices.get.return_value.device_role
    mocked_pynetbox.return_value.dcim.devices.get.return_value.role.slug = "server"
    assert isinstance(spicerack.netbox_server("host1"), NetboxServer)
    assert isinstance(spicerack.host("host1", netbox_read_write=read_write), Host)


@mock.patch("spicerack.remote.Remote.query", autospec=True)
def test_spicerack_dhcp_ok(mocked_remote_query):
    """It should return an instance of the DHCP class if created with the correct parameters."""
    mock_hosts = mock.MagicMock(spec_set=RemoteHosts)
    mock_hosts.__len__.return_value = 1
    mocked_remote_query.return_value = mock_hosts

    spicerack = Spicerack(verbose=True, dry_run=False, **SPICERACK_TEST_PARAMS)
    assert isinstance(spicerack.dhcp("codfw"), DHCP)
    assert mocked_remote_query.call_args.args[1] == "A:installserver and A:codfw"


@mock.patch("spicerack.remote.Remote.query", autospec=True)
def test_spicerack_dhcp_fallback(mocked_remote_query):
    """It should still create an instance of the DHCP class but fallback to eqiad if the query fails."""
    mock_hosts = mock.MagicMock(spec_set=RemoteHosts)
    mock_hosts.__len__.return_value = 1
    mocked_remote_query.side_effect = [RemoteError(), mock_hosts]

    spicerack = Spicerack(verbose=True, dry_run=False, **SPICERACK_TEST_PARAMS)
    assert isinstance(spicerack.dhcp("codfw"), DHCP)
    assert mocked_remote_query.call_args.args[1] == "A:installserver and A:eqiad"


def test_run_cookbook_no_callback():
    """It should raise a SpicerackError if there is no get_cookbook_callback defined."""
    spicerack = Spicerack(verbose=True, dry_run=False, **SPICERACK_TEST_PARAMS)
    with pytest.raises(SpicerackError, match="Unable to run other cookbooks, get_cookbook_callback is not set."):
        spicerack.run_cookbook("class_api.example", [])


def test_run_cookbook_raise():
    """It should raise a RunCookbookError if raises is set to True and the cookbook raises an exception."""
    get_cookbook = get_cookbook_callback([get_fixture_path("cookbook")])
    spicerack = Spicerack(verbose=True, dry_run=False, get_cookbook_callback=get_cookbook, **SPICERACK_TEST_PARAMS)
    with pytest.raises(
        RunCookbookError,
        match="run_cookbook returned exit code 99 when running cookbook group3.raise_exception with args",
    ):
        spicerack.run_cookbook("group3.raise_exception", [], raises=True)


@mock.patch("wmflib.interactive.ask_input", return_value="abort")
def test_run_cookbook_confirm(mocked_ask_input):
    """It should ask the user confirmation if confirm is set to True and the cookbook raises an exception."""
    get_cookbook = get_cookbook_callback([get_fixture_path("cookbook")])
    spicerack = Spicerack(verbose=True, dry_run=False, get_cookbook_callback=get_cookbook, **SPICERACK_TEST_PARAMS)
    with pytest.raises(AbortError, match="Task manually aborted"):
        spicerack.run_cookbook("group3.raise_exception", [], confirm=True)

    mocked_ask_input.assert_called_once()


@mock.patch("spicerack.Path.is_dir")
@mock.patch("spicerack.Repo")
def test_reposync(mocked_repo, mocked_is_dir):
    """Test spicerack.reposync."""
    spicerack = Spicerack(**SPICERACK_TEST_PARAMS)

    repo = mock.MagicMock(spec_set=Repo)
    repo.bare = False

    with pytest.raises(SpicerackError, match="Unknown repo missing_repo"):
        spicerack.reposync("missing_repo")

    mocked_is_dir.return_value = False
    with pytest.raises(SpicerackError, match=r"The repo directory \(/testrepo\) does not exist"):
        spicerack.reposync("testrepo")

    mocked_is_dir.return_value = True
    mocked_repo.return_value = repo
    with pytest.raises(SpicerackError, match=r"The repo directory \(/testrepo\) is not a bare git repository"):
        spicerack.reposync("testrepo")

    repo.bare = True
    assert isinstance(spicerack.reposync("testrepo"), RepoSync)


@mock.patch("spicerack.gethostname", return_value="test.example.com")
@mock.patch("spicerack.Dns", autospec=True)
@mock.patch("spicerack.remote.Remote.query", autospec=True)
@mock.patch("spicerack.icinga.CommandFile", autospec=True)
def test_spicerack_alerting(mocked_command_file, mocked_remote_query, mocked_dns, mocked_hostname, monkeypatch):
    """An instance of Spicerack should allow to get an AlertingHosts instance."""
    monkeypatch.setenv("SUDO_USER", "user1")
    icinga_server = mock.MagicMock(spec_set=RemoteHosts)
    icinga_server.hosts = "icinga-server.example.com"
    icinga_server.__len__.return_value = 1
    mocked_remote_query.return_value = icinga_server
    mocked_dns.return_value.resolve_cname.return_value = "icinga-server.example.com"
    mocked_command_file.return_value = "/var/lib/icinga/rw/icinga.cmd"

    spicerack = Spicerack(verbose=True, dry_run=False, **SPICERACK_TEST_PARAMS)

    assert spicerack.icinga_master_host().hosts == "icinga-server.example.com"
    assert isinstance(spicerack.alerting_hosts(["host1", "host2"]), AlertingHosts)
    mocked_hostname.assert_called_once_with()


@pytest.mark.parametrize("am_instance", (None, "production", "metricsinfra-eqiad1"))
def test_spicerack_alertmanager(am_instance):
    """An instance of Spicerack should allow to get an Alertmanager instance."""
    spicerack = Spicerack(
        verbose=True, dry_run=False, http_proxy="http://webproxy.eqiad.example:8080", **SPICERACK_TEST_PARAMS
    )

    config = load_yaml_config(spicerack.config_dir / "alertmanager" / "config.yaml")
    instance = config.get("instances").get(am_instance if am_instance else config.get("default_instance"))
    urls = instance.get("urls")

    http_authentication = None
    if "http_username" in instance and "http_password" in instance:
        http_authentication = HTTPBasicAuth(username=instance["http_username"], password=instance["http_password"])
    http_proxy = "http://webproxy.eqiad.example:8080" if instance.get("http_use_proxy") else None

    instance = spicerack.alertmanager(instance_name=am_instance)

    assert isinstance(instance, Alertmanager)
    assert instance._alertmanager_urls == urls  # pylint: disable=protected-access
    assert instance._http_session.auth == http_authentication  # pylint: disable=protected-access
    assert instance._http_session.proxies.get("http") == http_proxy  # pylint: disable=protected-access

    hosts_instance = spicerack.alertmanager_hosts(["host1", "host2"], instance_name=am_instance)
    assert isinstance(hosts_instance, AlertmanagerHosts)
    assert hosts_instance._alertmanager_urls == urls  # pylint: disable=protected-access
    assert hosts_instance._http_session.auth == http_authentication  # pylint: disable=protected-access
    assert hosts_instance._http_session.proxies.get("http") == http_proxy  # pylint: disable=protected-access


def test_spicerack_alertmanager_invalid_instance():
    """An instance of Spicerack should throw an error when given a nonexistent Alertmanager instance name."""
    spicerack = Spicerack(verbose=True, dry_run=False, **SPICERACK_TEST_PARAMS)
    with pytest.raises(SpicerackError):
        spicerack.alertmanager("nonexistent")


@pytest.mark.parametrize("am_instance", ("hosts-missing", "hosts-empty"))
def test_spicerack_alertmanager_instance_without_hosts(am_instance):
    """An instance of Spicerack should throw an error when given an Alertmanager instance with no hosts."""
    spicerack = Spicerack(verbose=True, dry_run=False, **SPICERACK_TEST_PARAMS)
    with pytest.raises(SpicerackError):
        spicerack.alertmanager(am_instance)


@mock.patch("spicerack.load_yaml_config")
def test_spicerack_alertmanager_no_default_instance(mocked_load_yaml_config):
    """An instance of Spicerack should throw an error when trying to access a non-configured default instance."""
    spicerack = Spicerack(verbose=True, dry_run=False, **SPICERACK_TEST_PARAMS)

    mocked_load_yaml_config.return_value = {"instances": {"nondefault": {"urls": ["https://alertmanager.example"]}}}

    with pytest.raises(SpicerackError):
        spicerack.alertmanager()


@pytest.mark.parametrize("ttl", (None, 3600))
@pytest.mark.parametrize("api_token_ro", ("", "sometoken"))
@pytest.mark.parametrize("cachedir", (None, ""))
@mock.patch("spicerack.load_yaml_config")
def test_spicerack_peeringdb(mocked_load_yaml_config, cachedir, api_token_ro, ttl, tmp_path):
    """An instance of Spicerack should allow to get a PeeringDB instance."""
    spicerack = Spicerack(verbose=True, dry_run=False, **SPICERACK_TEST_PARAMS)

    config = {}
    if api_token_ro:
        config["api_token_ro"] = api_token_ro
    if cachedir is not None:
        config["cachedir"] = str(tmp_path)
    mocked_load_yaml_config.return_value = config

    if ttl is not None:
        instance = spicerack.peeringdb(ttl=ttl)
    else:
        instance = spicerack.peeringdb()

    assert isinstance(instance, PeeringDB)


def test_spicerack_extender():
    """An instance of Spicerack with an extender should allow to access the extender accessors."""
    sys.path.append(str(get_fixture_path("external_modules")))
    loader_module = import_module("spicerack_extender")
    spicerack = Spicerack(extender_class=getattr(loader_module, "SpicerackExtender"), **SPICERACK_TEST_PARAMS)

    assert str(spicerack.cool_feature("Extender")) == "Extender is a cool feature!"

    with pytest.raises(AttributeError, match="'SpicerackExtender' object has no attribute 'nonexistent'"):
        # Test that non-existent accessors raise when there is an extender.
        spicerack.nonexistent()


def test_spicerack_lock(monkeypatch):
    """It should return an instance of spicerack.locking.Lock."""
    monkeypatch.setenv("USER", "")
    spicerack = Spicerack(etcd_config=get_fixture_path("locking", "config.yaml"), **SPICERACK_TEST_PARAMS)
    assert isinstance(spicerack.lock(), Lock)


def test_spicerack_private_lock():
    """It should return a lock instance for the spicerack modules and also cache it for re-use."""
    Spicerack.test_accessor = lambda self: getattr(self, "_spicerack_lock")
    spicerack = Spicerack(**SPICERACK_TEST_PARAMS)

    lock_1 = spicerack.test_accessor()
    lock_2 = spicerack.test_accessor()
    assert isinstance(lock_1, NoLock)
    assert lock_1 is lock_2  # Test that it returns the cached object
