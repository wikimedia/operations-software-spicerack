"""DHCP Module Tests."""

import base64
import re
from hashlib import sha256
from ipaddress import IPv4Address
from unittest import mock

import pytest

from spicerack import dhcp
from spicerack.locking import NoLock
from spicerack.remote import RemoteExecutionError


def get_mock_hosts():
    """Return a `spicerack.remote.Hosts` mock."""
    hosts = mock.MagicMock()
    hosts.__len__.return_value = 1
    hosts.run_sync.return_value = "some value"
    return hosts


def get_mock_fail_hosts():
    """Return a `spicerack.remote.Hosts` mock where execution fails."""
    hosts = get_mock_hosts()
    hosts.run_sync.side_effect = RemoteExecutionError("mock error", 1, iter(()))
    return hosts


def get_mock_suc_fail_hosts():
    """Return a `spicerack.remote.Hosts` mock where execution succeeds and then fails."""
    hosts = get_mock_hosts()
    hosts.run_sync.side_effect = [iter(()), RemoteExecutionError("mock error", 1, iter(()))]
    return hosts


def get_mock_config():
    """Return a `spicerack.dhcp.Configuration` mock."""
    config = mock.MagicMock()
    config.__str__.return_value = "test configuration"
    config.config_base64 = base64.b64encode(b"test configuration").decode()
    config.filename = "test.conf"
    return config


# Test Configuration Generator Objects
configuration_generator_data = (
    # dhcpconfopt82 tests
    # - basic check of functionality
    (
        dhcp.DHCPConfOpt82,
        {
            "hostname": "testhost0",
            "ipv4": IPv4Address("10.0.0.1"),
            "switch_hostname": "asw2-d-eqiad",
            "switch_iface": "ge-0/0/0",
            "vlan": 1021,
            "ttys": 1,
            "distro": "buster",
        },
        (
            "\nhost testhost0 {\n"
            '    host-identifier option agent.circuit-id "asw2-d-eqiad:ge-0/0/0:1021";\n'
            "    fixed-address 10.0.0.1;\n"
            '    option pxelinux.pathprefix "http://apt.wikimedia.org/tftpboot/buster-installer/";\n'
            "}\n"
        ),
        "ttyS1-115200/testhost0.conf",
    ),
    # - update media type
    (
        dhcp.DHCPConfOpt82,
        {
            "hostname": "testhost0",
            "ipv4": IPv4Address("10.0.0.1"),
            "switch_hostname": "asw2-d-eqiad",
            "switch_iface": "ge-0/0/0",
            "vlan": 1021,
            "ttys": 1,
            "distro": "buster",
            "media_type": "rescue",
        },
        (
            "\nhost testhost0 {\n"
            '    host-identifier option agent.circuit-id "asw2-d-eqiad:ge-0/0/0:1021";\n'
            "    fixed-address 10.0.0.1;\n"
            '    option pxelinux.pathprefix "http://apt.wikimedia.org/tftpboot/buster-rescue/";\n'
            "}\n"
        ),
        "ttyS1-115200/testhost0.conf",
    ),
    # - tty argument should change the file path
    (
        dhcp.DHCPConfOpt82,
        {
            "hostname": "testhost0",
            "ipv4": IPv4Address("10.0.0.1"),
            "switch_hostname": "asw2-d-eqiad",
            "switch_iface": "ge-0/0/0",
            "vlan": 1021,
            "ttys": 0,
            "distro": "buster",
        },
        (
            "\nhost testhost0 {\n"
            '    host-identifier option agent.circuit-id "asw2-d-eqiad:ge-0/0/0:1021";\n'
            "    fixed-address 10.0.0.1;\n"
            '    option pxelinux.pathprefix "http://apt.wikimedia.org/tftpboot/buster-installer/";\n'
            "}\n"
        ),
        "ttyS0-115200/testhost0.conf",
    ),
    # - dhcp_filename and dhcp_options arguments should be rendered.
    (
        dhcp.DHCPConfOpt82,
        {
            "hostname": "testhost0",
            "ipv4": IPv4Address("10.0.0.1"),
            "switch_hostname": "asw2-d-eqiad",
            "switch_iface": "ge-0/0/0",
            "vlan": 1021,
            "ttys": 0,
            "distro": "buster",
            "dhcp_filename": "pxelinux",
            "dhcp_options": {
                "pxelinux.pathprefix": "/srv/tftpboot/buster-installer/",
                "pxelinux.test2": "someoption",
            },
        },
        (
            "\nhost testhost0 {\n"
            '    host-identifier option agent.circuit-id "asw2-d-eqiad:ge-0/0/0:1021";\n'
            "    fixed-address 10.0.0.1;\n"
            '    filename "pxelinux";\n'
            '    option pxelinux.pathprefix "/srv/tftpboot/buster-installer/";\n'
            '    option pxelinux.test2 "someoption";\n'
            "}\n"
        ),
        "ttyS0-115200/testhost0.conf",
    ),
    # - If distro is empty the default pathprefix config is not rendered.
    (
        dhcp.DHCPConfOpt82,
        {
            "hostname": "testhost0",
            "ipv4": IPv4Address("10.0.0.1"),
            "switch_hostname": "asw2-d-eqiad",
            "switch_iface": "ge-0/0/0",
            "vlan": 1021,
            "ttys": 0,
            "distro": "",
            "dhcp_filename": "pxelinux",
        },
        (
            "\nhost testhost0 {\n"
            '    host-identifier option agent.circuit-id "asw2-d-eqiad:ge-0/0/0:1021";\n'
            "    fixed-address 10.0.0.1;\n"
            '    filename "pxelinux";\n'
            "}\n"
        ),
        "ttyS0-115200/testhost0.conf",
    ),
    # - If distro is None the default pathprefix config is not rendered.
    (
        dhcp.DHCPConfOpt82,
        {
            "hostname": "testhost0",
            "ipv4": IPv4Address("10.0.0.1"),
            "switch_hostname": "asw2-d-eqiad",
            "switch_iface": "ge-0/0/0",
            "vlan": 1021,
            "ttys": 0,
            "distro": None,
            "dhcp_filename": "pxelinux",
        },
        (
            "\nhost testhost0 {\n"
            '    host-identifier option agent.circuit-id "asw2-d-eqiad:ge-0/0/0:1021";\n'
            "    fixed-address 10.0.0.1;\n"
            '    filename "pxelinux";\n'
            "}\n"
        ),
        "ttyS0-115200/testhost0.conf",
    ),
    # - If dhcp_filename_exclude_vendor is set, vendor should be excluded, Opt82
    (
        dhcp.DHCPConfOpt82,
        {
            "hostname": "testhost0",
            "ipv4": IPv4Address("10.0.0.1"),
            "switch_hostname": "asw2-d-eqiad",
            "switch_iface": "ge-0/0/0",
            "vlan": 1021,
            "ttys": 0,
            "distro": None,
            "dhcp_filename": "http://snponly.efi",
            "dhcp_filename_exclude_vendor": "d-i",
        },
        (
            "\nhost testhost0 {\n"
            '    host-identifier option agent.circuit-id "asw2-d-eqiad:ge-0/0/0:1021";\n'
            "    fixed-address 10.0.0.1;\n"
            '    if option vendor-class-identifier = "d-i" {\n'
            '        filename "";\n'
            "    } else {\n"
            '        filename "http://snponly.efi";\n'
            "    }\n"
            "}\n"
        ),
        "ttyS0-115200/testhost0.conf",
    ),
    # - If dhcp_filename_exclude_vendor is set, vendor should be excluded, Mac
    (
        dhcp.DHCPConfMac,
        {
            "hostname": "testhost0",
            "ipv4": IPv4Address("10.0.0.1"),
            "mac": "00:00:00:00:00:01",
            "ttys": 0,
            "distro": None,
            "dhcp_filename": "http://snponly.efi",
            "dhcp_filename_exclude_vendor": "d-i",
        },
        (
            "\nhost testhost0 {\n"
            "    hardware ethernet 00:00:00:00:00:01;\n"
            "    fixed-address 10.0.0.1;\n"
            '    if option vendor-class-identifier = "d-i" {\n'
            '        filename "";\n'
            "    } else {\n"
            '        filename "http://snponly.efi";\n'
            "    }\n"
            "}\n"
        ),
        "ttyS0-115200/testhost0.conf",
    ),
    # DHCPConfMac tests
    # - basic check of functionality
    (
        dhcp.DHCPConfMac,
        {
            "hostname": "testhost0",
            "ipv4": IPv4Address("10.0.0.1"),
            "mac": "00:00:00:00:00:01",
            "ttys": 0,
            "distro": "buster",
        },
        (
            "\nhost testhost0 {\n"
            "    hardware ethernet 00:00:00:00:00:01;\n"
            "    fixed-address 10.0.0.1;\n"
            '    option pxelinux.pathprefix "http://apt.wikimedia.org/tftpboot/buster-installer/";\n'
            "}\n"
        ),
        "ttyS0-115200/testhost0.conf",
    ),
    # - update media type
    (
        dhcp.DHCPConfMac,
        {
            "hostname": "testhost0",
            "ipv4": IPv4Address("10.0.0.1"),
            "mac": "00:00:00:00:00:01",
            "ttys": 0,
            "distro": "buster",
            "media_type": "installer-11.0",
        },
        (
            "\nhost testhost0 {\n"
            "    hardware ethernet 00:00:00:00:00:01;\n"
            "    fixed-address 10.0.0.1;\n"
            '    option pxelinux.pathprefix "http://apt.wikimedia.org/tftpboot/buster-installer-11.0/";\n'
            "}\n"
        ),
        "ttyS0-115200/testhost0.conf",
    ),
    # - tty argument should change the file path
    (
        dhcp.DHCPConfMac,
        {
            "hostname": "testhost0",
            "ipv4": IPv4Address("10.0.0.1"),
            "mac": "00:00:00:00:00:01",
            "ttys": 1,
            "distro": "bullseye",
        },
        (
            "\nhost testhost0 {\n"
            "    hardware ethernet 00:00:00:00:00:01;\n"
            "    fixed-address 10.0.0.1;\n"
            '    option pxelinux.pathprefix "http://apt.wikimedia.org/tftpboot/bullseye-installer/";\n'
            "}\n"
        ),
        "ttyS1-115200/testhost0.conf",
    ),
    # - dhcp_filename and dhcp_options arguments should be rendered.
    (
        dhcp.DHCPConfMac,
        {
            "hostname": "testhost0",
            "ipv4": IPv4Address("10.0.0.1"),
            "mac": "00:00:00:00:00:01",
            "ttys": 1,
            "distro": "bullseye",
            "dhcp_filename": "pxelinux",
            "dhcp_options": {
                "pxelinux.pathprefix": "/srv/tftpboot/buster-installer/",
                "pxelinux.test2": "someoption",
            },
        },
        (
            "\nhost testhost0 {\n"
            "    hardware ethernet 00:00:00:00:00:01;\n"
            "    fixed-address 10.0.0.1;\n"
            '    filename "pxelinux";\n'
            '    option pxelinux.pathprefix "/srv/tftpboot/buster-installer/";\n'
            '    option pxelinux.test2 "someoption";\n'
            "}\n"
        ),
        "ttyS1-115200/testhost0.conf",
    ),
    # - If distro is empty string, the default pathprefix option is not rendered.
    (
        dhcp.DHCPConfMac,
        {
            "hostname": "testhost0",
            "ipv4": IPv4Address("10.0.0.1"),
            "mac": "00:00:00:00:00:01",
            "ttys": 1,
            "distro": "",
            "dhcp_filename": "pxelinux",
        },
        (
            "\nhost testhost0 {\n"
            "    hardware ethernet 00:00:00:00:00:01;\n"
            "    fixed-address 10.0.0.1;\n"
            '    filename "pxelinux";\n'
            "}\n"
        ),
        "ttyS1-115200/testhost0.conf",
    ),
    # - If distro is None string, the default pathprefix option is not rendered.
    (
        dhcp.DHCPConfMac,
        {
            "hostname": "testhost0",
            "ipv4": IPv4Address("10.0.0.1"),
            "mac": "00:00:00:00:00:01",
            "ttys": 1,
            "distro": None,
            "dhcp_filename": "pxelinux",
        },
        (
            "\nhost testhost0 {\n"
            "    hardware ethernet 00:00:00:00:00:01;\n"
            "    fixed-address 10.0.0.1;\n"
            '    filename "pxelinux";\n'
            "}\n"
        ),
        "ttyS1-115200/testhost0.conf",
    ),
    # DHCPConfUUID tests
    # - basic check of functionality
    (
        dhcp.DHCPConfUUID,
        {
            "hostname": "testhost0",
            "ipv4": IPv4Address("10.0.0.1"),
            "uuid": "4c4c4544-0059-4b10-804e-b4c04f4d5733",
            "ttys": 0,
            "distro": "buster",
        },
        (
            "\nhost testhost0 {\n"
            "    host-identifier option pxe-client-id 00:44:45:4c:4c:59:00:10:4b:80:4e:b4:c0:4f:4d:57:33;\n"
            "    fixed-address 10.0.0.1;\n"
            '    option pxelinux.pathprefix "http://apt.wikimedia.org/tftpboot/buster-installer/";\n'
            "}\n"
        ),
        "ttyS0-115200/testhost0.conf",
    ),
    # dhcpconfmgmt tests
    (  # Dell host
        dhcp.DHCPConfMgmt,
        {
            "datacenter": "eqiad",
            "serial": "TEST",
            "manufacturer": "Dell",
            "fqdn": "test1001.mgmt.eqiad.wmnet",
            "ipv4": IPv4Address("10.0.0.1"),
        },
        (
            '\nclass "test1001.mgmt.eqiad.wmnet" {\n'
            '    match if (lcase(option host-name) = "idrac-test");\n'
            "}\npool {\n"
            '    allow members of "test1001.mgmt.eqiad.wmnet";\n'
            "    range 10.0.0.1 10.0.0.1;\n"
            "}\n"
        ),
        "mgmt-eqiad/test1001.mgmt.eqiad.wmnet.conf",
    ),
    (  # Juniper device
        dhcp.DHCPConfMgmt,
        {
            "datacenter": "eqiad",
            "serial": "TESTSERIAL",
            "manufacturer": "Juniper",
            "fqdn": "test-switch1001.mgmt.eqiad.wmnet",
            "ipv4": IPv4Address("10.0.0.1"),
        },
        (
            '\nclass "test-switch1001.mgmt.eqiad.wmnet" {\n'
            '    match if (lcase(option host-name) = "testserial");\n'
            "}\npool {\n"
            '    allow members of "test-switch1001.mgmt.eqiad.wmnet";\n'
            "    range 10.0.0.1 10.0.0.1;\n"
            "}\n"
        ),
        "mgmt-eqiad/test-switch1001.mgmt.eqiad.wmnet.conf",
    ),
)
"""`tuple[class, tuple[dict[str, str], str]]`: Parameters for test_configuration_generator."""


@pytest.mark.parametrize("generator,kw_arguments,expected,expected_filename", configuration_generator_data)
def test_configuration_generator(generator, kw_arguments, expected, expected_filename):
    """Test configuration generators producing expected outputs with various parameters."""
    confobj = generator(**kw_arguments)
    assert str(confobj) == expected
    assert confobj.filename == expected_filename


@pytest.mark.parametrize(
    "mac",
    (
        "00:00:00:00:00:00",
        "01:23:45:67:89:ab",
        "cd:ef:00:11:22:33",
        "aa:aa:aa:aa:aa:aa",
        "AA:AA:AA:AA:AA:AA",
        "ff:ff:ff:ff:ff:ff",
    ),
)
def test_dhcp_conf_mac_valid_mac(mac):
    """It should not raise when a valid MAC address is passed."""
    config = dhcp.DHCPConfMac(hostname="testhost0", ipv4=IPv4Address("10.0.0.1"), mac=mac, ttys=1, distro="bullseye")
    assert config.mac == mac


@pytest.mark.parametrize(
    "mac",
    (
        ":00:00:00:00:00:00",
        "00:00:00:00:00:00:",
        ":00:00:00:00:00:00:",
        "0:00:00:00:00:00",
        "00:00:00:00:00:0",
        "000:00:00:00:00:00",
        "00:00:00:00:00:000",
        "00:00:000:00:00:00",
        "g0:00:00:00:00:00",
        "00-00-00-00-00-00",
        "01-23-45-67-89-AB",
        "0123.4567.89AB",
        "01-23-45-67-89-AB-CD-EF",
    ),
)
def test_dhcp_conf_mac_invalid_mac(mac):
    """It should raise DHCPError if an invalid MAC address is passed."""
    with pytest.raises(dhcp.DHCPError, match="Invalid MAC address"):
        dhcp.DHCPConfMac(hostname="testhost0", ipv4=IPv4Address("10.0.0.1"), mac=mac, ttys=1, distro="bullseye")


@pytest.mark.parametrize(
    "datacenter, fqdn, error",
    (
        ("invalid", "", "Invalid datacenter invalid, must be one of"),
        ("eqiad", "invalid.eqiad.wmnet", "Invalid management FQDN invalid.eqiad.wmnet, must match"),
    ),
)
def test_dhcp_mgmt_fail(datacenter, fqdn, error):
    """A DHCPConfMgmt object should fail to create if invalid parameters are passed to its init."""
    with pytest.raises(dhcp.DHCPError, match=re.escape(error)):
        dhcp.DHCPConfMgmt(datacenter=datacenter, serial="", manufacturer="", fqdn=fqdn, ipv4=None)


def test_create_dhcp_no_hosts():
    """Test fail (hosts parameter has no hosts) DHCP instance creation."""
    hosts_mock = get_mock_hosts()
    hosts_mock.__len__.return_value = 0
    with pytest.raises(dhcp.DHCPError, match="No target hosts provided"):
        dhcp.DHCP(hosts_mock, datacenter="eqiad", lock=NoLock())


def test_create_dhcp_wrong_dc():
    """It should raise a DHCPError in case the datacenter is inexistent."""
    hosts_mock = get_mock_hosts()
    hosts_mock.__len__.return_value = 2
    with pytest.raises(dhcp.DHCPError, match="Invalid datacenter invalid, must be one of"):
        dhcp.DHCP(hosts_mock, datacenter="invalid", lock=NoLock())


class TestDHCP:
    """Test various other aspects of DHCP module."""

    def setup_method(self):
        """Do any one time setup for the tests."""
        # pylint: disable=attribute-defined-outside-init
        remotehosts_mock = get_mock_hosts()
        self.dhcp = dhcp.DHCP(remotehosts_mock, datacenter="eqiad", lock=NoLock(), dry_run=False)

    def _setup_dhcp_mocks(self, hosts=None):
        """Setup the DHCP's hosts remote as new mocks."""
        if hosts is None:
            hosts = get_mock_hosts()

        self.dhcp._hosts = hosts  # pylint: disable=protected-access
        return hosts

    def test_push_configuration_ok(self):
        """Test push_configuration success."""
        config = get_mock_config()
        hosts = self._setup_dhcp_mocks()

        self.dhcp.push_configuration(config)
        hosts.run_sync.assert_has_calls(
            [
                mock.call(
                    "/bin/echo 'dGVzdCBjb25maWd1cmF0aW9u' | /usr/bin/base64 -d > /etc/dhcp/automation/test.conf",
                    print_progress_bars=False,
                ),
                mock.call("/usr/local/sbin/dhcpincludes -r commit", print_progress_bars=False),
            ]
        )

    def test_push_configuration_echo_fail(self):
        """Test push_configuration, where writing to the file fails."""
        config = get_mock_config()
        hosts = get_mock_suc_fail_hosts()
        hosts.run_sync.side_effect = list(hosts.run_sync.side_effect)[1:]
        self._setup_dhcp_mocks(hosts=hosts)

        with pytest.raises(dhcp.DHCPError, match="Failed to create snippet"):
            self.dhcp.push_configuration(config)

    def test_push_configuration_refresh_fail(self):
        """When the call to _refresh_dhcp() fails, it should remove the snippet and refresh again."""
        config = get_mock_config()
        hosts = get_mock_suc_fail_hosts()
        hosts.run_sync.side_effect = [
            "some value",
            RemoteExecutionError("mock error", 1, iter(())),
            "some value",
            "some value",
        ]
        self._setup_dhcp_mocks(hosts=hosts)

        with pytest.raises(dhcp.DHCPRestartError, match="Failed to refresh the DHCP server when running dhcpincludes"):
            self.dhcp.push_configuration(config)

        hosts.run_sync.assert_has_calls(
            [mock.call("/usr/local/sbin/dhcpincludes -r commit", print_progress_bars=False)]
        )

    def test_remove_config_ok(self):
        """Test remove_configuration where everything succeeds."""
        config = get_mock_config()
        hosts = self._setup_dhcp_mocks()
        with mock.patch("spicerack.dhcp.RemoteHosts") as mock_remotehosts:
            configsha256 = sha256(str(config).encode()).hexdigest()
            mock_remotehosts.results_to_list.return_value = [[None, f"{configsha256} {config.filename}"]]
            self.dhcp.remove_configuration(config)

        call_sha256 = mock.call(
            f"sha256sum {dhcp.DHCP_TARGET_PATH}/{config.filename}",
            is_safe=True,
            print_output=False,
            print_progress_bars=False,
        )
        call_rm = mock.call(
            f"/bin/rm -v {dhcp.DHCP_TARGET_PATH}/{config.filename}", print_output=False, print_progress_bars=False
        )
        call_refresh = mock.call("/usr/local/sbin/dhcpincludes -r commit", print_progress_bars=False)

        hosts.run_sync.assert_has_calls([call_sha256, call_rm, call_refresh])

    def test_remove_config_sha256_noresult(self):
        """Test remove_configuration where sha256sum returns nothing."""
        config = get_mock_config()
        self._setup_dhcp_mocks()
        with mock.patch("spicerack.dhcp.RemoteHosts") as mock_remotehosts:
            mock_remotehosts.results_to_list.return_value = []

            with pytest.raises(dhcp.DHCPError, match="No output when trying to checksum snippet"):
                self.dhcp.remove_configuration(config)

    def test_remove_config_sha256_fail(self):
        """Test remove_configuration where sha256sum fails to run."""
        config = get_mock_config()
        self._setup_dhcp_mocks(hosts=get_mock_fail_hosts())

        with pytest.raises(dhcp.DHCPError, match="Failed to checksum"):
            self.dhcp.remove_configuration(config)

    def test_remove_config_sha256_mismatch(self):
        """Test remove_configuration where sha256sum and the locally computed sum mismatch."""
        config = get_mock_config()
        self._setup_dhcp_mocks()
        configsha256 = sha256(str(config).encode()).hexdigest()
        config.__str__.return_value = "different test configuration"

        with mock.patch("spicerack.dhcp.RemoteHosts") as mock_remotehosts:
            mock_remotehosts.results_to_list.return_value = [[None, f"{configsha256} {config.filename}"]]
            with pytest.raises(dhcp.DHCPError, match="has a mismatched SHA256, refusing to remove it"):
                self.dhcp.remove_configuration(config)

    def test_remove_config_sha256_mismatch_force(self):
        """Test remove_configuration where there is a sha256 mismatch but we pass force=True."""
        config = get_mock_config()
        hosts = self._setup_dhcp_mocks()
        configsha256 = sha256(str(config).encode()).hexdigest()
        config.__str__.return_value = "different test configuration"

        with mock.patch("spicerack.dhcp.RemoteHosts") as mock_remotehosts:
            mock_remotehosts.results_to_list.return_value = [[None, f"{configsha256} {config.filename}"]]
            self.dhcp.remove_configuration(config, force=True)

        call_rm = mock.call(
            f"/bin/rm -v {dhcp.DHCP_TARGET_PATH}/{config.filename}", print_output=False, print_progress_bars=False
        )
        call_refresh = mock.call("/usr/local/sbin/dhcpincludes -r commit", print_progress_bars=False)

        hosts.run_sync.assert_has_calls([call_rm, call_refresh])

    def test_remove_config_rm_fail(self):
        """Test remove_configuration where rm fails."""
        config = get_mock_config()
        self._setup_dhcp_mocks(hosts=get_mock_suc_fail_hosts())

        with mock.patch("spicerack.dhcp.RemoteHosts") as mock_remotehosts:
            configsha256 = sha256(str(config).encode()).hexdigest()
            mock_remotehosts.results_to_list.return_value = [[None, f"{configsha256} {config.filename}"]]

            with pytest.raises(dhcp.DHCPError, match="Failed to remove snippet"):
                self.dhcp.remove_configuration(config)

    def test_push_context_manager(self):
        """Test push context manager success."""
        config = get_mock_config()
        hosts = self._setup_dhcp_mocks()
        call_sha256 = mock.call(
            f"sha256sum {dhcp.DHCP_TARGET_PATH}/{config.filename}",
            is_safe=True,
            print_output=False,
            print_progress_bars=False,
        )
        call_rm = mock.call(
            f"/bin/rm -v {dhcp.DHCP_TARGET_PATH}/{config.filename}", print_output=False, print_progress_bars=False
        )
        call_refresh = mock.call("/usr/local/sbin/dhcpincludes -r commit", print_progress_bars=False)

        with mock.patch("spicerack.dhcp.RemoteHosts") as mock_remotehosts:
            configsha256 = sha256(str(config).encode()).hexdigest()
            mock_remotehosts.results_to_list.return_value = [[None, f"{configsha256} {config.filename}"]]

            with self.dhcp.config(config):
                pass

        hosts.run_sync.assert_has_calls([call_sha256, call_rm, call_refresh])

    def test_push_context_manager_raise(self):
        """Test push context manager where internal code raises."""
        config = get_mock_config()
        hosts = self._setup_dhcp_mocks()

        call_write = mock.call(
            f"/bin/echo '{config.config_base64}' | /usr/bin/base64 -d > {dhcp.DHCP_TARGET_PATH}/{config.filename}",
            print_progress_bars=False,
        )
        call_sha256 = mock.call(
            f"sha256sum {dhcp.DHCP_TARGET_PATH}/{config.filename}",
            is_safe=True,
            print_output=False,
            print_progress_bars=False,
        )
        call_rm = mock.call(
            f"/bin/rm -v {dhcp.DHCP_TARGET_PATH}/{config.filename}", print_output=False, print_progress_bars=False
        )
        call_refresh = mock.call("/usr/local/sbin/dhcpincludes -r commit", print_progress_bars=False)

        with mock.patch("spicerack.dhcp.RemoteHosts") as mock_remotehosts:
            configsha256 = sha256(str(config).encode()).hexdigest()
            mock_remotehosts.results_to_list.return_value = [[None, f"{configsha256} {config.filename}"]]
            with pytest.raises(RuntimeError):
                with self.dhcp.config(config):
                    raise RuntimeError()

        hosts.run_sync.assert_has_calls([call_write, call_refresh, call_sha256, call_rm, call_refresh])
