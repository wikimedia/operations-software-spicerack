"""Hosts module."""

from typing import TYPE_CHECKING

from spicerack.exceptions import SpicerackError
from spicerack.mysql import MysqlRemoteHosts
from spicerack.netbox import NetboxHostNotFoundError
from spicerack.remote import RemoteHosts

if TYPE_CHECKING:  # Prevent circular dependency, is needed only for type hints
    import spicerack  # pragma: no cover | not imported at runtime


class HostError(SpicerackError):
    """Custom exception class for errors related to the Host instance."""


class Host:
    """A class to represent a host across various services.

    The class ensures that the host exists in our source of truth (Netbox) and exposes various services that will have
    the host as target for easy of use when managing a single host.
    """

    def __init__(
        self, name: str, spicerack_instance: "spicerack.Spicerack", *, netbox_read_write: bool = False
    ) -> None:
        """Initialize the instance.

        Arguments:
            name: the short hostname of the host.
            spicerack_instance: the spicerack instance.
            netbox_read_write: whether the Netbox related operation should be performed with a read-write token
                (:py:data:`True`) or a read-only one (:py:data:`False`).

        Raises:
            spicerack.netbox.NetboxError: if unable to find the host in Netbox or load its data.

        """
        self._spicerack = spicerack_instance
        self._remote = self._spicerack.remote()
        try:
            self._netbox_server = self._spicerack.netbox_server(name, read_write=netbox_read_write)
        except NetboxHostNotFoundError:
            raise HostError(f"Unable to find host {name} in Netbox") from None

    @classmethod
    def from_remote(cls, remote_hosts: RemoteHosts, spicerack_instance: "spicerack.Spicerack") -> "Host":
        """Initialize the Host instance from a RemoteHosts instance.

        Arguments:
            remote_hosts: the intance from where to create the host instance, must have only one host.
            spicerack_instance: the spicerack instance to pass to the Host constructor.

        Returns:
            the Host instance.

        Raises:
            spicerack.hosts.HostError: if the remote hosts doesn't have a single host.

        """
        if len(remote_hosts) != 1:
            raise HostError(
                f"Unable to create Host instance from RemoteHosts {remote_hosts}, "
                f"expected 1 host, got {len(remote_hosts)}."
            )

        return cls(str(remote_hosts).split(".", maxsplit=1)[0], spicerack_instance)

    @property
    def hostname(self) -> str:
        """The short hostname of the host.

        Examples:
            ::

                >>> host.hostname
                'example1001'

        Returns:
            the hostname as reported on Netbox.

        """
        return self._netbox_server.name

    @property
    def fqdn(self) -> str:
        """The fully qualified domain name (FQDN) of the host.

        Examples:
            ::

                >>> host.fqdn
                'example1001.eqiad.wmnet'

        Returns:
            the FQDN as defined in Netbox.

        """
        return self._netbox_server.fqdn

    @property
    def mgmt_fqdn(self) -> str:
        """The fully qualified domain name (FQDN) of the management interface of the host.

        Examples:
            ::

                >>> host.mgmt_fqdn
                'example1001.mgmt.eqiad.wmnet'


        Returns:
            the FQDN of the management interface as defined in Netbox.

        """
        return self._netbox_server.mgmt_fqdn

    def remote(self) -> "spicerack.RemoteHosts":
        """Get an instance to execute ssh commands on the host. It ensures that the host is present in PuppetDB.

        Examples:
            ::

                >>> host.remote.run_sync('command')

        Returns:
            the remote hosts instance.

        """
        return self._remote.query(self.fqdn)

    def netbox(self) -> "spicerack.NetboxServer":
        """Get an instance with all the Netbox data of the host.

        Examples:
            ::

                >>> host.netbox.status
                'active'

        Returns:
            the netbox server instance.

        """
        return self._netbox_server

    def puppet(self) -> "spicerack.PuppetHosts":
        """Get an instance to manage Puppet on the host.

        Examples:
            ::

                >>> host.puppet.run()

        Returns:
            the Puppet hosts instance.

        """
        return self._spicerack.puppet(self.remote())

    def mysql(self) -> MysqlRemoteHosts:
        """Get an instance to manage Mysql/Mariadb on the host.

        There is no check that the host has a Mysql/Mariadb server when calling this property.
        The Mysql/Mariadb specific features will fail if the host doesn't have a server installed/running.

        Examples:
            ::

                >>> host.mysql.run_query(query)

        Returns:
            the mysql remote hosts instance.

        """
        return MysqlRemoteHosts(self.remote())

    def apt_get(self) -> "spicerack.AptGetHosts":
        """Get an instance to manage Debian packages on the host via apt-get.

        Examples:
            ::

                >>> host.apt_get.update()

        Returns:
            the apt-get instance.

        """
        return self._spicerack.apt_get(self.remote())

    def alerting(self) -> "spicerack.AlertingHosts":
        """Get an instance to manage both Alertmanager and Icinga alerts for this host.

        Examples:
            ::

                >>> with host.alerting.downtimed(reason, duration=duration):
                ...     # do something

        Returns:
            the alerting hosts instance.

        """
        return self._spicerack.alerting_hosts([self.fqdn])

    def icinga(self) -> "spicerack.IcingaHosts":
        """Get an instance to manage Icinga alerts for this host.

        Examples:
            ::

                >>> with host.icinga.downtimed(reason, duration=duration):
                ...     # do something

        Returns:
            the Icinga hosts instance.

        """
        return self._spicerack.icinga_hosts([self.fqdn])

    def alertmanager(self) -> "spicerack.AlertmanagerHosts":
        """Get an instance to manage Alertmanager alerts for this host.

        Examples:
            ::

                >>> with host.alertmanager.downtimed(reason, duration=duration):
                ...     # do something

        Returns:
            the Alertmanager hosts instance.

        """
        return self._spicerack.alertmanager_hosts([self.fqdn])

    def redfish(self) -> "spicerack.Redfish":
        """Get an instance to manage the host using Redfish on the management interface of the host.

        Examples:
            ::

                >>> host.redfish.check_connection()

        Returns:
            the Redfish instance.

        Raises:
            spicerack.SpicerackError: if the host is a Virtual Machine or the manufacturer is not supported.

        """
        return self._spicerack.redfish(self.hostname)

    def ipmi(self) -> "spicerack.Ipmi":
        """Get an instance to manage the host using IPMI on the management interface of the host.

        See Also:
            https://wikitech.wikimedia.org/wiki/Management_Interfaces

        Examples:
            ::

                >>> host.ipmi.power_status()
                'on'

        Returns:
            the ipmi instance.

        Raises:
            spicerack.hosts.HostError: if the host is a Virtual Machine.

        """
        if self.netbox().virtual:
            raise HostError(f"Host '{self.hostname}' is a Virtual Machine, IPMI not supported.")

        return self._spicerack.ipmi(self.mgmt_fqdn)
