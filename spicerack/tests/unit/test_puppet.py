"""Puppet module tests."""

import json
import re
from collections import namedtuple
from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest
from ClusterShell.MsgTree import MsgTreeElem
from cumin import nodeset

from spicerack import puppet
from spicerack.administrative import Reason
from spicerack.exceptions import SpicerackError
from spicerack.remote import RemoteExecutionError, RemoteHosts

REASON = Reason("Disable reason", "user1", "orchestration-host", task_id="T12345")
PUPPET_SERVER_CA_CERT_METADATA_SIGNED = (
    b'{"signed": [{"name":"test.example.com","state":"signed","fingerprint":"00:AA",'
    b'"fingerprints":{"default":"00:AA","SHA1":"11:BB","SHA256": "00:AA","SHA512":"22:CC"},'
    b'"dns_alt_names":["DNS:service.example.com"]}]}'
)
PUPPET_SERVER_CA_CERT_METADATA_REQUESTED = (
    b'{"signed": [{"name":"test.example.com","state":"requested","fingerprint":"00:AA",'
    b'"fingerprints":{"default":"00:AA","SHA1":"11:BB","SHA256": "00:AA","SHA512":"22:CC"},'
    b'"dns_alt_names":["DNS:service.example.com"]}]}'
)
PUPPET_SERVER_CA_CERT_METADATA_MISSING = b'{"missing": ["test.example.org"]}'
PUPPET_CA_CERT_METADATA_SIGNED = (
    b'[{"name":"test.example.com","state":"signed","fingerprint":"00:AA",'
    b'"fingerprints":{"default":"00:AA","SHA1":"11:BB","SHA256": "00:AA","SHA512":"22:CC"},'
    b'"dns_alt_names":["DNS:service.example.com"]}]'
)
PUPPET_CA_CERT_METADATA_REQUESTED = (
    b'[{"name":"test.example.com","state":"requested","fingerprint":"00:AA",'
    b'"fingerprints":{"default":"00:AA","SHA1":"11:BB","SHA256": "00:AA","SHA512":"22:CC"},'
    b'"dns_alt_names":["DNS:service.example.com"]}]'
)
PUPPET_GENERATE_CERTIFICATE_SUCCESS = b"""Info: Creating a new SSL key for test.example.com
Info: Caching certificate for ca
Info: csr_attributes file loading from /etc/puppet/csr_attributes.yaml
Info: Creating a new SSL certificate request for test.example.com
Info: Certificate Request fingerprint (SHA256): 00:FF
Info: Caching certificate for ca
Exiting; no certificate found and waitforcert is disabled
"""
PUPPET_GENERATE_CERTIFICATE_FAILED = rb"""Info: Creating a new SSL key for test.example.com
Info: Caching certificate for ca
Info: Caching certificate for test.example.com
Error: Could not request certificate: The certificate retrieved from the master does not match the agent's private key.
Certificate fingerprint: 00:FF
To fix this, remove the certificate from both the master and the agent and then start a puppet run, which will...
On the master:
  puppet cert clean test.example.com
On the agent:
  1a. On most platforms: find /var/lib/puppet/ssl -name test.example.com.pem -delete
  1b. On Windows: del "\var\lib\puppet\ssl\certs\test.example.com.pem" /f
  2. puppet agent -t
Exiting; failed to retrieve certificate and waitforcert is disabled
"""

MockedDnsSrv = namedtuple("MockedDnsSrv", ["target"])
MockedDnsAnswer = namedtuple("MockedDnsAnswer", ["ttl", "rrset"])


@mock.patch("spicerack.puppet.Dns", autospec=True)
def test_get_ca_via_srv_record(mocked_dns_resolve):
    """An instance of Spicerack should allow to get a PuppetServer instance."""
    dns_answer = MockedDnsAnswer(ttl=600, rrset=[MockedDnsSrv(target="puppetserver1001.eqiad.wmnet")])
    mocked_dns_resolve.return_value.resolve.return_value = dns_answer
    assert puppet.get_ca_via_srv_record("eqiad.wmnet") == "puppetserver1001.eqiad.wmnet"


@pytest.mark.parametrize(
    "response, err_msg",
    (
        (
            MockedDnsAnswer(ttl=600, rrset=None),
            "Unable to find record for _x-puppet-ca._tcp.eqiad.wmnet",
        ),
        (
            MockedDnsAnswer(ttl=600, rrset=[]),
            "Unable to find record for _x-puppet-ca._tcp.eqiad.wmnet",
        ),
        (
            MockedDnsAnswer(ttl=600, rrset=[MockedDnsSrv(target="foo"), MockedDnsSrv(target="bar")]),
            "_x-puppet-ca._tcp.eqiad.wmnet returned multiple ca servers: foo,bar",
        ),
    ),
)
@mock.patch("spicerack.puppet.Dns", autospec=True)
def test_get_ca_via_srv_record_raises(mocked_dns_resolve, response, err_msg):
    """An instance of Spicerack should allow to get a PuppetServer instance."""
    mocked_dns_resolve.return_value.resolve.return_value = response
    with pytest.raises(SpicerackError, match=err_msg):
        puppet.get_ca_via_srv_record("eqiad.wmnet")
    mocked_dns_resolve.assert_called_once()


def test_get_puppet_ca_hostname_ok():
    """It should get the hostname of the Puppet CA from the local Puppet agent."""
    assert puppet.get_puppet_ca_hostname() == "puppetmaster1001.eqiad.wmnet"


class TestPuppetHosts:
    """Test class for the PuppetHosts class."""

    def setup_method(self):
        """Setup the test environment."""
        # pylint: disable=attribute-defined-outside-init
        self.mocked_remote_hosts = mock.MagicMock(spec_set=RemoteHosts)
        self.mocked_remote_hosts.__len__.return_value = 1
        self.puppet_hosts = puppet.PuppetHosts(self.mocked_remote_hosts)

    @pytest.mark.parametrize(
        "verbatim_reason, result",
        ((False, f"disable-puppet {REASON.quoted()}"), (True, f'disable-puppet "{REASON.reason}"')),
    )
    def test_disable(self, verbatim_reason, result):
        """It should disable Puppet on the hosts."""
        self.puppet_hosts.disable(REASON, verbatim_reason)
        self.mocked_remote_hosts.run_sync.assert_called_once_with(result)

    @pytest.mark.parametrize(
        "verbatim_reason, result",
        ((False, f"enable-puppet {REASON.quoted()}"), (True, f'enable-puppet "{REASON.reason}"')),
    )
    def test_enable(self, verbatim_reason, result):
        """It should enable Puppet on the hosts."""
        self.puppet_hosts.enable(REASON, verbatim_reason)
        self.mocked_remote_hosts.run_sync.assert_called_once_with(result)

    @pytest.mark.parametrize("verbatim_reason, result", ((False, REASON.quoted()), (True, f'"{REASON.reason}"')))
    def test_disabled(self, verbatim_reason, result):
        """It should disable Puppet, yield and enable Puppet on the hosts."""
        with self.puppet_hosts.disabled(REASON, verbatim_reason):
            self.mocked_remote_hosts.run_sync.assert_called_once_with(f"disable-puppet {result}")
            self.mocked_remote_hosts.run_sync.reset_mock()

        self.mocked_remote_hosts.run_sync.assert_called_once_with(f"enable-puppet {result}")

    def test_disabled_on_raise(self):
        """It should re-enable Puppet even if the yielded code raises exception.."""
        with pytest.raises(RuntimeError):
            with self.puppet_hosts.disabled(REASON):
                self.mocked_remote_hosts.run_sync.reset_mock()
                raise RuntimeError("Error")

        self.mocked_remote_hosts.run_sync.assert_called_once_with(f"enable-puppet {REASON.quoted()}")

    def test_check_enabled_ok(self):
        """It should check that all hosts have Puppet enabled."""
        host1 = nodeset("test1.example.com")
        host2 = nodeset("test2.example.com")
        results = [
            (host1, MsgTreeElem(b"0", parent=MsgTreeElem())),
            (host2, MsgTreeElem(b"0", parent=MsgTreeElem())),
        ]
        self.mocked_remote_hosts.run_sync.return_value = iter(results)
        self.puppet_hosts.check_enabled()

    def test_check_enabled_raise(self):
        """It should raise PuppetHostsCheckError if Puppet is disabled on some hosts."""
        host1 = nodeset("test1.example.com")
        host2 = nodeset("test2.example.com")
        results = [
            (host1, MsgTreeElem(b"0", parent=MsgTreeElem())),
            (host2, MsgTreeElem(b"1", parent=MsgTreeElem())),
        ]
        self.mocked_remote_hosts.run_sync.return_value = iter(results)
        with pytest.raises(
            puppet.PuppetHostsCheckError,
            match="Puppet is not enabled on those hosts: test2.example.com",
        ):
            self.puppet_hosts.check_enabled()

    def test_check_disabled_ok(self):
        """It should check that all hosts have Puppet disabled."""
        host1 = nodeset("test1.example.com")
        host2 = nodeset("test2.example.com")
        results = [
            (host1, MsgTreeElem(b"1", parent=MsgTreeElem())),
            (host2, MsgTreeElem(b"1", parent=MsgTreeElem())),
        ]
        self.mocked_remote_hosts.run_sync.return_value = iter(results)
        self.puppet_hosts.check_disabled()

    def test_check_disabled_raise(self):
        """It should raise PuppetHostsCheckError if Puppet is disabled on some hosts."""
        host1 = nodeset("test1.example.com")
        host2 = nodeset("test2.example.com")
        results = [
            (host1, MsgTreeElem(b"1", parent=MsgTreeElem())),
            (host2, MsgTreeElem(b"0", parent=MsgTreeElem())),
        ]
        self.mocked_remote_hosts.run_sync.return_value = iter(results)
        with pytest.raises(
            puppet.PuppetHostsCheckError,
            match="Puppet is not disabled on those hosts: test2.example.com",
        ):
            self.puppet_hosts.check_disabled()

    @pytest.mark.parametrize(
        "kwargs, expected",
        (
            ({}, ""),
            ({"enable_reason": REASON}, "--enable " + REASON.quoted()),
            ({"quiet": True}, "--quiet"),
            ({"failed_only": True}, "--failed-only"),
            ({"force": True}, "--force"),
            ({"attempts": 5}, "--attempts 5"),
        ),
    )
    def test_run_ok(self, kwargs, expected):
        """It should run Puppet with the specified arguments."""
        self.puppet_hosts.run(**kwargs)
        self.mocked_remote_hosts.run_sync.assert_called_once_with(
            puppet.Command(f"run-puppet-agent {expected}".strip(), timeout=300.0),
            batch_size=10,
        )

    def test_run_timeout(self):
        """It should run Puppet with the customized timeout."""
        self.puppet_hosts.run(timeout=30)
        self.mocked_remote_hosts.run_sync.assert_called_once_with(
            puppet.Command("run-puppet-agent ", timeout=30.0), batch_size=10
        )

    def test_first_run(self):
        """It should enable and Puppet with a very long timeout without using custom wrappers."""
        self.puppet_hosts.first_run()
        self.mocked_remote_hosts.run_sync.assert_called_once_with(
            "systemctl stop puppet.service",
            "systemctl reset-failed puppet.service || true",
            "puppet agent --enable",
            puppet.Command(
                "puppet agent --onetime --no-daemonize --verbose --no-splay --show_diff --no-usecacheonfailure",
                timeout=10800,
            ),
            print_output=False,
            print_progress_bars=False,
        )

    def test_first_run_not_systemd(self):
        """It should enable and Puppet with a very long timeout without using custom wrappers."""
        self.puppet_hosts.first_run(has_systemd=False)
        self.mocked_remote_hosts.run_sync.assert_called_once_with(
            "puppet agent --enable",
            puppet.Command(
                "puppet agent --onetime --no-daemonize --verbose --no-splay --show_diff --no-usecacheonfailure",
                timeout=10800,
            ),
            print_output=False,
            print_progress_bars=False,
        )

    def test_regenerate_certificate_ok(self):
        """It should delete and regenerate the Puppet certificate."""
        results = [
            (
                nodeset("test.example.com"),
                MsgTreeElem(PUPPET_GENERATE_CERTIFICATE_SUCCESS, parent=MsgTreeElem()),
            )
        ]
        self.mocked_remote_hosts.run_sync.side_effect = [iter(()), iter(results)]

        fingerprints = self.puppet_hosts.regenerate_certificate()

        self.mocked_remote_hosts.run_sync.assert_has_calls(
            [
                mock.call("rm -rfv /var/lib/puppet/ssl"),
                mock.call(puppet.Command("puppet agent --test --color=false", ok_codes=[]), print_output=False),
            ]
        )
        assert fingerprints == {"test.example.com": "00:FF"}

    def test_regenerate_certificate_raise(self):
        """It should raise PuppetHostsError if unable to find any of the fingerprint."""
        message = PUPPET_GENERATE_CERTIFICATE_SUCCESS.decode().replace(": 00:FF", "").encode()
        results = [(nodeset("test.example.com"), MsgTreeElem(message, parent=MsgTreeElem()))]
        self.mocked_remote_hosts.run_sync.side_effect = [iter(()), iter(results)]

        with pytest.raises(
            puppet.PuppetHostsError,
            match="Unable to find CSR fingerprints for all hosts",
        ):
            self.puppet_hosts.regenerate_certificate()

    def test_regenerate_certificate_errors(self):
        """It should raise PuppetHostsError and print the Puppet errors if unable to find any of the fingerprint."""
        results = [
            (
                nodeset("test.example.com"),
                MsgTreeElem(PUPPET_GENERATE_CERTIFICATE_FAILED, parent=MsgTreeElem()),
            )
        ]
        self.mocked_remote_hosts.run_sync.side_effect = [iter(()), iter(results)]

        with pytest.raises(
            puppet.PuppetHostsError,
            match=(
                "test.example.com: Error: Could not request certificate: The certificate retrieved "
                "from the master does not match the agent's private key."
            ),
        ):
            self.puppet_hosts.regenerate_certificate()

    def test_wait_since_ok(self):
        """It should return immediately if there is already successful Puppet run since the given datetime."""
        last_run = datetime.utcnow()
        # timestamp() consider naive datetime objects as local time.
        last_run_string = str(int(last_run.replace(tzinfo=timezone.utc).timestamp()))
        start = last_run - timedelta(seconds=1)

        nodes = nodeset("test.example.com")
        results = [(nodes, MsgTreeElem(last_run_string.encode(), parent=MsgTreeElem()))]
        self.mocked_remote_hosts.run_sync.return_value = iter(results)
        self.mocked_remote_hosts.hosts = nodes

        self.puppet_hosts.wait_since(start)

        self.mocked_remote_hosts.run_sync.assert_called_once_with(
            (
                "source /usr/local/share/bash/puppet-common.sh && last_run_success && awk /last_run/'{ print $2 }' "
                '"${PUPPET_SUMMARY}"'
            ),
            is_safe=True,
            print_output=False,
            print_progress_bars=False,
        )

    # TODO: check why the following test_wait_since_* tests take longer (~4s each) when running the whole suite but are
    # quick if running only tests in this module (tox -e py34-unit -- -k test_puppet)
    @mock.patch("wmflib.decorators.time.sleep", return_value=None)
    def test_wait_since_timeout(self, mocked_sleep):
        """It should raise PuppetHostsCheckError if the successful Puppet run is too old within the timeout."""
        last_run = datetime.utcnow()
        # timestamp() consider naive datetime objects as local time.
        last_run_string = str(int(last_run.replace(tzinfo=timezone.utc).timestamp()))
        start = last_run + timedelta(seconds=1)

        nodes = nodeset("test.example.com")
        results = [(nodes, MsgTreeElem(last_run_string.encode(), parent=MsgTreeElem()))]
        self.mocked_remote_hosts.run_sync.side_effect = [results] * 60
        self.mocked_remote_hosts.hosts = nodes

        with pytest.raises(puppet.PuppetHostsCheckError, match="Successful Puppet run too old"):
            self.puppet_hosts.wait_since(start)

        assert mocked_sleep.called

    @mock.patch("wmflib.decorators.time.sleep", return_value=None)
    def test_wait_since_failed_execution(self, mocked_sleep):
        """It should raise PuppetHostsCheckError if fails to get the successful Puppet run within the timeout."""
        self.mocked_remote_hosts.run_sync.side_effect = RemoteExecutionError(1, "fail", iter(()))
        self.mocked_remote_hosts.hosts = nodeset("test.example.com")

        with pytest.raises(puppet.PuppetHostsCheckError, match="Unable to find a successful Puppet run"):
            self.puppet_hosts.wait_since(datetime.utcnow())

        assert mocked_sleep.called

    @mock.patch("wmflib.decorators.time.sleep", return_value=None)
    def test_wait_since_missing_host(self, mocked_sleep):
        """It should raise PuppetHostsCheckError unable to get the result from some host."""
        last_run = datetime.utcnow()
        # timestamp() consider naive datetime objects as local time.
        last_run_string = str(int(last_run.replace(tzinfo=timezone.utc).timestamp()))
        start = last_run - timedelta(seconds=1)

        nodes = nodeset("test[1-2].example.com")
        results = [
            (
                nodeset("test1.example.com"),
                MsgTreeElem(last_run_string.encode(), parent=MsgTreeElem()),
            )
        ]
        self.mocked_remote_hosts.run_sync.side_effect = [results] * 60
        self.mocked_remote_hosts.hosts = nodes

        with pytest.raises(
            puppet.PuppetHostsCheckError,
            match="Unable to get successful Puppet run from: test2.example.com",
        ):
            self.puppet_hosts.wait_since(start)

        assert mocked_sleep.called

    def test_wait_ok(self):
        """It should return immediately if there is already successful Puppet run since now."""
        last_run = datetime.utcnow() + timedelta(seconds=1)
        # timestamp() consider naive datetime objects as local time.
        last_run_string = str(int(last_run.replace(tzinfo=timezone.utc).timestamp()))

        nodes = nodeset("test.example.com")
        results = [(nodes, MsgTreeElem(last_run_string.encode(), parent=MsgTreeElem()))]
        self.mocked_remote_hosts.run_sync.return_value = iter(results)
        self.mocked_remote_hosts.hosts = nodes

        self.puppet_hosts.wait()

        self.mocked_remote_hosts.run_sync.assert_called_once_with(
            (
                "source /usr/local/share/bash/puppet-common.sh && last_run_success && awk /last_run/'{ print $2 }' "
                '"${PUPPET_SUMMARY}"'
            ),
            is_safe=True,
            print_output=False,
            print_progress_bars=False,
        )

    @pytest.mark.parametrize(
        "get_config_return, puppethost_side_effect",
        (
            (
                {"test1001.example.org": "true", "test1002.example.org": "true", "test1003.example.org": "false"},
                [
                    {"test1001.example.org": "eqiad.wmnet", "test1002.example.org": "codfw.wmnet"},
                    {"test1003.example.org": "dummy.puppetmast.er"},
                ],
            ),
            (
                {"test1001.example.org": "true", "test1002.example.org": "true", "test1003.example.org": "true"},
                [
                    {
                        "test1001.example.org": "eqiad.wmnet",
                        "test1002.example.org": "codfw.wmnet",
                        "test1003.example.org": "eqiad.wmnet",
                    },
                ],
            ),
            (
                {"test1001.example.org": "false", "test1002.example.org": "false", "test1003.example.org": "false"},
                [
                    {
                        "test1001.example.org": "dummy.puppetmast.er",
                        "test1002.example.org": "dummy.puppetmast.er",
                        "test1003.example.org": "dummy.puppetmast.er",
                    },
                ],
            ),
        ),
    )
    @mock.patch("spicerack.puppet.get_ca_via_srv_record")
    @mock.patch("spicerack.puppet.PuppetHosts")
    @mock.patch("spicerack.puppet.PuppetHosts.get_config")
    def test_get_ca_servers(
        self,
        mocked_get_config,
        mocked_puppet_hosts,
        mocked_get_ca_via_srv_record,
        get_config_return,
        puppethost_side_effect,
    ):
        """Test that get ca servers explodes multihost nodeset into single hosts."""
        expected_puppetmaster = "dummy.puppetmast.er"
        mocked_get_config.return_value = get_config_return
        mocked_puppet_hosts.return_value.get_config.side_effect = puppethost_side_effect
        mocked_get_ca_via_srv_record.return_value = expected_puppetmaster

        check_srv_domains = any(v == "true" for v in get_config_return)
        check_ca_server = any(v == "false" for v in get_config_return)

        result = self.puppet_hosts.get_ca_servers()

        mocked_get_config.assert_called_once_with("use_srv_records")
        if check_srv_domains:
            mocked_puppet_hosts.return_value.get_config.assert_any_call("srv_domain")
        if check_ca_server:
            mocked_puppet_hosts.return_value.get_config.assert_any_call("ca_server")

        assert "test1001.example.org" in result
        assert result["test1001.example.org"] == expected_puppetmaster
        assert "test1002.example.org" in result
        assert result["test1002.example.org"] == expected_puppetmaster
        assert "test1003.example.org" in result
        assert result["test1003.example.org"] == expected_puppetmaster

    def test_get_config_explodes_multihost_nodeset_into_single_hosts(self):
        """Test that get ca servers explodes multihost nodeset into single hosts."""
        expected_puppetmaster = "dummy.puppetmast.er"
        self.mocked_remote_hosts.run_sync.return_value = [
            (
                nodeset("test[0-1].example.com"),
                MsgTreeElem(expected_puppetmaster.encode(), parent=MsgTreeElem()),
            ),
        ]
        result = self.puppet_hosts.get_config("ca_server")
        self.mocked_remote_hosts.run_sync.assert_called_once()
        assert "test0.example.com" in result
        assert result["test0.example.com"] == expected_puppetmaster
        assert "test1.example.com" in result
        assert result["test1.example.com"] == expected_puppetmaster

    def test_get_config_handles_empty_result(self):
        """Test that get ca servers handles empty result."""
        self.mocked_remote_hosts.run_sync.return_value = []
        result = self.puppet_hosts.get_config("ca_server")
        self.mocked_remote_hosts.run_sync.assert_called_once()
        assert result == {}  # pylint: disable=use-implicit-booleaness-not-comparison

    def test_get_config_handles_multiple_results(self):
        """Test test get ca servers handles multiple results."""
        self.mocked_remote_hosts.run_sync.return_value = [
            (
                nodeset("test0.example.com"),
                MsgTreeElem(b"test0.puppetmast.er", parent=MsgTreeElem()),
            ),
            (
                nodeset("test1.example.com"),
                MsgTreeElem(b"test1.puppetmast.er", parent=MsgTreeElem()),
            ),
        ]
        result = self.puppet_hosts.get_config("ca_server")
        self.mocked_remote_hosts.run_sync.assert_called_once()
        assert "test0.example.com" in result
        assert result["test0.example.com"] == "test0.puppetmast.er"
        assert "test1.example.com" in result
        assert result["test1.example.com"] == "test1.puppetmast.er"

    def test_get_config_handles_multiple_lines_in_command_output(self):
        """Test test get ca servers handles multiple results."""
        self.mocked_remote_hosts.run_sync.return_value = [
            (
                nodeset("test0.example.com"),
                MsgTreeElem(
                    b"test0.puppetmast.er",
                    parent=MsgTreeElem(b"some message that should be ignored", parent=MsgTreeElem()),
                ),
            ),
        ]
        result = self.puppet_hosts.get_config("ca_server")
        self.mocked_remote_hosts.run_sync.assert_called_once()
        assert "test0.example.com" in result
        assert result["test0.example.com"] == "test0.puppetmast.er"


class TestPuppetServer:
    """Test class for the PuppetServer class."""

    def setup_method(self):
        """Setup the test environment."""
        # pylint: disable=attribute-defined-outside-init
        self.mocked_server_host = mock.MagicMock(spec_set=RemoteHosts)
        self.mocked_server_host.__len__.return_value = 1
        self.puppet_server = puppet.PuppetServer(self.mocked_server_host)

    def test_init_raise(self):
        """It should raise PuppetServerError if the Puppet master host instance doesn't match one host."""
        self.mocked_server_host.__len__.return_value = 2
        with pytest.raises(
            puppet.PuppetServerError,
            match="The server_host instance must target only one host, got 2",
        ):
            puppet.PuppetServer(self.mocked_server_host)

    def test_delete(self):
        """It should delete the host from Puppet master and PuppetDB."""
        self.puppet_server.delete("test.example.com")
        self.mocked_server_host.run_sync.assert_called_once_with(
            "puppet node clean test.example.com", "puppet node deactivate test.example.com", print_progress_bars=False
        )

    def test_destroy_ok(self):
        """It should delete the certificate of the host in the Puppet CA."""
        results = [
            (
                nodeset("puppetserver.example.com"),
                MsgTreeElem(PUPPET_SERVER_CA_CERT_METADATA_SIGNED, parent=MsgTreeElem()),
            )
        ]
        self.mocked_server_host.run_sync.return_value = iter(results)

        self.puppet_server.destroy("test.example.com")
        self.mocked_server_host.run_sync.assert_called_with(
            "puppetserver ca clean --certname test.example.com", print_progress_bars=False
        )

    def test_destroy_missing(self):
        """It should not do anything if the certificate of the host in the Puppet CA is alredy missing."""
        results = [
            (
                nodeset("puppetserver.example.com"),
                MsgTreeElem(PUPPET_SERVER_CA_CERT_METADATA_MISSING, parent=MsgTreeElem()),
            )
        ]
        self.mocked_server_host.run_sync.return_value = iter(results)

        self.puppet_server.destroy("test.example.com")

        for call in self.mocked_server_host.mock_calls:
            if call.args and "ca clean" in call.args[0]:
                raise RuntimeError(f"Expected ca clean to not be called, got: {call}")

    def test_verify_ok(self):
        """It should verify that the host has a signed certificate in the Puppet CA."""
        results = [
            (
                nodeset("puppetserver.example.com"),
                MsgTreeElem(PUPPET_SERVER_CA_CERT_METADATA_SIGNED, parent=MsgTreeElem()),
            )
        ]
        self.mocked_server_host.run_sync.return_value = iter(results)

        assert self.puppet_server.verify("test.example.com") is None

        self.mocked_server_host.run_sync.assert_has_calls(
            [
                mock.call(
                    "puppetserver ca list --format json --certname test.example.com",
                    is_safe=True,
                    print_output=False,
                    print_progress_bars=False,
                ),
            ]
        )

    def test_verify_raise(self):
        """It should raise PuppetServerError if the certificate is not valid on the Puppet CA."""
        results = [
            (
                nodeset("puppetserver.example.com"),
                MsgTreeElem(PUPPET_SERVER_CA_CERT_METADATA_REQUESTED, parent=MsgTreeElem()),
            )
        ]
        self.mocked_server_host.run_sync.return_value = iter(results)

        with pytest.raises(
            puppet.PuppetServerError, match="Expected certificate for test.example.com to be signed, got: requested"
        ):
            self.puppet_server.verify("test.example.com")

        self.mocked_server_host.run_sync.assert_has_calls(
            [
                mock.call(
                    "puppetserver ca list --format json --certname test.example.com",
                    is_safe=True,
                    print_output=False,
                    print_progress_bars=False,
                ),
            ]
        )

    def test_sign_ok(self):
        """It should sign the certificate in the Puppet CA."""
        requested_results = [
            (
                nodeset("puppetserver.example.com"),
                MsgTreeElem(PUPPET_SERVER_CA_CERT_METADATA_REQUESTED, parent=MsgTreeElem()),
            )
        ]
        signed_results = [
            (
                nodeset("puppetserver.example.com"),
                MsgTreeElem(PUPPET_SERVER_CA_CERT_METADATA_SIGNED, parent=MsgTreeElem()),
            )
        ]
        self.mocked_server_host.run_sync.side_effect = [
            iter(requested_results),
            iter(()),
            iter(signed_results),
        ]

        self.puppet_server.sign("test.example.com", "00:AA")

        self.mocked_server_host.run_sync.assert_has_calls(
            [
                mock.call(
                    "puppetserver ca list --format json --certname test.example.com",
                    is_safe=True,
                    print_output=False,
                    print_progress_bars=False,
                ),
                mock.call(
                    "puppetserver ca sign --certname test.example.com",
                    print_output=False,
                    print_progress_bars=False,
                ),
                mock.call(
                    "puppetserver ca list --format json --certname test.example.com",
                    is_safe=True,
                    print_output=False,
                    print_progress_bars=False,
                ),
            ]
        )

    def test_sign_wrong_state(self):
        """It should raise PuppetServerError if the certificate is not in the requested state."""
        results = [
            (
                nodeset("puppetserver.example.com"),
                MsgTreeElem(PUPPET_SERVER_CA_CERT_METADATA_SIGNED, parent=MsgTreeElem()),
            )
        ]
        self.mocked_server_host.run_sync.return_value = iter(results)

        with pytest.raises(
            puppet.PuppetServerError,
            match="Certificate for test.example.com not in requested state, got: signed",
        ):
            self.puppet_server.sign("test.example.com", "00:AA")

    def test_sign_wrong_fingerprint(self):
        """It should raise PuppetServerError if the fingerprint doesn't match the one in the CSR."""
        results = [
            (
                nodeset("puppetserver.example.com"),
                MsgTreeElem(PUPPET_SERVER_CA_CERT_METADATA_REQUESTED, parent=MsgTreeElem()),
            )
        ]
        self.mocked_server_host.run_sync.return_value = iter(results)

        with pytest.raises(
            puppet.PuppetServerError,
            match="CSR fingerprint 00:AA for test.example.com does not match provided fingerprint FF:FF",
        ):
            self.puppet_server.sign("test.example.com", "FF:FF")

    def test_sign_fail(self):
        """It should raise PuppetServerError if the sign operation fails."""
        requested_results = [
            (
                nodeset("puppetserver.example.com"),
                MsgTreeElem(PUPPET_SERVER_CA_CERT_METADATA_REQUESTED, parent=MsgTreeElem()),
            )
        ]
        sign_results = [
            (
                nodeset("puppetserver.example.com"),
                MsgTreeElem(b"sign error", parent=MsgTreeElem()),
            )
        ]
        signed_results = [
            (
                nodeset("puppetserver.example.com"),
                MsgTreeElem(PUPPET_SERVER_CA_CERT_METADATA_REQUESTED, parent=MsgTreeElem()),
            )
        ]
        self.mocked_server_host.run_sync.side_effect = [
            iter(requested_results),
            iter(sign_results),
            iter(signed_results),
        ]

        with pytest.raises(
            puppet.PuppetServerError,
            match="Expected certificate for test.example.com to be signed, got: requested",
        ):
            self.puppet_server.sign("test.example.com", "00:AA")

    def test_wait_for_csr_already_ok(self):
        """It should return immediately if the certificate is already requested."""
        results = [
            (
                nodeset("puppetserver.example.com"),
                MsgTreeElem(PUPPET_SERVER_CA_CERT_METADATA_REQUESTED, parent=MsgTreeElem()),
            )
        ]
        self.mocked_server_host.run_sync.return_value = iter(results)

        self.puppet_server.wait_for_csr("test.example.com")

        self.mocked_server_host.run_sync.assert_called_once_with(
            "puppetserver ca list --format json --certname test.example.com",
            is_safe=True,
            print_output=False,
            print_progress_bars=False,
        )

    def test_wait_for_csr_fail(self):
        """It should raise PuppetServerError if the certificate is in a wrong state."""
        results = [
            (
                nodeset("puppetserver.example.com"),
                MsgTreeElem(PUPPET_SERVER_CA_CERT_METADATA_SIGNED, parent=MsgTreeElem()),
            )
        ]
        self.mocked_server_host.run_sync.return_value = iter(results)

        with pytest.raises(
            puppet.PuppetServerError,
            match="Expected certificate in requested state, got: signed",
        ):
            self.puppet_server.wait_for_csr("test.example.com")

    @mock.patch("wmflib.decorators.time.sleep", return_value=None)
    def test_wait_for_csr_timeout(self, mocked_sleep):
        """It should raise PuppetServerCheckError if the certificate request doesn't appear."""
        results = [
            (
                nodeset("puppetserver.example.com"),
                MsgTreeElem(b"[]", parent=MsgTreeElem()),
            )
        ]
        self.mocked_server_host.run_sync.side_effect = [iter(results) for _ in range(10)]

        with pytest.raises(
            puppet.PuppetServerCheckError,
            match="No certificate found for hostname: test.example.com",
        ):
            self.puppet_server.wait_for_csr("test.example.com")

        assert mocked_sleep.called

    def test_get_certificate_metadata_ok(self):
        """It should return the metadata of the certificate for the host in the Puppet CA."""
        results = [
            (
                nodeset("puppetserver.example.com"),
                MsgTreeElem(PUPPET_SERVER_CA_CERT_METADATA_SIGNED, parent=MsgTreeElem()),
            )
        ]
        self.mocked_server_host.run_sync.return_value = iter(results)

        metadata = self.puppet_server.get_certificate_metadata("test.example.com")

        assert metadata == json.loads(PUPPET_SERVER_CA_CERT_METADATA_SIGNED.decode())["signed"][0]
        self.mocked_server_host.run_sync.assert_called_once_with(
            "puppetserver ca list --format json --certname test.example.com",
            is_safe=True,
            print_output=False,
            print_progress_bars=False,
        )

    @pytest.mark.parametrize(
        "json_output, exception, exception_message",
        (
            (
                b'{"signed":[{"name":"test.example.com"},{"name":"test.example.com"}]}',
                puppet.PuppetServerError,
                "Expected one result from Puppet CA, got 2",
            ),
            (
                b"[true]",
                puppet.PuppetServerCheckError,
                r"Expected a dict but got list: \[True\]",
            ),
            (
                b'{"missing":["test.example.com"]}',
                puppet.PuppetServerCheckError,
                r"The puppet server has no CSR for test.example.com",
            ),
            (
                b'{"signed":[{"name":"invalid.example.com"}]}',
                puppet.PuppetServerError,
                "Hostname mismatch invalid.example.com != test.example.com",
            ),
            (
                b'{"signed":[], "requested": []}',
                puppet.PuppetServerError,
                "Expected one result type from Puppet CA, got 2",
            ),
        ),
    )
    def test_get_certificate_metadata_raises(self, json_output, exception, exception_message):
        """It should raise PuppetServerError if the Puppet CA returns multiple certificates metadata."""
        results = [
            (
                nodeset("puppetserver.example.com"),
                MsgTreeElem(json_output, parent=MsgTreeElem()),
            )
        ]
        self.mocked_server_host.run_sync.return_value = iter(results)

        with pytest.raises(exception, match=exception_message):
            self.puppet_server.get_certificate_metadata("test.example.com")

    def test_run_json_command_none_zero_rc(self):
        """If the cumin commands returns 0 the function should still return data."""
        json_output = b'{"missing":["test.example.com"]}'
        results = [
            (
                nodeset("puppetserver.example.com"),
                MsgTreeElem(json_output, parent=MsgTreeElem()),
            )
        ]
        self.mocked_server_host.run_sync.return_value = iter(results)
        side_effect = RemoteExecutionError(1, "Cumin, execution failed", iter(results))
        self.mocked_server_host.run_sync.side_effect = side_effect
        assert self.puppet_server._run_json_command("") == json.loads(json_output)  # pylint: disable=protected-access

    @pytest.mark.parametrize("fmt", ["json", "yaml", "s"])
    def test_hiera_lookup(self, fmt):
        """It should return the metadata of the certificate for the host in the Puppet CA."""
        results = [
            (
                nodeset("puppetserver.example.com"),
                MsgTreeElem(b"misc", parent=MsgTreeElem()),
            )
        ]
        self.mocked_server_host.run_sync.return_value = iter(results)

        assert self.puppet_server.hiera_lookup("test.example.com", "cluster", fmt=fmt) == "misc"

        self.mocked_server_host.run_sync.assert_called_once_with(
            f"puppet lookup --render-as {fmt} --compile --node test.example.com cluster 2>/dev/null",
            is_safe=True,
            print_output=False,
            print_progress_bars=False,
        )


class TestPuppetMaster:
    """Test class for the PuppetMaster class."""

    def setup_method(self):
        """Setup the test environment."""
        # pylint: disable=attribute-defined-outside-init
        self.mocked_master_host = mock.MagicMock(spec_set=RemoteHosts)
        self.mocked_master_host.__len__.return_value = 1
        self.puppet_master = puppet.PuppetMaster(self.mocked_master_host)

    def test_destroy(self):
        """It should delete the certificate of the host in the Puppet CA."""
        self.puppet_master.destroy("test.example.com")
        self.mocked_master_host.run_sync.assert_called_once_with(
            "puppet ca --disable_warnings deprecations destroy test.example.com", print_progress_bars=False
        )

    def test_verify_ok(self):
        """It should verify that the host has a signed certificate in the Puppet CA."""
        json_output = b'{"host":"test.example.com","valid":true}'
        results = [
            (
                nodeset("puppetmaster.example.com"),
                MsgTreeElem(json_output, parent=MsgTreeElem()),
            )
        ]
        self.mocked_master_host.run_sync.return_value = iter(results)

        self.puppet_master.verify("test.example.com")
        self.mocked_master_host.run_sync.assert_called_once_with(
            "puppet ca --disable_warnings deprecations --render-as json verify test.example.com",
            is_safe=True,
            print_output=False,
            print_progress_bars=False,
        )

    def test_verify_raise(self):
        """It should raise PuppetServerError if the certificate is not valid on the Puppet CA."""
        json_output = b'{"host":"test.example.com","valid":false,"error":"Error message"}'
        results = [
            (
                nodeset("puppetmaster.example.com"),
                MsgTreeElem(json_output, parent=MsgTreeElem()),
            )
        ]
        self.mocked_master_host.run_sync.return_value = iter(results)

        with pytest.raises(
            puppet.PuppetServerError,
            match="Invalid certificate for test.example.com: Error message",
        ):
            self.puppet_master.verify("test.example.com")

        self.mocked_master_host.run_sync.assert_called_once_with(
            "puppet ca --disable_warnings deprecations --render-as json verify test.example.com",
            is_safe=True,
            print_output=False,
            print_progress_bars=False,
        )

    def test_verify_no_output(self):
        """It should raise PuppetServerError if there is no output from the executed command."""
        self.mocked_master_host.run_sync.return_value = iter(())
        with pytest.raises(
            puppet.PuppetServerError,
            match=(
                re.escape(
                    "Got no output from Puppet server while executing command (rc: 0): "
                    "puppet ca --disable_warnings deprecations --render-as json verify test.example.com"
                )
            ),
        ):
            self.puppet_master.verify("test.example.com")

    def test_verify_invalid_json(self):
        """It should raise PuppetServerError if there output of the executed command is invalid JSON."""
        json_output = b'{"host":"test.example.com",,}'
        results = [
            (
                nodeset("puppetmaster.example.com"),
                MsgTreeElem(json_output, parent=MsgTreeElem()),
            )
        ]
        self.mocked_master_host.run_sync.return_value = iter(results)

        with pytest.raises(
            puppet.PuppetServerError,
            match=(
                re.escape(
                    "Unable to parse Puppet server response for command (rc: 0): "
                    '"puppet ca --disable_warnings deprecations --render-as json verify test.example.com": '
                    r'{"host":"test.example.com",,}'
                )
            ),
        ):
            self.puppet_master.verify("test.example.com")

    def test_sign_ok(self):
        """It should sign the certificate in the Puppet CA."""
        requested_results = [
            (
                nodeset("puppetmaster.example.com"),
                MsgTreeElem(PUPPET_CA_CERT_METADATA_REQUESTED, parent=MsgTreeElem()),
            )
        ]
        signed_results = [
            (
                nodeset("puppetmaster.example.com"),
                MsgTreeElem(PUPPET_CA_CERT_METADATA_SIGNED, parent=MsgTreeElem()),
            )
        ]
        self.mocked_master_host.run_sync.side_effect = [
            iter(requested_results),
            iter(()),
            iter(signed_results),
        ]

        self.puppet_master.sign("test.example.com", "00:AA")

        self.mocked_master_host.run_sync.assert_has_calls(
            [
                mock.call(
                    "puppet ca --disable_warnings deprecations --render-as json "
                    r'list --all --subject "^test\.example\.com$"',
                    is_safe=True,
                    print_output=False,
                    print_progress_bars=False,
                ),
                mock.call(
                    "puppet cert --disable_warnings deprecations sign test.example.com",
                    print_output=False,
                    print_progress_bars=False,
                ),
                mock.call(
                    "puppet ca --disable_warnings deprecations --render-as json "
                    r'list --all --subject "^test\.example\.com$"',
                    is_safe=True,
                    print_output=False,
                    print_progress_bars=False,
                ),
            ]
        )

    def test_sign_wrong_state(self):
        """It should raise PuppetServerError if the certificate is not in the requested state."""
        results = [
            (
                nodeset("puppetmaster.example.com"),
                MsgTreeElem(PUPPET_CA_CERT_METADATA_SIGNED, parent=MsgTreeElem()),
            )
        ]
        self.mocked_master_host.run_sync.return_value = iter(results)

        with pytest.raises(
            puppet.PuppetServerError,
            match="Certificate for test.example.com not in requested state, got: signed",
        ):
            self.puppet_master.sign("test.example.com", "00:AA")

    def test_sign_wrong_fingerprint(self):
        """It should raise PuppetServerError if the fingerprint doesn't match the one in the CSR."""
        results = [
            (
                nodeset("puppetmaster.example.com"),
                MsgTreeElem(PUPPET_CA_CERT_METADATA_REQUESTED, parent=MsgTreeElem()),
            )
        ]
        self.mocked_master_host.run_sync.return_value = iter(results)

        with pytest.raises(
            puppet.PuppetServerError,
            match="CSR fingerprint 00:AA for test.example.com does not match provided fingerprint FF:FF",
        ):
            self.puppet_master.sign("test.example.com", "FF:FF")

    def test_sign_fail(self):
        """It should raise PuppetServerError if the sign operation fails."""
        requested_results = [
            (
                nodeset("puppetmaster.example.com"),
                MsgTreeElem(PUPPET_CA_CERT_METADATA_REQUESTED, parent=MsgTreeElem()),
            )
        ]
        sign_results = [
            (
                nodeset("puppetmaster.example.com"),
                MsgTreeElem(b"sign error", parent=MsgTreeElem()),
            )
        ]
        signed_results = [
            (
                nodeset("puppetmaster.example.com"),
                MsgTreeElem(PUPPET_CA_CERT_METADATA_REQUESTED, parent=MsgTreeElem()),
            )
        ]
        self.mocked_master_host.run_sync.side_effect = [
            iter(requested_results),
            iter(sign_results),
            iter(signed_results),
        ]

        with pytest.raises(
            puppet.PuppetServerError,
            match="Expected certificate for test.example.com to be signed, got: requested",
        ):
            self.puppet_master.sign("test.example.com", "00:AA")

    def test_get_certificate_metadata_ok(self):
        """It should return the metadata of the certificate for the host in the Puppet CA."""
        results = [
            (
                nodeset("puppetmaster.example.com"),
                MsgTreeElem(PUPPET_CA_CERT_METADATA_SIGNED, parent=MsgTreeElem()),
            )
        ]
        self.mocked_master_host.run_sync.return_value = iter(results)

        metadata = self.puppet_master.get_certificate_metadata("test.example.com")

        assert metadata == json.loads(PUPPET_CA_CERT_METADATA_SIGNED.decode())[0]
        self.mocked_master_host.run_sync.assert_called_once_with(
            "puppet ca --disable_warnings deprecations --render-as json list "
            r'--all --subject "^test\.example\.com$"',
            is_safe=True,
            print_output=False,
            print_progress_bars=False,
        )

    @pytest.mark.parametrize(
        "json_output, exception, exception_message",
        (
            (
                b"{}",
                puppet.PuppetServerCheckError,
                "No certificate found for hostname: test.example.com",
            ),
            (
                b'[{"name":"test.example.com"},{"name":"test.example.com"}]',
                puppet.PuppetServerError,
                "Expected one result from Puppet CA, got 2",
            ),
            (
                b'[{"name":"invalid.example.com"}]',
                puppet.PuppetServerError,
                "Hostname mismatch invalid.example.com != test.example.com",
            ),
        ),
    )
    def test_get_certificate_metadata_raises(self, json_output, exception, exception_message):
        """It should raise PuppetServerError if the Puppet CA returns multiple certificates metadata."""
        results = [
            (
                nodeset("puppetmaster.example.com"),
                MsgTreeElem(json_output, parent=MsgTreeElem()),
            )
        ]
        self.mocked_master_host.run_sync.return_value = iter(results)

        with pytest.raises(exception, match=exception_message):
            self.puppet_master.get_certificate_metadata("test.example.com")
