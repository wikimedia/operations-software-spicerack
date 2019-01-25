"""IPMI module.

Todo:
    replace with pyghmi.
"""
import logging
import os

from datetime import timedelta
from subprocess import CalledProcessError, check_output  # nosec

from spicerack.decorators import retry
from spicerack.exceptions import SpicerackCheckError, SpicerackError


IPMI_SAFE_BOOT_PARAMS = ('0000000000', '8000020000')  # No or unimportant overrides.
logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


class IpmiError(SpicerackError):
    """Custom exception class for errors of the Ipmi class."""


class IpmiCheckError(SpicerackCheckError):
    """Custom exception class for check errors of the Ipmi class."""


class Ipmi:
    """Class to manage remote IPMI via ipmitool."""

    def __init__(self, password, dry_run=True):
        """Initialize the instance.

        Arguments:
            password (str): the password to use to connect via IPMI.
            dry_run (bool, optional): whether this is a DRY-RUN.
        """
        # FIXME: move to subprocess.run() with env once Python 3.4 support is dropped or directly to pyghmi.
        os.environ['IPMITOOL_PASSWORD'] = password
        self._dry_run = dry_run

    def command(self, mgmt_hostname, command_parts, is_safe=False):  # pylint: disable=no-self-use
        """Run an ipmitool command for a remote management console hostname.

        Arguments:
            mgmt_hostname (str): the FQDN of the management interface of the host to target.
            command_parts (list): a list of :py:class:`str` with the IPMI command components to execute.
            is_safe (bool, optional): if this is a safe command to run also in DRY RUN mode.

        Returns:
            str: the output of the ipmitool command.

        Raises:
            spicerack.ipmi.IpmiError: on failure.

        """
        command = ['ipmitool', '-I', 'lanplus', '-H', mgmt_hostname, '-U', 'root', '-E'] + command_parts
        logger.info('Running IPMI command: %s', ' '.join(command))

        if self._dry_run and not is_safe:
            return ''

        try:
            output = check_output(command).decode()  # nosec
        except CalledProcessError as e:
            raise IpmiError('Remote IPMI for {mgmt} failed (exit={code}): {output}'.format(
                mgmt=mgmt_hostname, code=e.returncode, output=e.output)) from e

        logger.debug(output)

        return output

    def check_connection(self, mgmt_hostname):
        """Ensure that remote IPMI is working for the management console hostname.

        Arguments:
            mgmt_hostname (str): the FQDN of the management interface of the host to target.

        Raises:
            spicerack.ipmi.IpmiError: if unable to connect or execute a test command.

        """
        status = self.command(mgmt_hostname, ['chassis', 'power', 'status'], is_safe=True)
        if not status.startswith('Chassis Power is'):
            raise IpmiError('Unexpected chassis status: {status}'.format(status=status))

    def check_bootparams(self, mgmt_hostname):
        """Check if the BIOS boot parameters are back to normal values.

        Arguments:
            mgmt_hostname (str): the FQDN of the management interface of the host to target.

        Raises:
            spicerack.ipmi.IpmiCheckError: if the BIOS boot parameters are incorrect.

        """
        param = self._get_boot_parameter(mgmt_hostname, 'Boot parameter data')
        if param not in IPMI_SAFE_BOOT_PARAMS:
            raise IpmiCheckError('Expected BIOS boot params in {accepted} got: {param}'.format(
                accepted=IPMI_SAFE_BOOT_PARAMS, param=param))

    @retry(tries=3, delay=timedelta(seconds=20), backoff_mode='linear', exceptions=(IpmiCheckError,))
    def force_pxe(self, mgmt_hostname):
        """Force PXE for the next boot and verify that the setting was applied.

        Arguments:
            mgmt_hostname (str): the FQDN of the management interface of the host to target.

        Raises:
            spicerack.ipmi.IpmiCheckError: if unable to verify the PXE mode within the retries.

        """
        self.command(mgmt_hostname, ['chassis', 'bootdev', 'pxe'])
        boot_device = self._get_boot_parameter(mgmt_hostname, 'Boot Device Selector')
        if boot_device != 'Force PXE':
            raise IpmiCheckError('Unable to verify that Force PXE is set. The host might reboot in the current OS')

    def _get_boot_parameter(self, mgmt_hostname, param_label):
        """Get a specific boot parameter of the host.

        Arguments:
            mgmt_hostname (str): the FQDN of the management interface of the host to target.
            param_label (str): the label of the boot parameter to lookout for.

        Raises:
            spicerack.ipmi.IpmiError: if unable to find the given label or to extract its value.

        Returns:
            str: the value of the parameter.

        """
        bootparams = self.command(mgmt_hostname, ['chassis', 'bootparam', 'get', '5'], is_safe=True)
        for line in bootparams.splitlines():
            if param_label in line:
                try:
                    value = line.split(':')[1].strip(' \n')
                    break
                except IndexError:
                    raise IpmiError("Unable to extract value for parameter '{label}' from line: {line}".format(
                        label=param_label, line=line))
        else:
            raise IpmiError("Unable to find the boot parameter '{label}' in: {output}".format(
                label=param_label, output=bootparams))

        return value
