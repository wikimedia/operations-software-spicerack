"""IPMI module.

Todo:
    replace with pyghmi.
"""
import logging
import os

from datetime import timedelta
from subprocess import CalledProcessError, check_output  # nosec
from typing import List

from spicerack.decorators import retry
from spicerack.exceptions import SpicerackCheckError, SpicerackError


IPMI_PASSWORD_MAX_LEN = 20
IPMI_PASSWORD_MIN_LEN = 16
IPMI_SAFE_BOOT_PARAMS = ('0000000000', '8000020000')  # No or unimportant overrides.
logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


class IpmiError(SpicerackError):
    """Custom exception class for errors of the Ipmi class."""


class IpmiCheckError(SpicerackCheckError):
    """Custom exception class for check errors of the Ipmi class."""


class Ipmi:
    """Class to manage remote IPMI via ipmitool."""

    def __init__(self, password: str, dry_run: bool = True) -> None:
        """Initialize the instance.

        Arguments:
            password (str): the password to use to connect via IPMI.
            dry_run (bool, optional): whether this is a DRY-RUN.
        """
        # FIXME: move to subprocess.run() with env once Python 3.4 support is dropped or directly to pyghmi.
        os.environ['IPMITOOL_PASSWORD'] = password
        self._dry_run = dry_run

    def command(  # pylint: disable=no-self-use
        self,
        mgmt_hostname: str,
        command_parts: List[str],
        is_safe: bool = False
    ) -> str:
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

    def check_connection(self, mgmt_hostname: str) -> None:
        """Ensure that remote IPMI is working for the management console hostname.

        Arguments:
            mgmt_hostname (str): the FQDN of the management interface of the host to target.

        Raises:
            spicerack.ipmi.IpmiError: if unable to connect or execute a test command.

        """
        status = self.command(mgmt_hostname, ['chassis', 'power', 'status'], is_safe=True)
        if not status.startswith('Chassis Power is'):
            raise IpmiError('Unexpected chassis status: {status}'.format(status=status))

    def check_bootparams(self, mgmt_hostname: str) -> None:
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
    def force_pxe(self, mgmt_hostname: str) -> None:
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

    def _get_boot_parameter(self, mgmt_hostname: str, param_label: str) -> str:
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

    def reset_password(self, mgmt_hostname: str, username: str, password: str) -> None:
        """Reset the given usernames password to the one provided

        Arguments:
            mgmt_hostname (str): the FQDN of the management interface of the host to target.
            username (str): The username who's password will be reset must not be empty
            password (str): The new password must have length between {min_len} and {max_len} bytes

        Raises:
            spicerack.ipmi.IpmiError: if unable reset password or arguments invalid

        """.format(min_len=IPMI_PASSWORD_MIN_LEN, max_len=IPMI_PASSWORD_MAX_LEN)
        # ipmitool stores passwords in either 16 or 20 byte strings
        # can't find much documentation on this
        if len(password) > IPMI_PASSWORD_MAX_LEN:
            raise IpmiError('New passwords is greater the IPMI {max_len} byte limit'.format(
                max_len=IPMI_PASSWORD_MAX_LEN))
        elif len(password) > IPMI_PASSWORD_MIN_LEN:
            password_store_size = str(IPMI_PASSWORD_MAX_LEN)
        elif len(password) == IPMI_PASSWORD_MIN_LEN:
            password_store_size = str(IPMI_PASSWORD_MIN_LEN)
        else:
            raise IpmiError('New passwords must be {min_len} bytes minimum'.format(
                min_len=IPMI_PASSWORD_MIN_LEN))

        if not username:
            raise IpmiError('Username can not be an empty string')

        user_id = self._get_user_id(mgmt_hostname, username)
        success = 'Set User Password command successful (user {user_id})\n'.format(
            user_id=user_id)
        result = self.command(
            mgmt_hostname,
            ['user', 'set', 'password', user_id, password, password_store_size])
        if self._dry_run:
            return
        if result != success:
            raise IpmiError('Password reset failed for username: {username}'.format(
                username=username))
        elif username == 'root':
            current_password = os.environ['IPMITOOL_PASSWORD']
            os.environ['IPMITOOL_PASSWORD'] = password
            try:
                self.check_connection(mgmt_hostname)
            except IpmiError as e:
                os.environ['IPMITOOL_PASSWORD'] = current_password
                raise IpmiError('Password reset failed for username: root') from e

    def _get_user_id(self, mgmt_hostname: str, username: str) -> str:
        """Get the user ID associated with a given username

        Arguments:
            mgmt_hostname (str): the FQDN of the management interface of the host to target.
            username (str): The username to search for

        Raises:
            spicerack.ipmi.IpmiError: if unable to find the given username.

        Returns:
            str: the user ID associated with the username

        """
        userlist = self.command(mgmt_hostname, ['user', 'list', '1'], is_safe=True)
        for line in userlist.splitlines():
            words = line.split()
            if words[0] == 'ID':
                continue
            if words[1] == username:
                return words[0]
        raise IpmiError("Unable to find ID for username: {username}".format(username=username))
