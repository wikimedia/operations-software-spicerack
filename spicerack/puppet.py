"""Puppet module."""
import json
import logging

from contextlib import contextmanager
from datetime import timedelta
from subprocess import CalledProcessError, check_output  # nosec

from spicerack.decorators import retry
from spicerack.exceptions import SpicerackCheckError, SpicerackError
from spicerack.remote import RemoteHostsAdapter


logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


def get_puppet_ca_hostname():
    """Return the FQDN of the current Puppet CA server.

    Raises:
        spicerack.puppet.PuppetMasterError: if unable to get the configured Puppet CA server.

    Returns:
        str: the hostname of the Puppet Certification Authority server.

    """
    try:
        output = check_output('puppet config print --section agent ca_server').decode().strip()  # nosec
    except CalledProcessError as e:
        raise PuppetMasterError('Get Puppet ca_server failed (exit={code}): {output}'.format(
            code=e.returncode, output=e.output)) from e

    if not output:
        raise PuppetMasterError('Got empty ca_server from Puppet agent')

    return output


class PuppetMasterError(SpicerackError):
    """Custom base exception class for errors in the PuppetMaster class."""


class PuppetMasterCheckError(SpicerackCheckError):
    """Custom exception class for check errors in the PuppetMaster class."""


class PuppetHosts(RemoteHostsAdapter):
    """Class to manage Puppet on the target hosts."""

    @contextmanager
    def disabled(self, reason):
        """Context manager to perform actions while puppet is disabled.

        Arguments:
            reason (spicerack.administrative.Reason): the reason to set for the Puppet disable and to use for the
                Puppet enable.
        """
        self.disable(reason)
        try:
            yield
        finally:
            self.enable(reason)

    def disable(self, reason):
        """Disable puppet with a specific reason.

        If Puppet was already disabled on a host with a different reason, the reason will not be overriden, allowing to
        leave Puppet disabled when re-enabling it if it was already disabled.

        Arguments:
            reason (spicerack.administrative.Reason): the reason to set for the Puppet disable.
        """
        logger.info('Disabling Puppet with reason %s on %d hosts: %s', reason.quoted(), len(self), self)
        self._remote_hosts.run_sync('disable-puppet {reason}'.format(reason=reason.quoted()))

    def enable(self, reason):
        """Enable Puppet with a specific reason, it must be the same used to disable it.

        Puppet will be re-enabled only if it was disable with the same reason. If it was disable with a different reason
        it will keep being disabled.

        Arguments:
            reason (spicerack.administrative.Reason): the reason to use for the Puppet enable.
        """
        logger.info('Enabling Puppet with reason %s on %d hosts: %s', reason.quoted(), len(self), self)
        self._remote_hosts.run_sync('enable-puppet {reason}'.format(reason=reason.quoted()))


class PuppetMaster:
    """Class to manage nodes and certificates on a Puppet master and Puppet CA server."""

    PUPPET_CERT_STATE_REQUESTED = 'requested'
    PUPPET_CERT_STATE_SIGNED = 'signed'

    def __init__(self, master_host):
        """Initialize the instance.

        Arguments:
            master_host (spicerack.remote.RemoteHosts): the remote hosts instance for the Puppetmaster and Puppet CA
                server. It must have only one target host.

        Raises:
            spicerack.puppet.PuppetMasterError: if the master_host doesn't have only one target host.

        """
        if len(master_host) != 1:
            raise PuppetMasterError('The master_host instance must target only one host, got {num}: {hosts}'.format(
                num=len(master_host), hosts=master_host))

        self._master_host = master_host

    def destroy(self, hostname):
        """Remove the certificate for the given hostname.

        If there is no certificate to remove it doesn't raise exception as the Puppet CA just outputs
        'Nothing was deleted'.

        Arguments:
            hostname (str): the FQDN of the host for which to remove the certificate.
        """
        self._master_host.run_sync('puppet ca destroy {host}'.format(host=hostname))

    def verify(self, hostname):
        """Verify that there is a valid certificate signed by the Puppet CA for the given hostname.

        Arguments:
            hostname (str): the FQDN of the host for which to verify the certificate.

        Raises:
            spicerack.puppet.PuppetMasterError: if the certificate is not valid.

        """
        response = self._run_json_command('puppet ca --render-as json verify {host}'.format(host=hostname))

        if not response['valid']:
            raise PuppetMasterError(
                'Invalid certificate for {host}: {error}'.format(host=hostname, error=response['error']))

    def sign(self, hostname, fingerprint, allow_alt_names=False):
        """Sign a CSR on the Puppet CA for the given host checking its fingerprint.

        Arguments:
            hostname (str): the FQDN of the host for which to sign the certificate.
            fingerprint (str): the fingerprint of the CSR generated on the client to verify it.
            allow_alt_names (bool, optional): whether to allow DNS alternative names in the certificate.

        Raises:
            spicerack.puppet.PuppetMasterError: if the certificate is in an unexpected state.

        """
        cert = self.get_certificate_metadata(hostname)
        if cert['state'] != PuppetMaster.PUPPET_CERT_STATE_REQUESTED:
            raise PuppetMasterError('Certificate for {host} not in requested state, got: {state}'.format(
                host=hostname, state=cert['state']))

        if cert['fingerprint'] != fingerprint:
            raise PuppetMasterError(
                'CSR fingerprint {csr} for {host} does not match provided fingerprint {expected}'.format(
                    csr=cert['fingerprint'], host=hostname, expected=fingerprint))

        if allow_alt_names:
            dns_option = '--allow-dns-alt-names'
        else:
            dns_option = '--no-allow-dns-alt-names'

        command = 'puppet cert sign {dns_option} {host}'.format(dns_option=dns_option, host=hostname)
        logger.info('Signing CSR for %s with fingerprint %s', hostname, fingerprint)
        executed = self._master_host.run_sync(command)

        cert = self.get_certificate_metadata(hostname)
        if cert['state'] != PuppetMaster.PUPPET_CERT_STATE_SIGNED:
            for _, output in executed:
                logger.error(output.message().decode())

            raise PuppetMasterError('Expected certificate for {host} to be signed, got: {state}'.format(
                host=hostname, state=cert['state']))

    @retry(tries=10, delay=timedelta(seconds=5), backoff_mode='power', exceptions=(PuppetMasterCheckError,))
    def wait_for_csr(self, hostname):
        """Poll until a CSR appears for the given hostname or the timeout is reached.

        Arguments:
            hostname (str): the FQDN of the host for which to check a CSR.

        Raises:
            spicerack.puppet.PuppetMasterError: if the certificate is in an unexpected state.
            spicerack.puppet.PuppetMasterCheckError: if within the timeout no CSR is found.

        """
        state = self.get_certificate_metadata(hostname)['state']
        if state != PuppetMaster.PUPPET_CERT_STATE_REQUESTED:
            raise PuppetMasterError('Expected certificate in requested state, got: {state}'.format(state=state))

    def get_certificate_metadata(self, hostname):
        """Return the metadata of the certificate of the given hostname in the Puppet CA.

        Arguments:
            hostname (str): the FQDN of the host for which to verify the certificate.

        Returns:
            dict: as returned by the Puppet CA CLI with the render as JSON option set. As example::

                {'dns_alt_names': ['DNS:service.example.com'],
                 'fingerprint': '00:FF:...',
                 'fingerprints': {
                    'SHA1': '00:FF:...', 'SHA256': '00:FF:...', 'SHA512': '00:FF:...', 'default': '00:FF:...'},
                 'name': 'host.example.com',
                 'state': 'signed'}

        Raises:
            spicerack.puppet.PuppetMasterCheckError: if no certificate is found.
            spicerack.puppet.PuppetMasterError: if more than one certificate is found or it has invalid data.

        """
        response = self._run_json_command('puppet ca --render-as json list --all --subject "{pattern}"'.format(
            pattern=hostname.replace('.', r'\.')))

        if not response:
            raise PuppetMasterCheckError('No certificate found for hostname: {host}'.format(host=hostname))
        elif len(response) > 1:
            raise PuppetMasterError('Expected one result from Puppet CA, got {num}'.format(num=len(response)))

        metadata = response[0]
        if metadata['name'] != hostname:
            raise PuppetMasterError(
                'Hostname mismatch {name} != {host}'.format(name=metadata['name'], host=hostname))

        return metadata

    def _run_json_command(self, command):
        """Execute and parse a Puppet CLI command that output JSON format.

        The commands run are assumed to be safe as the JSON format is useful for read-only operations only.

        Arguments:
            command (str): the command to execute on the Puppet master that returns JSON output.

        Returns:
            dict, list: the parsed JSON object.

        Raises:
            spicerack.puppet.PuppetMasterError: if unable to get or parse the command output.

        """
        for _, output in self._master_host.run_sync(command, is_safe=True):
            lines = output.message().decode()
            break
        else:
            raise PuppetMasterError(
                'Got no output from Puppet master while executing command: {command}'.format(command=command))

        try:
            response = json.loads(lines)
        except ValueError as e:
            raise PuppetMasterError('Unable to parse Puppet master response for command "{command}": {lines}'.format(
                command=command, lines=lines)) from e

        return response
