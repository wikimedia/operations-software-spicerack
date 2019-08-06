"""Puppet module."""
import json
import logging

from contextlib import contextmanager
from datetime import datetime, timedelta
from subprocess import CalledProcessError, check_output  # nosec
from typing import Dict, Iterator, List, Optional, Union

from cumin import NodeSet
from cumin.transports import Command

from spicerack.administrative import Reason
from spicerack.decorators import retry
from spicerack.exceptions import SpicerackCheckError, SpicerackError
from spicerack.remote import RemoteExecutionError, RemoteHosts, RemoteHostsAdapter


PUPPET_COMMON_SCRIPT = '/usr/local/share/bash/puppet-common.sh'
logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


def get_puppet_ca_hostname() -> str:
    """Return the FQDN of the current Puppet CA server.

    Raises:
        spicerack.puppet.PuppetMasterError: if unable to get the configured Puppet CA server.

    Returns:
        str: the hostname of the Puppet Certification Authority server.

    """
    try:
        output = check_output(  # nosec
            ['puppet', 'config', 'print', '--section', 'agent', 'ca_server']).decode().strip()
    except CalledProcessError as e:
        raise PuppetMasterError('Get Puppet ca_server failed (exit={code}): {output}'.format(
            code=e.returncode, output=e.output)) from e

    if not output:
        raise PuppetMasterError('Got empty ca_server from Puppet agent')

    return output


class PuppetHostsError(SpicerackError):
    """Custom base exception class for errors in the PuppetHosts class."""


class PuppetHostsCheckError(SpicerackError):
    """Custom base exception class for check errors in the PuppetHosts class."""


class PuppetMasterError(SpicerackError):
    """Custom base exception class for errors in the PuppetMaster class."""


class PuppetMasterCheckError(SpicerackCheckError):
    """Custom exception class for check errors in the PuppetMaster class."""


class PuppetHosts(RemoteHostsAdapter):
    """Class to manage Puppet on the target hosts."""

    @contextmanager
    def disabled(self, reason: Reason) -> Iterator[None]:
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

    def disable(self, reason: Reason) -> None:
        """Disable puppet with a specific reason.

        If Puppet was already disabled on a host with a different reason, the reason will not be overriden, allowing to
        leave Puppet disabled when re-enabling it if it was already disabled.

        Arguments:
            reason (spicerack.administrative.Reason): the reason to set for the Puppet disable.

        """
        logger.info('Disabling Puppet with reason %s on %d hosts: %s', reason.quoted(), len(self), self)
        self._remote_hosts.run_sync('disable-puppet {reason}'.format(reason=reason.quoted()))

    def enable(self, reason: Reason) -> None:
        """Enable Puppet with a specific reason, it must be the same used to disable it.

        Puppet will be re-enabled only if it was disable with the same reason. If it was disable with a different reason
        it will keep being disabled.

        Arguments:
            reason (spicerack.administrative.Reason): the reason to use for the Puppet enable.

        """
        logger.info('Enabling Puppet with reason %s on %d hosts: %s', reason.quoted(), len(self), self)
        self._remote_hosts.run_sync('enable-puppet {reason}'.format(reason=reason.quoted()))

    def check_enabled(self) -> None:
        """Check if Puppet is enabled on all hosts.

        Raises:
            spicerack.puppet.PuppetHostsCheckError: if Puppet is disabled on some hosts.

        """
        disabled = self._get_disabled()[True]
        if disabled:
            raise PuppetHostsCheckError(
                'Puppet is not enabled on those hosts: {hosts}'.format(hosts=disabled))

    def check_disabled(self) -> None:
        """Check if Puppet is disabled on all hosts.

        Raises:
            spicerack.puppet.PuppetHostsCheckError: if Puppet is enabled on some hosts.

        """
        enabled = self._get_disabled()[False]
        if enabled:
            raise PuppetHostsCheckError(
                'Puppet is not disabled on those hosts: {hosts}'.format(hosts=enabled))

    def run(  # pylint: disable=too-many-arguments
        self,
        timeout: int = 300,
        enable_reason: Optional[Reason] = None,
        quiet: bool = False,
        failed_only: bool = False,
        force: bool = False,
        attempts: int = 0,
        batch_size: int = 10
    ) -> None:
        """Run Puppet.

        Arguments:
            timeout (int, optional): the timeout in seconds to set in Cumin for the execution of the command.
            enable_reason (spicerack.administrative.Reason, optional): the reason to use to contextually re-enable
                Puppet if it was disabled.
            quiet (bool, optional): suppress Puppet output if True.
            failed_only (bool, optional): run Puppet only if the last run failed.
            force (bool, optional): forcely re-enable Puppet if it was disabled with ANY message.
            attempts (int, optional): override the default number of attempts waiting that an in-flight Puppet run
                completes before timing out as set in run-puppet-agent.
            batch_size (int, optional): how many concurrent Puppet runs to perform. The default value is tailored to
                not overload the Puppet masters.

        """
        args = []  # type: ignore
        if enable_reason is not None:
            args += ['--enable', enable_reason.quoted()]
        if quiet:
            args.append('--quiet')
        if failed_only:
            args.append('--failed-only')
        if force:
            args.append('--force')
        if attempts:
            args += ['--attempts', str(attempts)]

        args_string = ' '.join(args)
        command = 'run-puppet-agent {args}'.format(args=args_string)
        logger.info('Running Puppet with args %s on %d hosts: %s', args_string, len(self), self)
        self._remote_hosts.run_sync(Command(command, timeout=timeout), batch_size=batch_size)

    def first_run(self, has_systemd: bool = True) -> None:
        """Perform the first Puppet run on a clean host without using custom wrappers.

        Arguments:
            has_systemd (bool, optional): if the host has systemd as init system.

        """
        commands = []  # type: ignore
        if has_systemd:
            commands += ['systemctl stop puppet.service', 'systemctl reset-failed puppet.service || true']

        commands += [
            'puppet agent --enable',
            Command(('puppet agent --onetime --no-daemonize --verbose --no-splay --show_diff --ignorecache '
                     '--no-usecacheonfailure'), timeout=10800)]

        logger.info('Starting first Puppet run (sit back, relax, and enjoy the wait)')
        self._remote_hosts.run_sync(*commands)
        logger.info('First Puppet run completed')

    def regenerate_certificate(self) -> Dict[str, str]:
        """Delete the local Puppet certificate and generate a new CSR.

        Returns:
            dict: a dictionary with hostnames as keys and CSR fingerprint as values.

        """
        logger.info('Deleting local Puppet certificate on %d hosts: %s', len(self), self)
        self._remote_hosts.run_sync('rm -rfv /var/lib/puppet/ssl')

        fingerprints = {}
        errors = []
        # Puppet exits with 1 when generating the CSR
        command = Command('puppet agent --test --color=false', ok_codes=[1])
        logger.info('Generating a new Puppet certificate on %d hosts: %s', len(self), self)
        for nodeset, output in self._remote_hosts.run_sync(command):
            for line in output.message().decode().splitlines():
                if line.startswith('Error:'):
                    errors.append((nodeset, line))
                    continue

                if 'Certificate Request fingerprint' not in line:
                    continue

                fingerprint = ':'.join(line.split(':')[2:]).strip()
                if not fingerprint:
                    continue

                logger.info('Generated CSR for host %s: %s', nodeset, fingerprint)
                for host in nodeset:
                    fingerprints[host] = fingerprint

        if len(fingerprints) != len(self):
            formatted_errors = '\n'.join('{}: {}'.format(*error) for error in errors)
            raise PuppetHostsError(
                'Unable to find CSR fingerprints for all hosts, detected errors are:\n{errors}'.format(
                    errors=formatted_errors))

        return fingerprints

    def wait(self) -> None:
        """Wait until the next successful Puppet run is completed."""
        self.wait_since(datetime.utcnow())

    @retry(tries=60, delay=timedelta(seconds=30), backoff_mode='linear', exceptions=(PuppetHostsCheckError,))
    def wait_since(self, start: datetime) -> None:
        """Wait until a successful Puppet run is completed after the start time.

        Arguments:
            start (datetime.datetime): wait until a Puppet run is completed after this time.

        Raises:
            spicerack.puppet.PuppetHostsCheckError: if unable to get a successful Puppet run within the timeout.

        """
        remaining_nodes = self._remote_hosts.hosts
        command = ("source {file} && last_run_success && "
                   "awk /last_run/'{{ print $2 }}' \"${{PUPPET_SUMMARY}}\"").format(file=PUPPET_COMMON_SCRIPT)

        logger.info('Polling the completion of a successful Puppet run')
        try:
            for nodeset, output in self._remote_hosts.run_sync(command, is_safe=True):
                last_run = datetime.utcfromtimestamp(int(output.message().decode()))
                if last_run <= start:
                    raise PuppetHostsCheckError('Successful Puppet run too old ({run} <= {start}) on: {nodes}'.format(
                        run=last_run, start=start, nodes=nodeset))

                remaining_nodes.difference_update(nodeset, strict=False)

        except RemoteExecutionError as e:
            raise PuppetHostsCheckError('Unable to find a successful Puppet run') from e

        if remaining_nodes:
            raise PuppetHostsCheckError(
                'Unable to get successful Puppet run from: {nodes}'.format(nodes=remaining_nodes))

        logger.info('Successful Puppet run found')

    def _get_disabled(self) -> Dict[bool, NodeSet]:
        """Check if Puppet is disabled on the hosts.

        Returns:
            dict: a dict with :py:class:`bool` keys for Puppet disabled or not and hosts
            :py:class:`ClusterShell.NodeSet.NodeSet` as values.

        """
        results = self._remote_hosts.run_sync(
            'source {file} && test -f "${{PUPPET_DISABLEDLOCK}}" && echo "1" || echo "0"'.format(
                file=PUPPET_COMMON_SCRIPT), is_safe=True)

        disabled = {True: NodeSet(), False: NodeSet()}
        for nodeset, output in results:
            result = bool(int(output.message().decode().strip()))
            disabled[result] |= nodeset

        return disabled


class PuppetMaster:
    """Class to manage nodes and certificates on a Puppet master and Puppet CA server."""

    PUPPET_CERT_STATE_REQUESTED = 'requested'
    PUPPET_CERT_STATE_SIGNED = 'signed'

    def __init__(self, master_host: RemoteHosts) -> None:
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

    def delete(self, hostname: str) -> None:
        """Remove the host from the Puppet master and PuppetDB.

        Clean up signed certs, cached facts, node objects, and reports in the Puppet master, deactivate it in PuppetDB.
        Doesn't raise exception if the host was already removed.

        Arguments:
            hostname (str): the FQDN of the host for which to remove the certificate.

        """
        commands = ['puppet node {action} {host}'.format(action=action, host=hostname)
                    for action in ('clean', 'deactivate')]
        self._master_host.run_sync(*commands)

    def destroy(self, hostname: str) -> None:
        """Remove the certificate for the given hostname.

        If there is no certificate to remove it doesn't raise exception as the Puppet CA just outputs
        'Nothing was deleted'.

        Arguments:
            hostname (str): the FQDN of the host for which to remove the certificate.

        """
        self._master_host.run_sync('puppet ca destroy {host}'.format(host=hostname))

    def verify(self, hostname: str) -> None:
        """Verify that there is a valid certificate signed by the Puppet CA for the given hostname.

        Arguments:
            hostname (str): the FQDN of the host for which to verify the certificate.

        Raises:
            spicerack.puppet.PuppetMasterError: if the certificate is not valid.

        """
        response = self._run_json_command('puppet ca --render-as json verify {host}'.format(host=hostname))

        if not response['valid']:  # type: ignore
            raise PuppetMasterError(
                'Invalid certificate for {host}: {error}'.format(
                    host=hostname, error=response['error']))  # type: ignore

    def sign(self, hostname: str, fingerprint: str, allow_alt_names: bool = False) -> None:
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
    def wait_for_csr(self, hostname: str) -> None:
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

    def get_certificate_metadata(self, hostname: str) -> Dict:
        """Return the metadata of the certificate of the given hostname in the Puppet CA.

        Arguments:
            hostname (str): the FQDN of the host for which to verify the certificate.

        Returns:
            dict: as returned by the Puppet CA CLI with the render as JSON option set. As example::

                {
                    'dns_alt_names': ['DNS:service.example.com'],
                    'fingerprint': '00:FF:...',
                    'fingerprints': {
                        'SHA1': '00:FF:...',
                        'SHA256': '00:FF:...',
                        'SHA512': '00:FF:...',
                        'default': '00:FF:...',
                    },
                    'name': 'host.example.com',
                    'state': 'signed',
                }

        Raises:
            spicerack.puppet.PuppetMasterCheckError: if no certificate is found.
            spicerack.puppet.PuppetMasterError: if more than one certificate is found or it has invalid data.

        """
        response = self._run_json_command('puppet ca --render-as json list --all --subject "{pattern}"'.format(
            pattern=hostname.replace('.', r'\.')))

        if not response:
            raise PuppetMasterCheckError('No certificate found for hostname: {host}'.format(host=hostname))

        if len(response) > 1:
            raise PuppetMasterError('Expected one result from Puppet CA, got {num}'.format(num=len(response)))

        metadata = response[0]
        if metadata['name'] != hostname:
            raise PuppetMasterError(
                'Hostname mismatch {name} != {host}'.format(name=metadata['name'], host=hostname))

        return metadata

    def _run_json_command(self, command: str) -> Union[Dict, List]:
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
