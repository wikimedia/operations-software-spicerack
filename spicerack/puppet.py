"""Puppet module."""

import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Optional, Union, cast

from cumin import NodeSet, nodeset
from cumin.transports import Command
from wmflib.dns import Dns

from spicerack.administrative import Reason
from spicerack.decorators import retry
from spicerack.exceptions import SpicerackCheckError, SpicerackError
from spicerack.remote import RemoteExecutionError, RemoteHosts, RemoteHostsAdapter

PUPPET_COMMON_SCRIPT: str = "/usr/local/share/bash/puppet-common.sh"
"""The absolute path of the puppet-common script shipped by Puppet with useful functions."""
logger = logging.getLogger(__name__)


def get_ca_via_srv_record(domain: str) -> str:
    """Lookup the CA Server via the domain srv record."""
    question = f"_x-puppet-ca._tcp.{domain}"
    response = Dns().resolve(question, "SRV")
    if not response.rrset:
        raise SpicerackError(f"Unable to find record for {question}")
    answers = [str(rdata.target) for rdata in response.rrset]
    if len(answers) > 1:
        raise SpicerackError(f"{question} returned multiple ca servers: {','.join(answers)}")
    return answers[0].rstrip(".")


def get_puppet_ca_hostname() -> str:
    """Return the FQDN of the current Puppet CA server.

    Raises:
        spicerack.puppet.PuppetServerError: if unable to get the configured Puppet CA server.

    """
    return "puppetmaster1001.eqiad.wmnet"


class PuppetHostsError(SpicerackError):
    """Custom base exception class for errors in the PuppetHosts class."""


class PuppetHostsCheckError(SpicerackCheckError):
    """Custom base exception class for check errors in the PuppetHosts class."""


class PuppetServerError(SpicerackError):
    """Custom base exception class for errors in the PuppetMaster class."""


class PuppetServerCheckError(SpicerackCheckError):
    """Custom exception class for check errors in the PuppetMaster class."""


class PuppetHosts(RemoteHostsAdapter):
    """Class to manage Puppet on the target hosts."""

    @contextmanager
    def disabled(self, reason: Reason, verbatim_reason: bool = False) -> Iterator[None]:
        """Context manager to perform actions while puppet is disabled.

        Arguments:
            reason: the reason to set for the Puppet disable and to use for the Puppet enable.
            verbatim_reason: if true use the reason value verbatim.

        """
        self.disable(reason, verbatim_reason)
        try:
            yield
        finally:
            self.enable(reason, verbatim_reason)

    def get_ca_servers(self) -> dict[str, str]:
        """Retrieve the ca_servers for each node."""
        host_to_use_srv_records = self.get_config("use_srv_records")
        host_use_srv = nodeset()
        host_ca_server = nodeset()

        for hostname, use_srv_records in host_to_use_srv_records.items():
            if use_srv_records == "true":
                host_use_srv.add(hostname)
            else:
                host_ca_server.add(hostname)

        host_to_srv_domain = {}
        host_to_ca_server = {}

        if len(host_use_srv) > 0:
            host_to_srv_domain = PuppetHosts(self._remote_hosts.get_subset(host_use_srv)).get_config("srv_domain")
        if len(host_ca_server) > 0:
            host_to_ca_server = PuppetHosts(self._remote_hosts.get_subset(host_ca_server)).get_config("ca_server")

        answers = {}
        for fqdn, srv_domain in host_to_srv_domain.items():
            if srv_domain not in answers:
                ca_server = get_ca_via_srv_record(srv_domain)
                answers[srv_domain] = ca_server
            host_to_ca_server[fqdn] = answers[srv_domain]
        return host_to_ca_server

    def get_config(self, config: str, *, section: str = "agent") -> dict[str, str]:
        """Retrieve the ca_servers for each node."""
        raw_results = self._remote_hosts.run_sync(f"puppet config --section {section} print {config}")

        host_to_config: dict[str, str] = {}
        for node_set, output in raw_results:
            config = list(output.lines())[-1].decode()
            host_to_config.update({host: config for host in node_set})

        return host_to_config

    @staticmethod
    def _puppet_reason(reason: Reason, verbatim_reason: bool = False) -> str:
        """Return a correctly quoted puppet message.

        Arguments:
            reason: the reason to set for the Puppet disable.
            verbatim_reason: if true use the reason value verbatim.

        """
        if verbatim_reason:
            return f'"{reason.reason}"'
        return reason.quoted()

    def disable(self, reason: Reason, verbatim_reason: bool = False) -> None:
        """Disable puppet with a specific reason.

        If Puppet was already disabled on a host with a different reason, the reason will not be overriden, allowing to
        leave Puppet disabled when re-enabling it if it was already disabled.

        Arguments:
            reason: the reason to set for the Puppet disable.
            verbatim_reason: if true use the reason value verbatim.

        """
        logger.info(
            "Disabling Puppet with reason %s on %d hosts: %s",
            reason.quoted(),
            len(self),
            self,
        )
        self._remote_hosts.run_sync("disable-puppet " + self._puppet_reason(reason, verbatim_reason))

    def enable(self, reason: Reason, verbatim_reason: bool = False) -> None:
        """Enable Puppet with a specific reason, it must be the same used to disable it.

        Puppet will be re-enabled only if it was disable with the same reason. If it was disable with a different reason
        it will keep being disabled.

        Arguments:
            reason: the reason to use for the Puppet enable.
            verbatim_reason: if true use the reason value verbatim.

        """
        logger.info(
            "Enabling Puppet with reason %s on %d hosts: %s",
            reason.quoted(),
            len(self),
            self,
        )
        self._remote_hosts.run_sync("enable-puppet " + self._puppet_reason(reason, verbatim_reason))

    def check_enabled(self) -> None:
        """Check if Puppet is enabled on all hosts.

        Raises:
            spicerack.puppet.PuppetHostsCheckError: if Puppet is disabled on some hosts.

        """
        disabled = self._get_disabled()[True]
        if disabled:
            raise PuppetHostsCheckError(f"Puppet is not enabled on those hosts: {disabled}")

    def check_disabled(self) -> None:
        """Check if Puppet is disabled on all hosts.

        Raises:
            spicerack.puppet.PuppetHostsCheckError: if Puppet is enabled on some hosts.

        """
        enabled = self._get_disabled()[False]
        if enabled:
            raise PuppetHostsCheckError(f"Puppet is not disabled on those hosts: {enabled}")

    def run(  # pylint: disable=too-many-arguments
        self,
        *,
        timeout: int = 300,
        enable_reason: Optional[Reason] = None,
        quiet: bool = False,
        failed_only: bool = False,
        force: bool = False,
        attempts: int = 0,
        batch_size: int = 10,
    ) -> None:
        """Run Puppet.

        Arguments:
            timeout: the timeout in seconds to set in Cumin for the execution of the command.
            enable_reason: the reason to use to contextually re-enable Puppet if it was disabled.
            quiet: suppress Puppet output if True.
            failed_only: run Puppet only if the last run failed.
            force: forcely re-enable Puppet if it was disabled with ANY message.
            attempts: override the default number of attempts waiting that an in-flight Puppet run completes before
                timing out as set in run-puppet-agent.
            batch_size: how many concurrent Puppet runs to perform. The default value is tailored to not overload the
                Puppet masters.

        """
        args = []
        if enable_reason is not None:
            args += ["--enable", enable_reason.quoted()]
        if quiet:
            args.append("--quiet")
        if failed_only:
            args.append("--failed-only")
        if force:
            args.append("--force")
        if attempts:
            args += ["--attempts", str(attempts)]

        args_string = " ".join(args)
        command = f"run-puppet-agent {args_string}".strip()
        logger.info("Running Puppet with args '%s' on %d hosts: %s", args_string, len(self), self)
        self._remote_hosts.run_sync(Command(command, timeout=timeout), batch_size=batch_size)

    def first_run(self, has_systemd: bool = True) -> Iterator[tuple]:
        """Perform the first Puppet run on a clean host without using custom wrappers.

        Arguments:
            has_systemd: if the host has systemd as init system.

        """
        commands = []
        if has_systemd:
            commands += [
                "systemctl stop puppet.service",
                "systemctl reset-failed puppet.service || true",
            ]

        commands += [
            "puppet agent --enable",
            Command(
                "puppet agent --onetime --no-daemonize --verbose --no-splay --show_diff --no-usecacheonfailure",
                timeout=10800,
            ),
        ]

        logger.info("Starting first Puppet run (sit back, relax, and enjoy the wait)")
        results = self._remote_hosts.run_sync(*commands, print_output=False, print_progress_bars=False)
        logger.info("First Puppet run completed")
        return results

    def regenerate_certificate(self) -> dict[str, str]:
        """Delete the local Puppet certificate and generate a new CSR.

        Returns:
            A dictionary with hostnames as keys and CSR fingerprint as values.

        """
        logger.info("Deleting local Puppet certificate on %d hosts: %s", len(self), self)
        self._remote_hosts.run_sync("rm -rfv /var/lib/puppet/ssl")

        fingerprints = {}
        errors = []
        # The return codes for the cert generation are not well defined, we'll
        # check if it worked by searching for the fingerprint and parsing the
        # output.
        command = Command("puppet agent --test --color=false", ok_codes=[])
        logger.info("Generating a new Puppet certificate on %d hosts: %s", len(self), self)
        for node_set, output in self._remote_hosts.run_sync(command, print_output=False):
            for line in output.message().decode().splitlines():
                if line.startswith("Error:"):
                    errors.append((node_set, line))
                    continue

                if "Certificate Request fingerprint" not in line:
                    continue

                fingerprint = ":".join(line.split(":")[2:]).strip()
                if not fingerprint:
                    continue

                logger.info("Generated CSR for host %s: %s", node_set, fingerprint)
                for host in node_set:
                    fingerprints[host] = fingerprint

        if len(fingerprints) != len(self):
            raise PuppetHostsError(
                "Unable to find CSR fingerprints for all hosts, detected errors are:\n"
                + "\n".join(f"{node_set}: {line}" for node_set, line in errors)
            )

        return fingerprints

    def wait(self) -> None:
        """Wait until the next successful Puppet run is completed."""
        self.wait_since(datetime.utcnow())

    @retry(
        tries=60,
        delay=timedelta(seconds=30),
        backoff_mode="linear",
        exceptions=(PuppetHostsCheckError,),
    )
    def wait_since(self, start: datetime) -> None:
        """Wait until a successful Puppet run is completed after the start time.

        Arguments:
            start: wait until a Puppet run is completed after this time.

        Raises:
            spicerack.puppet.PuppetHostsCheckError: if unable to get a successful Puppet run within the timeout.

        """
        remaining_nodes = self._remote_hosts.hosts
        command = (
            f"source {PUPPET_COMMON_SCRIPT} && last_run_success && "
            "awk /last_run/'{ print $2 }' \"${PUPPET_SUMMARY}\""
        )

        logger.debug("Polling the completion of a successful Puppet run")
        try:
            for node_set, output in self._remote_hosts.run_sync(
                command, is_safe=True, print_output=False, print_progress_bars=False
            ):
                last_run = datetime.utcfromtimestamp(int(output.message().decode()))
                if last_run <= start:
                    raise PuppetHostsCheckError(f"Successful Puppet run too old ({last_run} <= {start}) on: {node_set}")

                remaining_nodes.difference_update(node_set, strict=False)

        except RemoteExecutionError as e:
            raise PuppetHostsCheckError("Unable to find a successful Puppet run") from e

        if remaining_nodes:
            raise PuppetHostsCheckError(f"Unable to get successful Puppet run from: {remaining_nodes}")

        logger.info("Successful Puppet run found")

    def _get_disabled(self) -> dict[bool, NodeSet]:
        """Check if Puppet is disabled on the hosts.

        Returns:
            A dict with :py:class:`bool` keys for Puppet disabled or not and hosts
            :py:class:`ClusterShell.NodeSet.NodeSet` as values.

        """
        results = self._remote_hosts.run_sync(
            f'source {PUPPET_COMMON_SCRIPT} && test -f "${{PUPPET_DISABLEDLOCK}}" && echo "1" || echo "0"',
            is_safe=True,
            print_output=False,
            print_progress_bars=False,
        )

        disabled = {True: nodeset(), False: nodeset()}
        for node_set, output in results:
            result = bool(int(output.message().decode().strip()))
            disabled[result] |= node_set

        return disabled


class PuppetServer(RemoteHostsAdapter):
    """Class to manage nodes and certificates on a Puppet server and Puppet CA server."""

    PUPPET_CERT_STATE_REQUESTED: str = "requested"
    """Puppet CA certificate status when requested."""
    PUPPET_CERT_STATE_SIGNED: str = "signed"
    """Puppet CA certificate status when signed."""

    # NOTE: this is shared
    def __init__(self, server_host: RemoteHosts) -> None:
        """Initialize the instance.

        Arguments:
            server_host: the remote hosts instance for the Puppetserver and Puppet CA server. It must have only one
                target host.

        Raises:
            spicerack.puppet.PuppetServerError: if the server_host doesn't have only one target host.

        """
        if len(server_host) != 1:
            raise PuppetServerError(
                f"The server_host instance must target only one host, got {len(server_host)}: {server_host}"
            )
        super().__init__(server_host)

    def delete(self, hostname: str) -> None:
        """Remove the host from the Puppet server and PuppetDB.

        Clean up signed certs, cached facts, node objects, and reports in the Puppet server, deactivate it in PuppetDB.
        Doesn't raise exception if the host was already removed.

        Arguments:
            hostname: the FQDN of the host for which to remove the certificate.

        """
        commands = [f"puppet node {action} {hostname}" for action in ("clean", "deactivate")]
        self._remote_hosts.run_sync(*commands, print_progress_bars=False)

    def destroy(self, hostname: str) -> None:
        """Remove the certificate for the given hostname.

        If there is no certificate to remove it doesn't raise exception.

        Arguments:
            hostname: the FQDN of the host for which to remove the certificate.

        Raises:
            spicerack.remote.RemoteExecutionError: if unable to destroy the certificate.

        """
        try:
            self.get_certificate_metadata(hostname)
        except PuppetServerCheckError:
            logger.info("The certificate for %s does not exist, nothing to do.", hostname)
            return

        self._remote_hosts.run_sync(f"puppetserver ca clean --certname {hostname}", print_progress_bars=False)

    def verify(self, hostname: str) -> None:
        """Verify that there is a valid certificate signed by the Puppet CA for the given hostname.

        Arguments:
            hostname: the FQDN of the host for which to verify the certificate.

        Raises:
            spicerack.puppet.PuppetServerError: if the certificate is not valid.

        """
        cert = self.get_certificate_metadata(hostname)
        if cert["state"] != PuppetServer.PUPPET_CERT_STATE_SIGNED:
            raise PuppetServerError(f"Expected certificate for {hostname} to be signed, got: {cert['state']}")

    def sign(self, hostname: str, fingerprint: str) -> None:
        """Sign a CSR on the Puppet CA for the given host checking its fingerprint.

        Arguments:
            hostname: the FQDN of the host for which to sign the certificate.
            fingerprint: the fingerprint of the CSR generated on the client to verify it.

        Raises:
            spicerack.puppet.PuppetServerError: if the certificate is in an unexpected state.

        """
        cert = self.get_certificate_metadata(hostname)
        if cert["state"] != PuppetServer.PUPPET_CERT_STATE_REQUESTED:
            raise PuppetServerError(f"Certificate for {hostname} not in requested state, got: {cert['state']}")

        if cert["fingerprint"] != fingerprint:
            raise PuppetServerError(
                f"CSR fingerprint {cert['fingerprint']} for {hostname} does not match provided fingerprint "
                f"{fingerprint}"
            )

        logger.info("Signing CSR for %s with fingerprint %s", hostname, fingerprint)
        command = f"puppetserver ca sign --certname {hostname}"
        executed = self._remote_hosts.run_sync(command, print_output=False, print_progress_bars=False)

        cert = self.get_certificate_metadata(hostname)
        if cert["state"] != PuppetServer.PUPPET_CERT_STATE_SIGNED:
            for _, output in executed:
                logger.error(output.message().decode())

            raise PuppetServerError(f"Expected certificate for {hostname} to be signed, got: {cert['state']}")

    @retry(
        tries=10,
        delay=timedelta(seconds=5),
        backoff_mode="power",
        exceptions=(PuppetServerCheckError,),
    )
    def wait_for_csr(self, hostname: str) -> None:
        """Poll until a CSR appears for the given hostname or the timeout is reached.

        Arguments:
            hostname: the FQDN of the host for which to check a CSR.

        Raises:
            spicerack.puppet.PuppetServerError: if the certificate is in an unexpected state.
            spicerack.puppet.PuppetServerCheckError: if within the timeout no CSR is found.

        """
        state = self.get_certificate_metadata(hostname)["state"]
        if state != PuppetServer.PUPPET_CERT_STATE_REQUESTED:
            raise PuppetServerError(f"Expected certificate in requested state, got: {state}")

    def get_certificate_metadata(self, hostname: str) -> dict:
        """Return the metadata of the certificate of the given hostname in the Puppet CA.

        Arguments:
            hostname: the FQDN of the host for which to verify the certificate.

        Returns:
            As returned by the Puppet CA CLI with the render as JSON option set. As example::

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
            spicerack.puppet.PuppetServerCheckError: if no certificate is found.
            spicerack.puppet.PuppetServerError: if more than one certificate is found or it has invalid data.

        """
        response = self._run_json_command(f"puppetserver ca list --format json --certname {hostname}")

        if not response:
            raise PuppetServerCheckError(f"No certificate found for hostname: {hostname}")

        # The following should never happen however the return type of self._run_json_command is Dict | list.
        # So we add this to keep mypy happy
        if not isinstance(response, dict):
            raise PuppetServerCheckError(f"Expected a dict but got list: {response}")

        if len(response.keys()) > 1:
            raise PuppetServerError(f"Expected one result type from Puppet CA, got {len(response.keys())}")

        # key will be either signed, requested, revoked Expected
        # for now we don't return this information as it already exists in metadata['state']
        key = list(response.keys())[0]
        if key == "missing":
            raise PuppetServerCheckError(f"The puppet server has no CSR for {hostname}")

        if len(response[key]) > 1:
            raise PuppetServerError(f"Expected one result from Puppet CA, got {len(response[key])}")
        metadata = response[key][0]
        if metadata["name"] != hostname:
            raise PuppetServerError(f"Hostname mismatch {metadata['name']} != {hostname}")

        return metadata

    def _run_json_command(self, command: str) -> Union[dict, list]:
        """Execute and parse a Puppet CLI command that output JSON format.

        The commands run are assumed to be safe as the JSON format is useful for read-only operations only.

        Arguments:
            command: the command to execute on the Puppet server that returns JSON output.

        Raises:
            spicerack.puppet.PuppetServerError: if unable to get or parse the command output.

        """
        return_code = 0
        try:
            command_results = self._remote_hosts.run_sync(
                command, is_safe=True, print_output=False, print_progress_bars=False
            )
        except RemoteExecutionError as e:
            return_code = e.retcode
            command_results = e.results
        for _, output in command_results:
            lines = output.message().decode()
            break
        else:
            raise PuppetServerError(
                f"Got no output from Puppet server while executing command (rc: {return_code}): {command}"
            )
        try:
            response = json.loads(lines)
        except ValueError as e:
            raise PuppetServerError(
                f'Unable to parse Puppet server response for command (rc: {return_code}): "{command}": {lines}'
            ) from e

        return response

    def hiera_lookup(self, fqdn: str, key: str, *, fmt: str = "s") -> str:
        """Lookup a hiera value for a specific host.

        Arguments:
            fqdn: the fqdn whose values we are looking up
            key: the hiera key to lookup
            fmt: how Puppet will render the object: 's' (PSON, default), 'json', 'yaml'

        """
        command = f"puppet lookup --render-as {fmt} --compile --node {fqdn} {key} 2>/dev/null"
        result = self._remote_hosts.run_sync(command, is_safe=True, print_output=False, print_progress_bars=False)
        _, output = next(result)
        return output.message().decode()


class PuppetMaster(PuppetServer):
    """Class to manage nodes and certificates on a Puppet master and Puppet CA server."""

    def destroy(self, hostname: str) -> None:
        """Remove the certificate for the given hostname.

        If there is no certificate to remove it doesn't raise exception as the Puppet CA just outputs
        'Nothing was deleted'.

        Arguments:
            hostname: the FQDN of the host for which to remove the certificate.

        """
        self._remote_hosts.run_sync(
            f"puppet ca --disable_warnings deprecations destroy {hostname}", print_progress_bars=False
        )

    def verify(self, hostname: str) -> None:
        """Verify that there is a valid certificate signed by the Puppet CA for the given hostname.

        Arguments:
            hostname: the FQDN of the host for which to verify the certificate.

        Raises:
            spicerack.puppet.PuppetServerError: if the certificate is not valid.

        """
        response = cast(
            dict,
            self._run_json_command(f"puppet ca --disable_warnings deprecations --render-as json verify {hostname}"),
        )

        if not response["valid"]:
            raise PuppetServerError(f"Invalid certificate for {hostname}: {response['error']}")

    def sign(self, hostname: str, fingerprint: str) -> None:
        """Sign a CSR on the Puppet CA for the given host checking its fingerprint.

        Arguments:
            hostname: the FQDN of the host for which to sign the certificate.
            fingerprint: the fingerprint of the CSR generated on the client to verify it.

        Raises:
            spicerack.puppet.PuppetServerError: if the certificate is in an unexpected state.

        """
        cert = self.get_certificate_metadata(hostname)
        if cert["state"] != PuppetMaster.PUPPET_CERT_STATE_REQUESTED:
            raise PuppetServerError(f"Certificate for {hostname} not in requested state, got: {cert['state']}")

        if cert["fingerprint"] != fingerprint:
            raise PuppetServerError(
                f"CSR fingerprint {cert['fingerprint']} for {hostname} does not match provided fingerprint "
                f"{fingerprint}"
            )

        command = f"puppet cert --disable_warnings deprecations sign {hostname}"
        logger.info("Signing CSR for %s with fingerprint %s", hostname, fingerprint)
        executed = self._remote_hosts.run_sync(command, print_output=False, print_progress_bars=False)

        cert = self.get_certificate_metadata(hostname)
        if cert["state"] != PuppetMaster.PUPPET_CERT_STATE_SIGNED:
            for _, output in executed:
                logger.error(output.message().decode())

            raise PuppetServerError(f"Expected certificate for {hostname} to be signed, got: {cert['state']}")

    def get_certificate_metadata(self, hostname: str) -> dict:
        """Return the metadata of the certificate of the given hostname in the Puppet CA.

        Arguments:
            hostname: the FQDN of the host for which to verify the certificate.

        Returns:
            As returned by the Puppet CA CLI with the render as JSON option set. As example::

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
            spicerack.puppet.PuppetServerCheckError: if no certificate is found.
            spicerack.puppet.PuppetServerError: if more than one certificate is found or it has invalid data.

        """
        pattern = hostname.replace(".", r"\.")
        response = self._run_json_command(
            f'puppet ca --disable_warnings deprecations --render-as json list --all --subject "^{pattern}$"'
        )

        if not response:
            raise PuppetServerCheckError(f"No certificate found for hostname: {hostname}")

        if len(response) > 1:
            raise PuppetServerError(f"Expected one result from Puppet CA, got {len(response)}")

        metadata = response[0]
        if metadata["name"] != hostname:
            raise PuppetServerError(f"Hostname mismatch {metadata['name']} != {hostname}")

        return metadata
