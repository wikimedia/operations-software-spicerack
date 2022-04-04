"""IPMI module.

Todo:
    replace with pyghmi.

"""
import logging
from datetime import timedelta
from subprocess import PIPE, CalledProcessError, run
from typing import Dict, List, Tuple

from spicerack.decorators import retry
from spicerack.exceptions import SpicerackCheckError, SpicerackError

IPMI_PASSWORD_MAX_LEN: int = 20
IPMI_PASSWORD_MIN_LEN: int = 16
IPMI_SAFE_BOOT_PARAMS: Tuple[str, ...] = (
    "0000000000",  # No overrides
    "8000000000",  # Boot Flag Valid
    "8000020000",  # Boot Flag Valid and Screen blank
)
logger = logging.getLogger(__name__)


class IpmiError(SpicerackError):
    """Custom exception class for errors of the Ipmi class."""


class IpmiCheckError(SpicerackCheckError):
    """Custom exception class for check errors of the Ipmi class."""


class Ipmi:
    """Class to manage remote IPMI via ipmitool."""

    def __init__(self, mgmt_fqdn: str, password: str, dry_run: bool = True) -> None:
        """Initialize the instance.

        Arguments:
            mgmt_fqdn (str): the management console FQDN to target.
            password (str): the password to use to connect via IPMI.
            dry_run (bool, optional): whether this is a DRY-RUN.

        """
        self.env: Dict[str, str] = {"IPMITOOL_PASSWORD": password}
        self._mgmt_fqdn = mgmt_fqdn
        self._dry_run = dry_run

    def command(self, command_parts: List[str], is_safe: bool = False, hide_parts: Tuple = ()) -> str:
        """Run an ipmitool command for a remote management console FQDN.

        Arguments:
            command_parts (list): a list of :py:class:`str` with the IPMI command components to execute.
            is_safe (bool, optional): if this is a safe command to run also in DRY RUN mode.
            hide_parts (tuple, optional): tuple with indexes of the command_parts list that should be redacted in logs
                and outputs because contain sensitive data. For example setting it to (2, 4) would replace in logs and
                outputs the 3rd and 5th element of the command_parts list.

        Returns:
            str: the output of the ipmitool command.

        Raises:
            spicerack.ipmi.IpmiError: on failure.

        """
        command = [
            "ipmitool",
            "-I",
            "lanplus",
            "-H",
            self._mgmt_fqdn,
            "-U",
            "root",
            "-E",
        ]
        redacted_parts = command_parts[:]
        for i in hide_parts:
            redacted_parts[i] = "__REDACTED__"

        logger.info("Running IPMI command: %s", " ".join(command + redacted_parts))

        if self._dry_run and not is_safe:
            return ""

        try:
            output = run(command + command_parts, env=self.env.copy(), stdout=PIPE, check=True).stdout.decode()
        except CalledProcessError as e:
            raise IpmiError(f"Remote IPMI for {self._mgmt_fqdn} failed (exit={e.returncode}): {e.output}") from e

        logger.debug(output)

        return output

    def check_connection(self) -> None:
        """Ensure that remote IPMI is working for the management console FQDN.

        Raises:
            spicerack.ipmi.IpmiError: if unable to connect or execute a test command.

        """
        self.power_status()

    def power_status(self) -> str:
        """Get the current power status for the management console FQDN.

        Raises:
            spicerack.ipmi.IpmiError: if unable to get the power status.

        """
        identifier = "Chassis Power is "
        status = self.command(["chassis", "power", "status"], is_safe=True)
        if not status.startswith(identifier):
            raise IpmiError(f"Unexpected chassis status: {status}")

        return status[len(identifier) :].strip()

    def check_bootparams(self) -> None:
        """Check if the BIOS boot parameters are back to normal values.

        Raises:
            spicerack.ipmi.IpmiCheckError: if the BIOS boot parameters are incorrect.

        """
        param = self._get_boot_parameter("Boot parameter data")
        if param not in IPMI_SAFE_BOOT_PARAMS:
            raise IpmiCheckError(f"Expected BIOS boot params in {IPMI_SAFE_BOOT_PARAMS} got: {param}")

    @retry(
        tries=3,
        delay=timedelta(seconds=20),
        backoff_mode="linear",
        exceptions=(IpmiCheckError,),
    )
    def force_pxe(self) -> None:
        """Force PXE for the next boot and verify that the setting was applied.

        Raises:
            spicerack.ipmi.IpmiCheckError: if unable to verify the PXE mode within the retries.

        """
        self.command(["chassis", "bootparam", "set", "bootflag", "force_pxe", "options=reset"])
        boot_device = self._get_boot_parameter("Boot Device Selector")
        if boot_device != "Force PXE":
            message = "Unable to verify that Force PXE is set. The host might reboot in the current OS"
            if self._dry_run:
                logger.warning(message)
            else:
                raise IpmiCheckError(message)

    def remove_boot_override(self) -> None:
        """Remove any boot override, if present for the next boot and verify that the change was applied.

        Raises:
            spicerack.ipmi.IpmiCheckError: if unable to verify the boot mode.

        """
        self.command(["chassis", "bootparam", "set", "bootflag", "none", "options=reset"])
        boot_device = self._get_boot_parameter("Boot Device Selector")
        if boot_device != "No override":
            message = "Unable to verify that the boot override was removed. The host might reboot in PXE"
            if self._dry_run:
                logger.warning(message)
            else:
                raise IpmiCheckError(message)

    def reboot(self) -> None:
        """Reboot a host via IPMI, either performing a power cycle or a power on based on the power status."""
        status = self.power_status()
        if status == "off":
            operation = "on"
        else:
            operation = "cycle"

        self.command(["chassis", "power", operation])

    def _get_boot_parameter(self, param_label: str) -> str:
        """Get a specific boot parameter of the host.

        Arguments:
            param_label (str): the label of the boot parameter to lookout for.

        Raises:
            spicerack.ipmi.IpmiError: if unable to find the given label or to extract its value.

        Returns:
            str: the value of the parameter.

        """
        bootparams = self.command(["chassis", "bootparam", "get", "5"], is_safe=True)
        for line in bootparams.splitlines():
            if param_label in line:
                try:
                    value = line.split(":")[1].strip(" \n")
                    break
                except IndexError as e:
                    raise IpmiError(f"Unable to extract value for parameter '{param_label}' from line: {line}") from e
        else:
            raise IpmiError(f"Unable to find the boot parameter '{param_label}' in: {bootparams}")
        return value

    @staticmethod
    def _get_password_store_size(password: str) -> int:
        """Parse the password to determine the correct storage size.

        Ipmitool stores passwords in either 16 or 20 byte strings depending
        on the password length.

        Arguments:
            password(str): the password string to parse

        Raises:
            spicerack.ipmi.IpmiError: if unable password is too big or too small

        Returns:
            int: A number representing the storage size

        """
        if len(password) > IPMI_PASSWORD_MAX_LEN:
            raise IpmiError(f"New passwords is greater then the {IPMI_PASSWORD_MAX_LEN} byte limit")
        if len(password) > IPMI_PASSWORD_MIN_LEN:
            return IPMI_PASSWORD_MAX_LEN
        if len(password) == IPMI_PASSWORD_MIN_LEN:
            return IPMI_PASSWORD_MIN_LEN
        raise IpmiError(f"New passwords must be {IPMI_PASSWORD_MIN_LEN} bytes minimum")

    def reset_password(self, username: str, password: str) -> None:
        """Reset the given usernames password to the one provided.

        Arguments:
            username (str): The username who's password will be reset must not be empty
            password (str): The new password, length between :py:const:`spicerack.ipmi.IPMI_PASSWORD_MIN_LEN` and
             :py:const:`spicerack.ipmi.IPMI_PASSWORD_MAX_LEN` bytes

        Raises:
            spicerack.ipmi.IpmiError: if unable reset password or arguments invalid

        """
        if not username:
            raise IpmiError("Username can not be an empty string")

        password_store_size = str(Ipmi._get_password_store_size(password))

        try:
            user_id = self._get_user_id(username)
        except IpmiError:
            # some systems (HP?) use channel 2
            logger.info("unable to find user in channel 1 testing channel 2")
            user_id = self._get_user_id(username, 2)

        success = f"Set User Password command successful (user {user_id})\n"
        result = self.command(["user", "set", "password", user_id, password, password_store_size], hide_parts=(4,))

        if self._dry_run:
            return

        if result != success:
            raise IpmiError(f"Password reset failed for username: {username}")

        if username == "root":
            current_password = self.env["IPMITOOL_PASSWORD"]
            self.env["IPMITOOL_PASSWORD"] = password
            try:
                self.check_connection()
            except IpmiError as error:
                self.env["IPMITOOL_PASSWORD"] = current_password
                raise IpmiError("Password reset failed for username: root") from error

    def _get_user_id(self, username: str, channel: int = 1) -> str:
        """Get the user ID associated with a given username.

        Arguments:
            username (str): The username to search for
            channel (int): The channel number for the user list; Default: 1

        Raises:
            spicerack.ipmi.IpmiError: if unable to find the given username.

        Returns:
            str: the user ID associated with the username

        """
        userlist = self.command(["user", "list", str(channel)], is_safe=True)
        for line in userlist.splitlines():
            words = line.split()
            if words[0] == "ID":
                continue
            if words[1] == username:
                return words[0]
        raise IpmiError(f"Unable to find ID for username: {username}")
