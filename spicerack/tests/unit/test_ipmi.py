"""IPMI module tests."""
import os

from subprocess import CalledProcessError  # nosec
from unittest import mock

import pytest

from spicerack import ipmi


BOOTPARAMS_OUTPUT = """
Boot parameter version: 1
Boot parameter 5 is valid/unlocked
Boot parameter data: {bootparams}
 Boot Flags :
   - Boot Flag Invalid
   - Options apply to only next boot
   - BIOS PC Compatible (legacy) boot
   - Boot Device Selector : {pxe}
   - Console Redirection control : System Default
   - BIOS verbosity : Console redirection occurs per BIOS configuration setting (default)
   - BIOS Mux Control Override : BIOS uses recommended setting of the mux at the end of POST
Invalid line
"""


class TestIpmi:
    """Test class for the Ipmi class."""

    def setup_method(self):
        """Setup the test environment."""
        # pylint: disable=attribute-defined-outside-init
        self.ipmi = ipmi.Ipmi('password', dry_run=False)
        self.ipmi_dry_run = ipmi.Ipmi('password')

    def test_init(self):
        """It should initialize the instance and set the IPMITOOL_PASSWORD environment variable."""
        assert isinstance(self.ipmi, ipmi.Ipmi)
        assert os.getenv('IPMITOOL_PASSWORD') == 'password'

    @mock.patch('spicerack.ipmi.check_output', return_value=b'test')
    def test_command_ok(self, mocked_check_output):
        """It should execute the IPMI command as expected."""
        assert self.ipmi.command('test-mgmt.example.com', ['test_command']) == 'test'
        mocked_check_output.assert_called_once_with(
            ['ipmitool', '-I', 'lanplus', '-H', 'test-mgmt.example.com', '-U', 'root', '-E', 'test_command'])

    @mock.patch('spicerack.ipmi.check_output')
    def test_command_dry_run_ok(self, mocked_check_output):
        """It should not execute the IPMI command if in DRY RUN mode."""
        assert self.ipmi_dry_run.command('test-mgmt.example.com', ['test_command']) == ''
        assert not mocked_check_output.called

    @mock.patch('spicerack.ipmi.check_output')
    def test_command_raise(self, mocked_check_output):
        """It should raise IpmiError if failed to execute the command."""
        mocked_check_output.side_effect = CalledProcessError(1, 'executed_command')
        with pytest.raises(ipmi.IpmiError, match='Remote IPMI for test-mgmt.example.com failed'):
            self.ipmi.command('test-mgmt.example.com', ['test_command'])

    @mock.patch('spicerack.ipmi.check_output', return_value=b'Chassis Power is on')
    def test_check_connection_ok(self, mocked_check_output):
        """It should check that the connection to the remote IPMI works running a simple command."""
        self.ipmi_dry_run.check_connection('test-mgmt.example.com')
        mocked_check_output.assert_called_once_with(
            ['ipmitool', '-I', 'lanplus', '-H', 'test-mgmt.example.com', '-U', 'root', '-E',
             'chassis', 'power', 'status'])

    @mock.patch('spicerack.ipmi.check_output', return_value=b'failed')
    def test_check_connection_raise(self, mocked_check_output):
        """It should raise IpmiError if unable to execute remote IPMI commands."""
        with pytest.raises(ipmi.IpmiError, match='Unexpected chassis status: failed'):
            self.ipmi.check_connection('test-mgmt.example.com')

        assert mocked_check_output.called

    @mock.patch('spicerack.ipmi.check_output')
    def test_check_bootparams_ok(self, mocked_check_output):
        """It should check that the BIOS boot parameters are normal."""
        mocked_check_output.return_value = BOOTPARAMS_OUTPUT.format(bootparams='0000000000', pxe='No override').encode()
        self.ipmi.check_bootparams('test-mgmt.example.com')
        mocked_check_output.assert_called_once_with(
            ['ipmitool', '-I', 'lanplus', '-H', 'test-mgmt.example.com', '-U', 'root', '-E',
             'chassis', 'bootparam', 'get', '5'])

    @mock.patch('spicerack.ipmi.check_output')
    def test_check_bootparams_wrong_value(self, mocked_check_output):
        """It should raise IpmiCheckError if the BIOS boot parameters are not the normal ones."""
        mocked_check_output.return_value = BOOTPARAMS_OUTPUT.format(bootparams='0004000000', pxe='Force PXE').encode()
        with pytest.raises(ipmi.IpmiCheckError,
                           match=r"Expected BIOS boot params in \('0000000000', '8000020000'\) got: 0004000000"):
            self.ipmi_dry_run.check_bootparams('test-mgmt.example.com')

        assert mocked_check_output.called

    @mock.patch('spicerack.ipmi.check_output', return_value=b'Boot parameter data')
    def test_check_bootparams_unable_to_extract(self, mocked_check_output):
        """It should raise IpmiError if unable to extract the value of the BIOS boot parameters."""
        with pytest.raises(ipmi.IpmiError, match="Unable to extract value for parameter 'Boot parameter data'"):
            self.ipmi.check_bootparams('test-mgmt.example.com')

        assert mocked_check_output.called

    @mock.patch('spicerack.ipmi.check_output', return_value=b'Invalid')
    def test_check_bootparams_missing_label(self, mocked_check_output):
        """It should raise IpmiError if unable to find the label looked for."""
        with pytest.raises(ipmi.IpmiError, match="Unable to find the boot parameter 'Boot parameter data'"):
            self.ipmi.check_bootparams('test-mgmt.example.com')

        assert mocked_check_output.called

    @mock.patch('spicerack.decorators.time.sleep', return_value=None)
    @mock.patch('spicerack.ipmi.check_output')
    def test_force_pxe_ok(self, mocked_check_output, mocked_sleep):
        """Should set the PXE boot mode for the next boot."""
        mocked_check_output.side_effect = [
            b'', BOOTPARAMS_OUTPUT.format(bootparams='0004000000', pxe='Force PXE').encode()]
        self.ipmi.force_pxe('test-mgmt.example.com')

        assert not mocked_sleep.called
        mocked_check_output.assert_has_calls([
            mock.call(['ipmitool', '-I', 'lanplus', '-H', 'test-mgmt.example.com', '-U', 'root', '-E',
                       'chassis', 'bootdev', 'pxe']),
            mock.call(['ipmitool', '-I', 'lanplus', '-H', 'test-mgmt.example.com', '-U', 'root', '-E',
                       'chassis', 'bootparam', 'get', '5'])])

    @mock.patch('spicerack.decorators.time.sleep', return_value=None)
    @mock.patch('spicerack.ipmi.check_output')
    def test_force_pxe_retried(self, mocked_check_output, mocked_sleep):
        """Should retry to set the PXE mode on failure."""
        mocked_check_output.side_effect = [
            b'PXE not set',
            BOOTPARAMS_OUTPUT.format(bootparams='0000000000', pxe='No override').encode(),
            b'PXE set',
            BOOTPARAMS_OUTPUT.format(bootparams='0004000000', pxe='Force PXE').encode()]
        self.ipmi.force_pxe('test-mgmt.example.com')
        assert mocked_sleep.called
