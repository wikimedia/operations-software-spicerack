"""Spicerack package."""
import os
from logging import Logger
from socket import gethostname
from typing import Dict, Optional, Sequence

from pkg_resources import DistributionNotFound, get_distribution
from wmflib import requests
from wmflib.actions import ActionsDict
from wmflib.config import load_ini_config, load_yaml_config
from wmflib.dns import Dns
from wmflib.interactive import get_username
from wmflib.phabricator import Phabricator, create_phabricator
from wmflib.prometheus import Prometheus

from spicerack._log import irc_logger
from spicerack.administrative import Reason
from spicerack.confctl import Confctl, ConftoolEntity
from spicerack.debmonitor import Debmonitor
from spicerack.dhcp import DHCP
from spicerack.dnsdisc import Discovery
from spicerack.elasticsearch_cluster import ElasticsearchClusters, create_elasticsearch_clusters
from spicerack.ganeti import Ganeti
from spicerack.icinga import ICINGA_DOMAIN, IcingaHosts
from spicerack.interactive import get_management_password
from spicerack.ipmi import Ipmi
from spicerack.management import Management
from spicerack.mediawiki import MediaWiki
from spicerack.mysql import Mysql
from spicerack.mysql_legacy import MysqlLegacy
from spicerack.netbox import NETBOX_DOMAIN, Netbox, NetboxServer
from spicerack.puppet import PuppetHosts, PuppetMaster, get_puppet_ca_hostname
from spicerack.redis_cluster import RedisCluster
from spicerack.remote import Remote, RemoteHosts
from spicerack.toolforge.etcdctl import EtcdctlController
from spicerack.typing import TypeHosts

try:
    __version__: str = get_distribution("wikimedia-spicerack").version  # Must be the same used as 'name' in setup.py
    """:py:class:`str`: the version of the current Spicerack module."""
except DistributionNotFound:  # pragma: no cover - this should never happen during tests
    pass  # package is not installed


class Spicerack:  # pylint: disable=too-many-instance-attributes
    """Spicerack service locator."""

    def __init__(
        self,
        *,
        verbose: bool = False,
        dry_run: bool = True,
        cumin_config: str = "/etc/cumin/config.yaml",
        cumin_installer_config: str = "/etc/cumin/config-installer.yaml",
        conftool_config: str = "/etc/conftool/config.yaml",
        conftool_schema: str = "/etc/conftool/schema.yaml",
        debmonitor_config: str = "/etc/debmonitor.conf",
        spicerack_config_dir: str = "/etc/spicerack",
        http_proxy: str = "",
    ) -> None:
        """Initialize the service locator for the Spicerack library.

        Arguments:
            verbose (bool, optional): whether to set the verbose mode.
            dry_run (bool, optional): whether this is a DRY-RUN.
            cumin_config (str, optional): the path to Cumin's configuration file.
            cumin_installer_config (str, optional): the path to Cumin's configuration file for the Debian installer.
            conftool_config (str, optional): the path to Conftool's configuration file.
            conftool_schema (str, optional): the path to Conftool's schema file.
            debmonitor_config (str, optional): the path to Debmonitor's INI configuration file. It must have at least
                the following schema::

                    [DEFAULT]
                    server=debmonitor.example.com
                    cert=/etc/debmonitor/ssl/cert.pem
                    key=/etc/debmonitor/ssl/server.key

            spicerack_config_dir (str, optional): the path for the root configuration directory for Spicerack.
                Module-specific configuration will be loaded from `config_dir/module_name/`.
            http_proxy (str, optional): the scheme://url:port of the HTTP proxy to use for external calls.

        """
        # Attributes
        self._verbose = verbose
        self._dry_run = dry_run
        self._http_proxy = http_proxy
        self._cumin_config = cumin_config
        self._cumin_installer_config = cumin_installer_config
        self._conftool_config = conftool_config
        self._conftool_schema = conftool_schema
        self._debmonitor_config = debmonitor_config
        self._spicerack_config_dir = spicerack_config_dir

        self._username = get_username()
        self._current_hostname = gethostname()
        self._irc_logger = irc_logger
        self._confctl: Optional[Confctl] = None
        self._mgmt_password: str = ""
        self._actions = ActionsDict()

    @property
    def dry_run(self) -> bool:
        """Getter for the ``dry_run`` property.

        Returns:
            bool: True if the DRY-RUN mode is set, False otherwise.

        """
        return self._dry_run

    @property
    def verbose(self) -> bool:
        """Getter for the ``verbose`` property.

        Returns:
            bool: True if the verbose mode is set, False otherwise.

        """
        return self._verbose

    @property
    def username(self) -> str:
        """Getter for the current username.

        Returns:
            str: the name of the effective running user.

        """
        return self._username

    @property
    def config_dir(self) -> str:
        """Getter for Spicerack's configuration file directory.

        Returns:
            str: a filesystem location of configuration files.

        """
        return self._spicerack_config_dir

    @property
    def http_proxy(self) -> str:
        """Getter for the HTTP PROXY to use for external calls.

        Returns:
            str: the scheme://url:port of the proxy.

        """
        return self._http_proxy

    @property
    def requests_proxies(self) -> Optional[Dict[str, str]]:
        """Getter to return the HTTP proxy configuration for the Requests module.

        Returns:
            dict: with the proxies as required by Requests documentation.
            :py:data:`None`: if no HTTP proxy is set.

        See Also:
            https://requests.readthedocs.io/en/master/user/advanced/#proxies

        """
        if not self._http_proxy:
            return None

        return {"http": self._http_proxy, "https": self._http_proxy}

    @property
    def irc_logger(self) -> Logger:
        """Getter for the ``irc_logger`` property.

        Returns:
            logging.Logger: the logger instance to write to IRC.

        """
        return self._irc_logger

    @property
    def actions(self) -> ActionsDict:
        """Getter for the ``actions`` property.

        Returns:
            wmflib.actions.ActionsDict: a dictionary to log and record cookbook actions.

        """
        return self._actions

    @property
    def icinga_master_host(self) -> RemoteHosts:
        """Getter for the ``icinga_master_host`` property.

        Returns:
            spicerack.remote.RemoteHosts: the instance to execute commands on the Icinga master host.

        """
        return self.remote().query(self.dns().resolve_cname(ICINGA_DOMAIN))

    @property
    def netbox_master_host(self) -> RemoteHosts:
        """Getter for the ``netbox_master_host`` property.

        Returns:
            spicerack.remote.RemoteHosts: the instance to execute commands on the Netbox master host.

        """
        return self.remote().query(self.dns().resolve_cname(NETBOX_DOMAIN))

    def remote(self, installer: bool = False) -> Remote:
        """Get a Remote instance.

        Arguments:
            installer (bool, optional): whether to use the special configuration to connect to a Debian installer
                or freshly re-imaged host prior to its first Puppet run.

        Returns:
            spicerack.remote.Remote: the Remote instance.

        """
        return Remote(self._cumin_installer_config if installer else self._cumin_config, dry_run=self._dry_run)

    def confctl(self, entity_name: str) -> ConftoolEntity:
        """Access a Conftool specific entity instance.

        Arguments:
            entity_name (str): the name of a Conftool entity. Possible values: ``node``, ``service``, ``discovery``,
                ``mwconfig``.

        Returns:
            spicerack.confctl.ConftoolEntity: the confctl entity instance.

        """
        if self._confctl is None:
            self._confctl = Confctl(
                config=self._conftool_config,
                schema=self._conftool_schema,
                dry_run=self._dry_run,
            )

        return self._confctl.entity(entity_name)

    def dhcp(self, remote_hosts: RemoteHosts) -> DHCP:  # pylint: disable=no-self-use
        """Return a DHCP configuration manager for specified site.

        Arguments:
            remote_hosts (RemoteHosts instance): Hosts to operate on, which are normally install servers with dhcp.

        Returns:
            spicerack.dhcp.DHCP : A DHCP configuration instance

        """
        return DHCP(remote_hosts)

    def dns(self) -> Dns:  # pylint: disable=no-self-use
        """Get a Dns instance.

        Returns:
            wmflib.dns.Dns: a Dns instance that will use the operating system default namserver(s).

        """
        return Dns()

    def discovery(self, *records: str) -> Discovery:
        """Get a Discovery instance.

        Arguments:
            *records (str): arbitrary positional arguments, each one must be a Discovery DNS record name.

        Returns:
            spicerack.dnsdisc.Discovery: the pre-configured Discovery instance for the given records.

        """
        return Discovery(
            self.confctl("discovery"),
            self.remote(),
            list(records),
            dry_run=self._dry_run,
        )

    def mediawiki(self) -> MediaWiki:
        """Get a MediaWiki instance.

        Returns:
            spicerack.mediawiki.MediaWiki: the MediaWiki instance.

        """
        return MediaWiki(
            self.confctl("mwconfig"),
            self.remote(),
            self._username,
            dry_run=self._dry_run,
        )

    def mysql(self) -> Mysql:
        """Get a Mysql instance.

        Returns:
            spicerack.mysql.Mysql: the Mysql instance.

        """
        return Mysql(dry_run=self._dry_run)

    def mysql_legacy(self) -> MysqlLegacy:
        """Get a MysqlLegacy instance.

        Returns:
            spicerack.mysql_legacy.MysqlLegacy: the MysqlLegacy instance.

        """
        return MysqlLegacy(self.remote(), dry_run=self._dry_run)

    def redis_cluster(self, cluster: str) -> RedisCluster:
        """Get a RedisCluster instance.

        Arguments:
            cluster (str): the name of the cluster.

        Returns:
            spicerack.redis_cluster.RedisCluster: the cluster instance.

        """
        return RedisCluster(
            cluster,
            os.path.join(self._spicerack_config_dir, "redis_cluster"),
            dry_run=self._dry_run,
        )

    def elasticsearch_clusters(
        self, clustergroup: str, write_queue_datacenters: Sequence[str]
    ) -> ElasticsearchClusters:
        """Get an ElasticsearchClusters instance.

        Arguments:
            clustergroup (str): name of cluster group e.g ``search_eqiad``.
            write_queue_datacenters (Sequence[str]): Sequence of which core DCs to query write queues for.

        Returns:
            spicerack.elasticsearch_cluster.ElasticsearchClusters: ElasticsearchClusters instance.

        """
        return create_elasticsearch_clusters(
            clustergroup,
            write_queue_datacenters,
            self.remote(),
            self.prometheus(),
            dry_run=self._dry_run,
        )

    def admin_reason(self, reason: str, task_id: Optional[str] = None) -> Reason:
        """Get an administrative Reason instance.

        Arguments:
            reason (str): the reason to use to justify an administrative action. See `spicerack.administrative.Reason`
                for all the details.
            task_id (str, optional): the task ID to mention in the reason.

        Returns:
            spicerack.administrative.Reason: the administrative Reason instance.

        """
        return Reason(reason, self._username, self._current_hostname, task_id=task_id)

    def icinga_hosts(self, target_hosts: TypeHosts, *, verbatim_hosts: bool = False) -> IcingaHosts:
        """Get an IcingaHosts instance.

        Arguments:
            target_hosts (spicerack.typing.TypeHosts): the target hosts either as a NodeSet instance or a sequence
                of strings.
            verbatim_hosts (bool, optional): if :py:data:`True` use the hosts passed verbatim as is, if instead
                :py:data:`False`, the default, consider the given target hosts as FQDNs and extract their hostnames to
                be used in Icinga.

        Returns:
            spicerack.icinga.IcingaHosts: IcingaHosts instance.

        """
        return IcingaHosts(self.icinga_master_host, target_hosts, verbatim_hosts=verbatim_hosts)

    def puppet(self, remote_hosts: RemoteHosts) -> PuppetHosts:  # pylint: disable=no-self-use
        """Get a PuppetHosts instance for the given remote hosts.

        Arguments:
            remote_hosts (spicerack.remote.RemoteHosts): the instance with the target hosts.

        Returns:
            spicerack.puppet.PuppetHosts: the instance to manage Puppet on the target hosts.

        """
        return PuppetHosts(remote_hosts)

    def puppet_master(self) -> PuppetMaster:
        """Get a PuppetMaster instance to manage hosts and certificates from a Puppet master.

        Returns:
            spicerack.puppet.PuppetMaster: the instance to manage Puppet hosts and certificates.

        """
        return PuppetMaster(self.remote().query(get_puppet_ca_hostname()))

    def ipmi(self, mgmt_fqdn: str) -> Ipmi:
        """Get an Ipmi instance to send remote IPMI commands to management consoles.

        Arguments:
            mgmt_fqdn (str): the management console FQDN to target.

        Returns:
            spicerack.ipmi.Ipmi: the instance to run ipmitool commands.

        """
        if not self._mgmt_password:
            self._mgmt_password = get_management_password()

        return Ipmi(mgmt_fqdn, self._mgmt_password, dry_run=self._dry_run)

    def phabricator(self, bot_config_file: str, section: str = "phabricator_bot") -> Phabricator:
        """Get a Phabricator instance to interact with a Phabricator website.

        Arguments:
            bot_config_file (str): the path to the configuration file for the Phabricator bot, with the following
                structure::

                    [section_name]
                    host = https://phabricator.example.com/api/
                    username = phab-bot
                    token = api-12345

            section (str, optional): the name of the section of the configuration file where to find the required
                parameters.

        Returns:
            wmflib.phabricator.Phabricator: the instance.

        """
        # Allow to specify the configuration file as opposed to other methods so that different clients can use
        # different Phabricator BOT accounts, potentially with different permissions.
        return create_phabricator(bot_config_file, section=section, dry_run=self._dry_run)

    def prometheus(self) -> Prometheus:  # pylint: disable=no-self-use
        """Get an Prometheus instance.

        Returns:
            wmflib.prometheus.Prometheus: Prometheus instance.

        """
        return Prometheus()

    def debmonitor(self) -> Debmonitor:
        """Get a Debmonitor instance to interact with a Debmonitor website.

        Returns:
            spicerack.debmonitor.Debmonitor: the instance.

        Raises:
            KeyError: if any configuration option is missing.

        """
        options = load_ini_config(self._debmonitor_config).defaults()
        return Debmonitor(options["server"], options["cert"], options["key"], dry_run=self._dry_run)

    def management(self) -> Management:
        """Get a Management instance to interact with the management interfaces.

        .. deprecated:: v1.0.0
            use :py:meth:`spicerack.Spicerack.netbox_server` instead, whose returned object has a ``mgmt_fqdn``
            and ``asset_tag_fqdn`` properties.

        Returns:
            spicerack.management.Management: the instance.

        """
        return Management(self.dns())

    def ganeti(self) -> Ganeti:
        """Get an instance to interact with Ganeti.

        Returns:
            spicerack.ganeti.Ganeti: the instance

        Raises:
            KeyError: If the configuration file does not contain the correct keys.

        """
        configuration = load_yaml_config(os.path.join(self._spicerack_config_dir, "ganeti", "config.yaml"))

        return Ganeti(
            configuration["username"],
            configuration["password"],
            configuration["timeout"],
            self.remote(),
        )

    def netbox(self, *, read_write: bool = False) -> Netbox:
        """Get a Netbox instance to interact with Netbox's API.

        Arguments:
            read_write (bool, optional): whether to use a read-write token.

        Returns:
            spicerack.netbox.Netbox: the instance

        """
        config = load_yaml_config(os.path.join(self._spicerack_config_dir, "netbox", "config.yaml"))
        if read_write and not self._dry_run:
            token = config["api_token_rw"]
        else:
            token = config["api_token_ro"]

        return Netbox(config["api_url"], token, dry_run=self._dry_run)

    def netbox_server(self, hostname: str, *, read_write: bool = False) -> NetboxServer:
        """Get a NetboxServer instance to interact with a server in Netbox, both physical and virtual.

        Arguments:
            hostname (str): the hostname (not FQDN) of the server to manage.
            read_write (bool, optional): whether to use a read-write token.

        Raises:
            spicerack.netbox.NetboxError: if unable to find or load the server.

        Returns:
            spicerack.netbox.NetboxServer: the NetboxServer instance.

        """
        return self.netbox(read_write=read_write).get_server(hostname)

    def requests_session(  # pylint: disable=no-self-use
        self, name: str, *, timeout: float = requests.DEFAULT_TIMEOUT, tries: int = 3, backoff: float = 1.0
    ) -> requests.Session:
        """Return a new requests Session with timeout and retry logic.

        Params:
            according to :py:func:`wmflib.requests.http_session`.

        Returns:
            requests.Session: the pre-configured session.

        """
        name = f"Spicerack/{__version__} {name}"
        return requests.http_session(name, timeout=timeout, tries=tries, backoff=backoff)

    def etcdctl(self, *, remote_host: RemoteHosts) -> EtcdctlController:  # pylint: disable=no-self-use
        """Add etcdctl control capabilities to the given RemoteHost.

        Params:
            remote_host: Single remote host (that should map one single host)
                to add capabilities to.

        Returns:
            A wrapped RemoteHost with the etcdctl control related methods.

        """
        return EtcdctlController(remote_host=remote_host)
