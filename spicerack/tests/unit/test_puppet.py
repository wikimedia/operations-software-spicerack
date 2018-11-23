"""Puppet module tests."""
import json

from subprocess import CalledProcessError  # nosec
from unittest import mock

import pytest

from ClusterShell.MsgTree import MsgTreeElem
from cumin import NodeSet

from spicerack import puppet
from spicerack.administrative import Reason
from spicerack.remote import RemoteHosts


PUPPET_CA_CERT_METADATA_SIGNED = (
    b'[{"name":"test.example.com","state":"signed","fingerprint":"00:AA",'
    b'"fingerprints":{"default":"00:AA","SHA1":"11:BB","SHA256": "00:AA","SHA512":"22:CC"},'
    b'"dns_alt_names":["DNS:service.example.com"]}]')
PUPPET_CA_CERT_METADATA_REQUESTED = (
    b'[{"name":"test.example.com","state":"requested","fingerprint":"00:AA",'
    b'"fingerprints":{"default":"00:AA","SHA1":"11:BB","SHA256": "00:AA","SHA512":"22:CC"},'
    b'"dns_alt_names":["DNS:service.example.com"]}]')


@mock.patch('spicerack.puppet.check_output', return_value=b'puppetmaster.example.com')
def test_get_puppet_ca_hostname_ok(mocked_check_output):
    """It should get the hostname of the Puppet CA from the local Puppet agent."""
    ca = puppet.get_puppet_ca_hostname()
    assert ca == 'puppetmaster.example.com'
    mocked_check_output.assert_called_once_with('puppet config print --section agent ca_server')


@mock.patch('spicerack.puppet.check_output', side_effect=CalledProcessError(1, 'executed_command'))
def test_get_puppet_ca_hostname_fail(mocked_check_output):
    """It should raise PuppetMasterError if unable to get the hostname of the Puppet CA from the Puppet agent."""
    with pytest.raises(puppet.PuppetMasterError, match='Get Puppet ca_server failed'):
        puppet.get_puppet_ca_hostname()

    assert mocked_check_output.called


@mock.patch('spicerack.puppet.check_output', return_value=b'')
def test_get_puppet_ca_hostname_empty(mocked_check_output):
    """It should raise PuppetMasterError if the Puppet CA from Puppet is empty."""
    with pytest.raises(puppet.PuppetMasterError, match='Got empty ca_server from Puppet agent'):
        puppet.get_puppet_ca_hostname()

    assert mocked_check_output.called


class TestPuppetHosts:
    """Test class for the PuppetHosts class."""

    def setup_method(self):
        """Setup the test environment."""
        # pylint: disable=attribute-defined-outside-init
        self.reason = Reason('Disable reason', 'user1', 'orchestration-host', task_id='T12345')
        self.mocked_remote_hosts = mock.MagicMock(spec_set=RemoteHosts)
        self.puppet_hosts = puppet.PuppetHosts(self.mocked_remote_hosts)

    def test_disable(self):
        """It should disable Puppet on the hosts."""
        self.puppet_hosts.disable(self.reason)
        self.mocked_remote_hosts.run_sync.assert_called_once_with(
            'disable-puppet {reason}'.format(reason=self.reason.quoted()))

    def test_enable(self):
        """It should enable Puppet on the hosts."""
        self.puppet_hosts.enable(self.reason)
        self.mocked_remote_hosts.run_sync.assert_called_once_with(
            'enable-puppet {reason}'.format(reason=self.reason.quoted()))

    def test_disabled(self):
        """It should disable Puppet, yield and enable Puppet on the hosts."""
        with self.puppet_hosts.disabled(self.reason):
            self.mocked_remote_hosts.run_sync.assert_called_once_with(
                'disable-puppet {reason}'.format(reason=self.reason.quoted()))
            self.mocked_remote_hosts.run_sync.reset_mock()

        self.mocked_remote_hosts.run_sync.assert_called_once_with(
            'enable-puppet {reason}'.format(reason=self.reason.quoted()))

    def test_disabled_on_raise(self):
        """It should re-enable Puppet even if the yielded code raises exception.."""
        with pytest.raises(RuntimeError):
            with self.puppet_hosts.disabled(self.reason):
                self.mocked_remote_hosts.run_sync.reset_mock()
                raise RuntimeError('Error')

        self.mocked_remote_hosts.run_sync.assert_called_once_with(
            'enable-puppet {reason}'.format(reason=self.reason.quoted()))


class TestPuppetMaster:
    """Test class for the PuppetMaster class."""

    def setup_method(self):
        """Setup the test environment."""
        # pylint: disable=attribute-defined-outside-init
        self.mocked_master_host = mock.MagicMock(spec_set=RemoteHosts)
        self.mocked_master_host.__len__.return_value = 1
        self.puppet_master = puppet.PuppetMaster(self.mocked_master_host)

    def test_init_raise(self):
        """It should raise PuppetMasterError if the Puppet master host instance doesn't match one host."""
        self.mocked_master_host.__len__.return_value = 2
        with pytest.raises(puppet.PuppetMasterError, match='The master_host instance must target only one host, got 2'):
            puppet.PuppetMaster(self.mocked_master_host)

    def test_destroy(self):
        """It should delete the certificate of the host in the Puppet CA."""
        self.puppet_master.destroy('test.example.com')
        self.mocked_master_host.run_sync.assert_called_once_with('puppet ca destroy test.example.com')

    def test_verify_ok(self):
        """It should verify that the host has a signed certificate in the Puppet CA."""
        json_output = b'{"host":"test.example.com","valid":true}'
        results = [(NodeSet('puppetmaster.example.com'), MsgTreeElem(json_output, parent=MsgTreeElem()))]
        self.mocked_master_host.run_sync.return_value = iter(results)

        self.puppet_master.verify('test.example.com')
        self.mocked_master_host.run_sync.assert_called_once_with(
            'puppet ca --render-as json verify test.example.com', is_safe=True)

    def test_verify_raise(self):
        """It should raise PuppetMasterError if the certificate is not valid on the Puppet CA."""
        json_output = b'{"host":"test.example.com","valid":false,"error":"Error message"}'
        results = [(NodeSet('puppetmaster.example.com'), MsgTreeElem(json_output, parent=MsgTreeElem()))]
        self.mocked_master_host.run_sync.return_value = iter(results)

        with pytest.raises(puppet.PuppetMasterError, match='Invalid certificate for test.example.com: Error message'):
            self.puppet_master.verify('test.example.com')

        self.mocked_master_host.run_sync.assert_called_once_with(
            'puppet ca --render-as json verify test.example.com', is_safe=True)

    def test_verify_no_output(self):
        """It should raise PuppetMasterError if there is no output from the executed command."""
        self.mocked_master_host.run_sync.return_value = iter(())
        with pytest.raises(puppet.PuppetMasterError,
                           match=('Got no output from Puppet master while executing command: '
                                  'puppet ca --render-as json verify test.example.com')):
            self.puppet_master.verify('test.example.com')

    def test_verify_invalid_json(self):
        """It should raise PuppetMasterError if there output of the executed command is invalid JSON."""
        json_output = b'{"host":"test.example.com",,}'
        results = [(NodeSet('puppetmaster.example.com'), MsgTreeElem(json_output, parent=MsgTreeElem()))]
        self.mocked_master_host.run_sync.return_value = iter(results)

        with pytest.raises(puppet.PuppetMasterError,
                           match=('Unable to parse Puppet master response for command '
                                  '"puppet ca --render-as json verify test.example.com"')):
            self.puppet_master.verify('test.example.com')

    def test_sign_ok(self):
        """It should sign the certificate in the Puppet CA."""
        requested_results = [(NodeSet('puppetmaster.example.com'),
                              MsgTreeElem(PUPPET_CA_CERT_METADATA_REQUESTED, parent=MsgTreeElem()))]
        signed_results = [(NodeSet('puppetmaster.example.com'),
                           MsgTreeElem(PUPPET_CA_CERT_METADATA_SIGNED, parent=MsgTreeElem()))]
        self.mocked_master_host.run_sync.side_effect = [iter(requested_results), iter(()), iter(signed_results)]

        self.puppet_master.sign('test.example.com', '00:AA')

        self.mocked_master_host.run_sync.assert_has_calls([
            mock.call(r'puppet ca --render-as json list --all --subject "test\.example\.com"', is_safe=True),
            mock.call('puppet cert sign --no-allow-dns-alt-names test.example.com'),
            mock.call(r'puppet ca --render-as json list --all --subject "test\.example\.com"', is_safe=True),
        ])

    def test_sign_alt_dns(self):
        """It should pass the --allow-dns-alt-names option while signing the certificate."""
        requested_results = [(NodeSet('puppetmaster.example.com'),
                              MsgTreeElem(PUPPET_CA_CERT_METADATA_REQUESTED, parent=MsgTreeElem()))]
        signed_results = [(NodeSet('puppetmaster.example.com'),
                           MsgTreeElem(PUPPET_CA_CERT_METADATA_SIGNED, parent=MsgTreeElem()))]
        self.mocked_master_host.run_sync.side_effect = [iter(requested_results), iter(()), iter(signed_results)]

        self.puppet_master.sign('test.example.com', '00:AA', allow_alt_names=True)

        self.mocked_master_host.run_sync.assert_has_calls([
            mock.call(r'puppet ca --render-as json list --all --subject "test\.example\.com"', is_safe=True),
            mock.call('puppet cert sign --allow-dns-alt-names test.example.com'),
            mock.call(r'puppet ca --render-as json list --all --subject "test\.example\.com"', is_safe=True),
        ])

    def test_sign_wrong_state(self):
        """It should raise PuppetMasterError if the certificate is not in the requested state."""
        results = [(NodeSet('puppetmaster.example.com'),
                    MsgTreeElem(PUPPET_CA_CERT_METADATA_SIGNED, parent=MsgTreeElem()))]
        self.mocked_master_host.run_sync.return_value = iter(results)

        with pytest.raises(puppet.PuppetMasterError,
                           match='Certificate for test.example.com not in requested state, got: signed'):
            self.puppet_master.sign('test.example.com', '00:AA')

    def test_sign_wrong_fingerprint(self):
        """It should raise PuppetMasterError if the fingerprint doesn't match the one in the CSR."""
        results = [(NodeSet('puppetmaster.example.com'),
                    MsgTreeElem(PUPPET_CA_CERT_METADATA_REQUESTED, parent=MsgTreeElem()))]
        self.mocked_master_host.run_sync.return_value = iter(results)

        with pytest.raises(
                puppet.PuppetMasterError,
                match='CSR fingerprint 00:AA for test.example.com does not match provided fingerprint FF:FF'):
            self.puppet_master.sign('test.example.com', 'FF:FF')

    def test_sign_fail(self):
        """It should raise PuppetMasterError if the sign operation fails."""
        requested_results = [(NodeSet('puppetmaster.example.com'),
                              MsgTreeElem(PUPPET_CA_CERT_METADATA_REQUESTED, parent=MsgTreeElem()))]
        sign_results = [(NodeSet('puppetmaster.example.com'),
                         MsgTreeElem(b'sign error', parent=MsgTreeElem()))]
        signed_results = [(NodeSet('puppetmaster.example.com'),
                           MsgTreeElem(PUPPET_CA_CERT_METADATA_REQUESTED, parent=MsgTreeElem()))]
        self.mocked_master_host.run_sync.side_effect = [
            iter(requested_results), iter(sign_results), iter(signed_results)]

        with pytest.raises(puppet.PuppetMasterError,
                           match='Expected certificate for test.example.com to be signed, got: requested'):
            self.puppet_master.sign('test.example.com', '00:AA')

    def test_wait_for_csr_already_ok(self):
        """It should return immediately if the certificate is already requested."""
        results = [(NodeSet('puppetmaster.example.com'),
                    MsgTreeElem(PUPPET_CA_CERT_METADATA_REQUESTED, parent=MsgTreeElem()))]
        self.mocked_master_host.run_sync.return_value = iter(results)

        self.puppet_master.wait_for_csr('test.example.com')

        self.mocked_master_host.run_sync.assert_called_once_with(
            r'puppet ca --render-as json list --all --subject "test\.example\.com"', is_safe=True)

    def test_wait_for_csr_fail(self):
        """It should raise PuppetMasterError if the certificate is in a wrong state."""
        results = [(NodeSet('puppetmaster.example.com'),
                    MsgTreeElem(PUPPET_CA_CERT_METADATA_SIGNED, parent=MsgTreeElem()))]
        self.mocked_master_host.run_sync.return_value = iter(results)

        with pytest.raises(puppet.PuppetMasterError, match='Expected certificate in requested state, got: signed'):
            self.puppet_master.wait_for_csr('test.example.com')

    @mock.patch('spicerack.decorators.time.sleep', return_value=None)
    def test_wait_for_csr_timeout(self, mocked_sleep):
        """It should raise PuppetMasterCheckError if the certificate request doesn't appear."""
        results = [(NodeSet('puppetmaster.example.com'), MsgTreeElem(b'[]', parent=MsgTreeElem()))]
        self.mocked_master_host.run_sync.side_effect = [iter(results) for _ in range(10)]

        with pytest.raises(puppet.PuppetMasterCheckError, match='No certificate found for hostname: test.example.com'):
            self.puppet_master.wait_for_csr('test.example.com')

        assert mocked_sleep.called

    def test_get_certificate_metadata_ok(self):
        """It should return the metadata of the certificate for the host in the Puppet CA."""
        results = [(NodeSet('puppetmaster.example.com'),
                    MsgTreeElem(PUPPET_CA_CERT_METADATA_SIGNED, parent=MsgTreeElem()))]
        self.mocked_master_host.run_sync.return_value = iter(results)

        metadata = self.puppet_master.get_certificate_metadata('test.example.com')

        assert metadata == json.loads(PUPPET_CA_CERT_METADATA_SIGNED.decode())[0]
        self.mocked_master_host.run_sync.assert_called_once_with(
            r'puppet ca --render-as json list --all --subject "test\.example\.com"', is_safe=True)

    @pytest.mark.parametrize('json_output, exception_message', (
        (b'[{"name":"test.example.com"},{"name":"test.example.com"}]', 'Expected one result from Puppet CA, got 2'),
        (b'[{"name":"invalid.example.com"}]', 'Hostname mismatch invalid.example.com != test.example.com'),
    ))
    def test_get_certificate_metadata_raises(self, json_output, exception_message):
        """It should raise PuppetMasterError if the Puppet CA returns multiple certificates metadata."""
        results = [(NodeSet('puppetmaster.example.com'), MsgTreeElem(json_output, parent=MsgTreeElem()))]
        self.mocked_master_host.run_sync.return_value = iter(results)

        with pytest.raises(puppet.PuppetMasterError, match=exception_message):
            self.puppet_master.get_certificate_metadata('test.example.com')
