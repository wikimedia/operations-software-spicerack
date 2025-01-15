"""Puppet module tests."""

from unittest import mock

import pytest

from spicerack import apt
from spicerack.remote import RemoteHosts

APT_GET_BASE_COMMAND = (
    'DEBIAN_FRONTEND=noninteractive /usr/bin/apt-get --quiet --yes --option Dpkg::Options::="--force-confdef" '
    '--option Dpkg::Options::="--force-confold"'
)


class TestAptGetHosts:
    """Test class for the AptGetHosts class."""

    def setup_method(self):
        """Setup the test environment."""
        # pylint: disable=attribute-defined-outside-init
        self.mocked_remote_hosts = mock.MagicMock(spec_set=RemoteHosts)
        self.mocked_remote_hosts.__len__.return_value = 1
        self.apt_get_hosts = apt.AptGetHosts(self.mocked_remote_hosts)

    @pytest.mark.parametrize(
        "kwargs",
        (
            {},
            {"batch_size": 3},
        ),
    )
    def test_update(self, kwargs):
        """It should run apt-get update on the hosts with the given parameters."""
        self.apt_get_hosts.update(**kwargs)
        self.mocked_remote_hosts.run_sync.assert_has_calls([mock.call(f"{APT_GET_BASE_COMMAND} update", **kwargs)])

    @pytest.mark.parametrize(
        "packages, kwargs",
        (
            (["package1"], {}),
            (["package1", "package2"], {}),
            (["package1"], {"batch_size": 3}),
        ),
    )
    def test_install(self, packages, kwargs):
        """It should run apt-get install on the hosts for the given packages."""
        self.apt_get_hosts.install(*packages, **kwargs)
        pkgs = " ".join(packages)
        self.mocked_remote_hosts.run_sync.assert_has_calls(
            [mock.call(f"{APT_GET_BASE_COMMAND} install {pkgs}", **kwargs)]
        )

    def test_install_no_packages(self):
        """It should raise an AptGetError if there were no packages provided."""
        with pytest.raises(apt.AptGetError, match=r"No packages to install were provided\."):
            self.apt_get_hosts.install()
