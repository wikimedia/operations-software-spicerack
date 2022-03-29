"""IPMI module tests."""

from subprocess import PIPE, CalledProcessError, CompletedProcess
from unittest import mock

import pytest

from spicerack import ipmi

ENV = {"IPMITOOL_PASSWORD": "password"}
IPMITOOL_BASE = [
    "ipmitool",
    "-I",
    "lanplus",
    "-H",
    "test-mgmt.example.com",
    "-U",
    "root",
    "-E",
]
BOOTPARAMS_OUTPUT = """
Boot parameter version: 1
Boot parameter 5 is valid/unlocked
Boot parameter data: {bootparams}
 Boot Flags :
   - Boot Flag Invalid
   - Options apply to only next boot
   - BIOS PC Compatible (legacy) boot
   - Boot Device Selector : {override}
   - Console Redirection control : System Default
   - BIOS verbosity : Console redirection occurs per BIOS configuration setting (default)
   - BIOS Mux Control Override : BIOS uses recommended setting of the mux at the end of POST
Invalid line
"""
USERLIST_OUTPUT = """ID  Name             Callin  Link Auth  IPMI Msg   Channel Priv Limit
1                    true    false      false      NO ACCESS
2   root             true    true       true       ADMINISTRATOR
3                    true    false      false      NO ACCESS
4                    true    false      false      NO ACCESS
5                    true    false      false      NO ACCESS
6                    true    false      false      NO ACCESS
7                    true    false      false      NO ACCESS
8                    true    false      false      NO ACCESS
9   user_number_9    true    false      false      NO ACCESS
10                   true    false      false      NO ACCESS
11                   true    false      false      NO ACCESS
12                   true    false      false      NO ACCESS
13                   true    false      false      NO ACCESS
14                   true    false      false      NO ACCESS
15                   true    false      false      NO ACCESS
16                   true    false      false      NO ACCESS
"""


class TestIpmi:
    """Test class for the Ipmi class."""

    def setup_method(self):
        """Setup the test environment."""
        # pylint: disable=attribute-defined-outside-init
        self.fqdn = "test-mgmt.example.com"
        self.ipmi = ipmi.Ipmi(self.fqdn, "password", dry_run=False)
        self.ipmi_dry_run = ipmi.Ipmi(self.fqdn, "password")

    def test_init(self):
        """It should initialize the instance and set the IPMITOOL_PASSWORD environment variable."""
        assert isinstance(self.ipmi, ipmi.Ipmi)

    @mock.patch("spicerack.ipmi.run", return_value=CompletedProcess((), 0, stdout=b"test"))
    def test_command_ok(self, mocked_run):
        """It should execute the IPMI command as expected."""
        assert self.ipmi.command(["test_command"]) == "test"
        mocked_run.assert_called_once_with(IPMITOOL_BASE + ["test_command"], env=ENV, stdout=PIPE, check=True)

    @mock.patch("spicerack.ipmi.run")
    def test_command_dry_run_ok(self, mocked_run):
        """It should not execute the IPMI command if in DRY RUN mode."""
        assert self.ipmi_dry_run.command(["test_command"]) == ""
        assert not mocked_run.called

    @mock.patch("spicerack.ipmi.run")
    def test_command_raise(self, mocked_run):
        """It should raise IpmiError if failed to execute the command."""
        mocked_run.side_effect = CalledProcessError(1, "executed_command")
        with pytest.raises(ipmi.IpmiError, match="Remote IPMI for test-mgmt.example.com failed"):
            self.ipmi.command(["test_command"])

    @mock.patch(
        "spicerack.ipmi.run",
        return_value=CompletedProcess((), 0, stdout=b"Chassis Power is on"),
    )
    def test_check_connection_ok(self, mocked_run):
        """It should check that the connection to the remote IPMI works running a simple command."""
        self.ipmi_dry_run.check_connection()
        mocked_run.assert_called_once_with(
            IPMITOOL_BASE + ["chassis", "power", "status"],
            env=ENV,
            stdout=PIPE,
            check=True,
        )

    @mock.patch(
        "spicerack.ipmi.run",
        return_value=CompletedProcess((), 0, stdout=b"Chassis Power is on\n"),
    )
    def test_power_status_ok(self, mocked_run):
        """It should return the current power status of the target host."""
        status = self.ipmi_dry_run.power_status()
        assert status == "on"
        mocked_run.assert_called_once_with(
            IPMITOOL_BASE + ["chassis", "power", "status"],
            env=ENV,
            stdout=PIPE,
            check=True,
        )

    @mock.patch("spicerack.ipmi.run", return_value=CompletedProcess((), 0, stdout=b"failed"))
    def test_power_status_raise(self, mocked_run):
        """It should raise IpmiError if unable to get the power status."""
        with pytest.raises(ipmi.IpmiError, match="Unexpected chassis status: failed"):
            self.ipmi.power_status()

        assert mocked_run.called

    @pytest.mark.parametrize("status, operation", (("on", "cycle"), ("off", "on")))
    @mock.patch("spicerack.ipmi.run")
    def test_reboot(self, mocked_run, status, operation):
        """It issue the proper reboot command based on the current power status."""
        mocked_run.return_value = CompletedProcess(
            (),
            0,
            stdout=f"Chassis Power is {status}\n".encode(),
        )
        self.ipmi.reboot()
        mocked_run.has_call(
            IPMITOOL_BASE + ["chassis", "power", operation],
            env=ENV,
            stdout=PIPE,
            check=True,
        )

    @mock.patch("spicerack.ipmi.run")
    def test_check_bootparams_ok(self, mocked_run):
        """It should check that the BIOS boot parameters are normal."""
        mocked_run.return_value = CompletedProcess(
            (),
            0,
            stdout=BOOTPARAMS_OUTPUT.format(bootparams="0000000000", override="No override").encode(),
        )
        self.ipmi.check_bootparams()
        mocked_run.assert_called_once_with(
            IPMITOOL_BASE + ["chassis", "bootparam", "get", "5"],
            env=ENV,
            stdout=PIPE,
            check=True,
        )

    @mock.patch("spicerack.ipmi.run")
    def test_check_bootparams_wrong_value(self, mocked_run):
        """It should raise IpmiCheckError if the BIOS boot parameters are not the normal ones."""
        mocked_run.return_value = CompletedProcess(
            (),
            0,
            stdout=BOOTPARAMS_OUTPUT.format(bootparams="0004000000", override="Force PXE").encode(),
        )
        with pytest.raises(
            ipmi.IpmiCheckError,
            match=r"Expected BIOS boot params in \('0000000000', '8000000000', '8000020000'\) got: 0004000000",
        ):
            self.ipmi_dry_run.check_bootparams()

        assert mocked_run.called

    @mock.patch(
        "spicerack.ipmi.run",
        return_value=CompletedProcess((), 0, stdout=b"Boot parameter data"),
    )
    def test_check_bootparams_unable_to_extract(self, mocked_run):
        """It should raise IpmiError if unable to extract the value of the BIOS boot parameters."""
        with pytest.raises(
            ipmi.IpmiError,
            match="Unable to extract value for parameter 'Boot parameter data'",
        ):
            self.ipmi.check_bootparams()

        assert mocked_run.called

    @mock.patch("spicerack.ipmi.run", return_value=CompletedProcess((), 0, stdout=b"Invalid"))
    def test_check_bootparams_missing_label(self, mocked_run):
        """It should raise IpmiError if unable to find the label looked for."""
        with pytest.raises(
            ipmi.IpmiError,
            match="Unable to find the boot parameter 'Boot parameter data'",
        ):
            self.ipmi.check_bootparams()

        assert mocked_run.called

    @mock.patch("wmflib.decorators.time.sleep", return_value=None)
    @mock.patch("spicerack.ipmi.run")
    def test_force_pxe_ok(self, mocked_run, mocked_sleep):
        """Should set the PXE boot mode for the next boot."""
        mocked_run.side_effect = [
            CompletedProcess((), 0, stdout=b""),
            CompletedProcess(
                (),
                0,
                stdout=BOOTPARAMS_OUTPUT.format(bootparams="0004000000", override="Force PXE").encode(),
            ),
        ]
        self.ipmi.force_pxe()

        assert not mocked_sleep.called
        mocked_run.assert_has_calls(
            [
                mock.call(
                    IPMITOOL_BASE + ["chassis", "bootparam", "set", "bootflag", "force_pxe", "options=reset"],
                    env=ENV,
                    stdout=PIPE,
                    check=True,
                ),
                mock.call(
                    IPMITOOL_BASE + ["chassis", "bootparam", "get", "5"],
                    env=ENV,
                    stdout=PIPE,
                    check=True,
                ),
            ]
        )

    @mock.patch("wmflib.decorators.time.sleep", return_value=None)
    @mock.patch("spicerack.ipmi.run")
    def test_force_pxe_retried(self, mocked_run, mocked_sleep):
        """Should retry to set the PXE mode on failure."""
        mocked_run.side_effect = [
            CompletedProcess((), 0, stdout=b"PXE not set"),
            CompletedProcess(
                (),
                0,
                stdout=BOOTPARAMS_OUTPUT.format(bootparams="0000000000", override="No override").encode(),
            ),
            CompletedProcess((), 0, stdout=b"PXE set"),
            CompletedProcess(
                (),
                0,
                stdout=BOOTPARAMS_OUTPUT.format(bootparams="0004000000", override="Force PXE").encode(),
            ),
        ]
        self.ipmi.force_pxe()
        assert mocked_sleep.called

    @mock.patch("wmflib.decorators.time.sleep", return_value=None)
    @mock.patch("spicerack.ipmi.run")
    def test_force_pxe_dry_run(self, mocked_run, mocked_sleep):
        """Should not raise an exception on dry-run mode when unable to verify the boot parameters."""
        mocked_run.side_effect = [
            CompletedProcess(
                (),
                0,
                stdout=BOOTPARAMS_OUTPUT.format(bootparams="0000000000", override="No override").encode(),
            ),
        ]
        self.ipmi_dry_run.force_pxe()  # should not raise
        assert not mocked_sleep.called

    @mock.patch("spicerack.ipmi.run")
    def test_remove_boot_override_ok(self, mocked_run):
        """Should unset any boot override for the next boot."""
        mocked_run.side_effect = [
            CompletedProcess((), 0, stdout=b""),
            CompletedProcess(
                (),
                0,
                stdout=BOOTPARAMS_OUTPUT.format(bootparams="8000000000", override="No override").encode(),
            ),
        ]
        self.ipmi.remove_boot_override()

        mocked_run.assert_has_calls(
            [
                mock.call(
                    IPMITOOL_BASE + ["chassis", "bootparam", "set", "bootflag", "none", "options=reset"],
                    env=ENV,
                    stdout=PIPE,
                    check=True,
                ),
                mock.call(
                    IPMITOOL_BASE + ["chassis", "bootparam", "get", "5"],
                    env=ENV,
                    stdout=PIPE,
                    check=True,
                ),
            ]
        )

    @mock.patch("spicerack.ipmi.run")
    def test_remove_boot_override_fail(self, mocked_run):
        """Should raise an IpmiCheckError exception on failure."""
        mocked_run.side_effect = [
            CompletedProcess((), 0, stdout=b"PXE not set"),
            CompletedProcess(
                (),
                0,
                stdout=BOOTPARAMS_OUTPUT.format(bootparams="000400000", override="Force PXE").encode(),
            ),
        ]
        with pytest.raises(ipmi.IpmiCheckError, match="Unable to verify that the boot override was removed."):
            self.ipmi.remove_boot_override()

    @mock.patch("spicerack.ipmi.run")
    def test_remove_boot_override_dry_run(self, mocked_run):
        """Should not raise an exception on dry-run mode when unable to verify the boot parameters."""
        mocked_run.side_effect = [
            CompletedProcess(
                (),
                0,
                stdout=BOOTPARAMS_OUTPUT.format(bootparams="0004000000", override="Force PXE").encode(),
            ),
        ]
        self.ipmi_dry_run.remove_boot_override()  # should not raise

    @mock.patch("spicerack.ipmi.run")
    def test_reset_password_16(self, mocked_run):
        """It should reset the users password and store the password as 16 bytes."""
        mocked_run.side_effect = [
            CompletedProcess((), 0, stdout=USERLIST_OUTPUT.encode()),
            CompletedProcess((), 0, stdout=b"Set User Password command successful (user 2)\n"),
            CompletedProcess((), 0, stdout=b"Chassis Power is on"),
        ]
        self.ipmi.reset_password("root", "a" * 16)
        mocked_run.assert_has_calls(
            [
                mock.call(
                    IPMITOOL_BASE + ["user", "list", "1"],
                    env=ENV,
                    stdout=PIPE,
                    check=True,
                ),
                mock.call(
                    IPMITOOL_BASE + ["user", "set", "password", "2", "a" * 16, "16"],
                    env=ENV,
                    stdout=PIPE,
                    check=True,
                ),
                mock.call(
                    IPMITOOL_BASE + ["chassis", "power", "status"],
                    env={"IPMITOOL_PASSWORD": "a" * 16},
                    stdout=PIPE,
                    check=True,
                ),
            ]
        )
        assert self.ipmi.env["IPMITOOL_PASSWORD"] == "a" * 16

    @mock.patch("spicerack.ipmi.run")
    def test_reset_password_20(self, mocked_run):
        """It should reset the users password and store the password as 20 bytes."""
        mocked_run.side_effect = [
            CompletedProcess((), 0, stdout=USERLIST_OUTPUT.encode()),
            CompletedProcess((), 0, stdout=b"Set User Password command successful (user 2)\n"),
            CompletedProcess((), 0, stdout=b"Chassis Power is on"),
        ]
        self.ipmi.reset_password("root", "a" * 17)
        mocked_run.assert_has_calls(
            [
                mock.call(
                    IPMITOOL_BASE + ["user", "list", "1"],
                    env=ENV,
                    stdout=PIPE,
                    check=True,
                ),
                mock.call(
                    IPMITOOL_BASE + ["user", "set", "password", "2", "a" * 17, "20"],
                    env=ENV,
                    stdout=PIPE,
                    check=True,
                ),
                mock.call(
                    IPMITOOL_BASE + ["chassis", "power", "status"],
                    env={"IPMITOOL_PASSWORD": "a" * 17},
                    stdout=PIPE,
                    check=True,
                ),
            ]
        )
        assert self.ipmi.env["IPMITOOL_PASSWORD"] == "a" * 17

    @mock.patch("spicerack.ipmi.run")
    def test_reset_password_not_root(self, mocked_run):
        """It should reset the users password."""
        mocked_run.side_effect = [
            CompletedProcess((), 0, stdout=USERLIST_OUTPUT.encode()),
            CompletedProcess((), 0, stdout=b"Set User Password command successful (user 9)\n"),
        ]
        self.ipmi.reset_password("user_number_9", "a" * 16)
        mocked_run.assert_has_calls(
            [
                mock.call(
                    IPMITOOL_BASE + ["user", "list", "1"],
                    env=ENV,
                    stdout=PIPE,
                    check=True,
                ),
                mock.call(
                    IPMITOOL_BASE + ["user", "set", "password", "9", "a" * 16, "16"],
                    env=ENV,
                    stdout=PIPE,
                    check=True,
                ),
            ]
        )

    @mock.patch("spicerack.ipmi.run")
    def test_reset_password_dryrun(self, mocked_run):
        """It should not reset the users password."""
        mocked_run.return_value = CompletedProcess((), 0, stdout=USERLIST_OUTPUT.encode())
        self.ipmi_dry_run.reset_password("root", "a" * 16)
        mocked_run.called_once_with(IPMITOOL_BASE + ["user", "list", "1"], env=ENV, stdout=PIPE, check=True)

    @mock.patch("spicerack.ipmi.run")
    def test_reset_password_fail_command(self, mocked_run):
        """It should fail the password reset command."""
        mocked_run.side_effect = [
            CompletedProcess((), 0, stdout=USERLIST_OUTPUT.encode()),
            CompletedProcess((), 0, stdout=b"Fail password reset\n"),
        ]
        with pytest.raises(ipmi.IpmiError, match="Password reset failed for username: user_number_9"):
            self.ipmi.reset_password("user_number_9", "a" * 16)
        mocked_run.assert_has_calls(
            [
                mock.call(
                    IPMITOOL_BASE + ["user", "list", "1"],
                    env=ENV,
                    stdout=PIPE,
                    check=True,
                ),
                mock.call(
                    IPMITOOL_BASE + ["user", "set", "password", "9", "a" * 16, "16"],
                    env=ENV,
                    stdout=PIPE,
                    check=True,
                ),
            ]
        )
        assert self.ipmi.env["IPMITOOL_PASSWORD"] == "password"

    @mock.patch("spicerack.ipmi.run")
    def test_reset_password_connection_test(self, mocked_run):
        """It should fail the check connection command."""
        mocked_run.side_effect = [
            CompletedProcess((), 0, stdout=USERLIST_OUTPUT.encode()),
            CompletedProcess((), 0, stdout=b"Set User Password command successful (user 2)\n"),
            CompletedProcess((), 0, stdout=b"Failed connection test"),
        ]
        with pytest.raises(ipmi.IpmiError, match="Password reset failed for username: root"):
            self.ipmi.reset_password("root", "a" * 16)
        mocked_run.assert_has_calls(
            [
                mock.call(
                    IPMITOOL_BASE + ["user", "list", "1"],
                    env=ENV,
                    stdout=PIPE,
                    check=True,
                ),
                mock.call(
                    IPMITOOL_BASE + ["user", "set", "password", "2", "a" * 16, "16"],
                    env=ENV,
                    stdout=PIPE,
                    check=True,
                ),
                mock.call(
                    IPMITOOL_BASE + ["chassis", "power", "status"],
                    env={"IPMITOOL_PASSWORD": "a" * 16},
                    stdout=PIPE,
                    check=True,
                ),
            ]
        )
        assert self.ipmi.env["IPMITOOL_PASSWORD"] == "password"

    @mock.patch("spicerack.ipmi.run")
    def test_reset_nonexistent_username(self, mocked_run):
        """It should raise IpmiError as the username will not be found."""
        with pytest.raises(ipmi.IpmiError, match="Unable to find ID for username: nonexistent"):
            self.ipmi.reset_password("nonexistent", "a" * 16)
        mocked_run.assert_has_calls(
            [
                mock.call(
                    IPMITOOL_BASE + ["user", "list", "1"],
                    env=ENV,
                    stdout=PIPE,
                    check=True,
                ),
                mock.call(
                    IPMITOOL_BASE + ["user", "list", "2"],
                    env=ENV,
                    stdout=PIPE,
                    check=True,
                ),
            ],
            any_order=True,
        )

    def test_reset_password_bad_username(self):
        """It should raise IpmiError is username is empty."""
        with pytest.raises(ipmi.IpmiError, match="Username can not be an empty string"):
            self.ipmi.reset_password("", "a" * 16)

    def test_reset_password_short_password(self):
        """It should raise IpmiError as password is less then 16 bytes."""
        with pytest.raises(ipmi.IpmiError, match="New passwords must be 16 bytes minimum"):
            self.ipmi.reset_password("root", "a" * 15)

    def test_reset_password_long_password(self):
        """It should raise IpmiError as password is larger then 20 bytes."""
        with pytest.raises(ipmi.IpmiError, match="New passwords is greater then the 20 byte limit"):
            self.ipmi.reset_password("root", "a" * 21)
