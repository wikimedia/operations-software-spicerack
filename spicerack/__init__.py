"""Spicerack package."""

import sys
from collections.abc import Callable, Sequence
from ipaddress import ip_interface
from logging import Logger, getLogger
from os import getpid
from pathlib import Path
from socket import gethostname
from typing import TYPE_CHECKING, Any, Optional, Union

from git import Repo
from pkg_resources import DistributionNotFound, get_distribution
from requests.auth import HTTPBasicAuth
from wmflib import requests
from wmflib.actions import ActionsDict
from wmflib.config import load_ini_config, load_yaml_config
from wmflib.dns import Dns
from wmflib.interactive import confirm_on_failure, get_username
from wmflib.phabricator import Phabricator, create_phabricator
from wmflib.prometheus import Prometheus, Thanos

from spicerack._log import irc_logger, sal_logger
from spicerack.administrative import Reason
from spicerack.alerting import AlertingHosts
from spicerack.alertmanager import Alertmanager, AlertmanagerHosts
from spicerack.apiclient import APIClient
from spicerack.apt import AptGetHosts
from spicerack.confctl import Confctl, ConftoolEntity
from spicerack.dbctl import Dbctl
from spicerack.debmonitor import Debmonitor
from spicerack.dhcp import DHCP
from spicerack.dnsdisc import Discovery
from spicerack.exceptions import RunCookbookError, SpicerackError
from spicerack.ganeti import Ganeti
from spicerack.hosts import Host
from spicerack.icinga import ICINGA_DOMAIN, IcingaHosts
from spicerack.interactive import get_management_password
from spicerack.ipmi import Ipmi
from spicerack.k8s import Kubernetes
from spicerack.kafka import Kafka
from spicerack.locking import COOKBOOKS_CUSTOM_PREFIX, SPICERACK_PREFIX, Lock, NoLock, get_lock_instance
from spicerack.mediawiki import MediaWiki
from spicerack.mysql import Mysql
from spicerack.netbox import MANAGEMENT_IFACE_NAME, Netbox, NetboxServer
from spicerack.orchestrator import Orchestrator
from spicerack.peeringdb import PeeringDB
from spicerack.puppet import PuppetHosts, PuppetMaster, PuppetServer, get_ca_via_srv_record, get_puppet_ca_hostname
from spicerack.redfish import Redfish, RedfishDell, RedfishSupermicro
from spicerack.redis_cluster import RedisCluster
from spicerack.remote import Remote, RemoteError, RemoteHosts
from spicerack.reposync import RepoSync
from spicerack.service import Catalog
from spicerack.toolforge.etcdctl import EtcdctlController
from spicerack.typing import TypeHosts

try:
    from spicerack.elasticsearch_cluster import ElasticsearchClusters, create_elasticsearch_clusters
except ImportError:  # For when elasticsearch is not supported

    class ElasticsearchClusters:  # type: ignore  # https://github.com/python/mypy/issues/1153
        """Dummy class for the type."""

    def create_elasticsearch_clusters(*args: Any, **kwargs: Any) -> ElasticsearchClusters:  # type: ignore
        """Dummy function to mimic the real one."""
        return ElasticsearchClusters(*args, **kwargs)


if TYPE_CHECKING:  # Imported only during type checking, prevents cyclic imports at runtime
    from spicerack._menu import BaseItem  # pragma: no cover


logger = getLogger(__name__)

try:
    __version__: str = get_distribution("wikimedia-spicerack").version  # Must be the same used as 'name' in setup.py
    """The version of the current Spicerack module."""
except DistributionNotFound:  # pragma: no cover - this should never happen during tests
    pass  # package is not installed


class Spicerack:  # pylint: disable=too-many-instance-attributes
    """Spicerack service locator."""

    def __init__(  # pylint: disable=too-many-arguments
        self,
        *,
        verbose: bool = False,
        dry_run: bool = True,
        cumin_config: str = "/etc/cumin/config.yaml",
        cumin_installer_config: str = "/etc/cumin/config-installer.yaml",
        conftool_config: str = "/etc/conftool/config.yaml",
        conftool_schema: str = "/etc/conftool/schema.yaml",
        debmonitor_config: str = "/etc/debmonitor.conf",
        etcd_config: str = "",  # Locking support, if empty string is disabled
        spicerack_config_dir: str = "/etc/spicerack",
        http_proxy: str = "",
        get_cookbook_callback: Optional[Callable[["Spicerack", str, Sequence[str]], Optional["BaseItem"]]] = None,
        extender_class: Optional[type["SpicerackExtenderBase"]] = None,
    ) -> None:
        """Initialize the service locator for the Spicerack library.

        Arguments:
            verbose: whether to set the verbose mode.
            dry_run: whether this is a DRY-RUN.
            cumin_config: the path to Cumin's configuration file.
            cumin_installer_config: the path to Cumin's configuration file for the Debian installer.
            conftool_config: the path to Conftool's configuration file.
            conftool_schema: the path to Conftool's schema file.
            debmonitor_config: the path to Debmonitor's INI configuration file. It must have at least the following
                schema::

                    [DEFAULT]
                    server=debmonitor.example.com
                    cert=/etc/debmonitor/ssl/cert.pem
                    key=/etc/debmonitor/ssl/server.key

            etcd_config: the path to the Etcd configuration file. Set to empty string to disable the locking support.
            spicerack_config_dir: the path for the root configuration directory for Spicerack. Module-specific
                configuration will be loaded from ``config_dir/module_name/``.
            http_proxy: the ``scheme://url:port`` of the HTTP proxy to use for external calls.
            get_cookbook_callback: a callable to retrieve a CookbookItem to execute a cookbook from inside another
                cookbook.
            extender_class: an optional class object that inherits from :py:class:`spicerack.SpicerackExtenderBase` to
                dynamically add accessors to Spicerack. If not set no extenders will be registered, even if
                ``external_modules_dir`` is specified in the configuration.

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
        self._etcd_config: Optional[Path] = Path(etcd_config) if etcd_config else None
        self._spicerack_config_dir = Path(spicerack_config_dir)
        self._get_cookbook_callback = get_cookbook_callback
        self._spicerack_lock_cache: Optional[Union[Lock, NoLock]] = None

        self._username = get_username()
        self._current_hostname = gethostname()
        self._irc_logger = irc_logger
        self._sal_logger = sal_logger
        self._confctl: Optional[Confctl] = None
        self._service_catalog: Optional[Catalog] = None
        self._management_password: str = ""
        self._actions = ActionsDict()
        self._authdns_servers: dict[str, str] = {}

        self._extender = None
        if extender_class is not None:  # If present, instantiate it with the current instance as parameter
            self._extender = extender_class(spicerack=self)

    def __getattr__(self, name: str) -> Any:
        """Attribute accessor to dynamically load external accessors when present.

        This method is called only if a method or attribute with the given name is not present in the current instance.

        :Parameters:
            according to Python's Data model :py:meth:`object.__getattr__`.

        """
        if self._extender is not None:
            return getattr(self._extender, name)

        raise AttributeError(f"AttributeError: '{self.__class__.__name__}' object has no attribute '{name}'")

    @property
    def _spicerack_lock(self) -> Union[Lock, NoLock]:
        """Get a Lock instance to acquire locks with concurrency and TTL inside Spicerack modules.

        In case the locking support is disabled, a :py:class:`spicerack.locking.NoLock` instance is returned, with the
        same API of the :py:class:`spicerack.locking.Lock` class but that does nothing.

        Returns:
            The lock instance already initialized with a dedicated prefix for the keys.

        """
        if self._spicerack_lock_cache is None:
            self._spicerack_lock_cache = get_lock_instance(
                config_file=self._etcd_config, prefix=SPICERACK_PREFIX, owner=self.owner, dry_run=self._dry_run
            )

        return self._spicerack_lock_cache

    @property
    def dry_run(self) -> bool:
        """Returns :py:data:`True` if the ``DRY-RUN`` mode is set, :py:data:`False` otherwise."""
        return self._dry_run

    @property
    def verbose(self) -> bool:
        """Returns :py:data:`True` if the verbose mode is set, :py:data:`False` otherwise."""
        return self._verbose

    @property
    def username(self) -> str:
        """Returns the name of the effective running user."""
        return self._username

    @property
    def current_hostname(self) -> str:
        """Returns the name of the hostname where the code is running."""
        return self._current_hostname

    @property
    def owner(self) -> str:
        """Returns the owner of the current code: user@host [pid]."""
        return f"{self._username}@{self._current_hostname} [{getpid()}]"

    @property
    def config_dir(self) -> Path:
        """Getter for Spicerack's configuration file directory where the module-specific configs are available.

        They can be accessed with::

            self.config_dir / module_name / config_file

        """
        return self._spicerack_config_dir

    @property
    def http_proxy(self) -> str:
        """Returns the ``scheme://url:port`` of the HTTP PROXY proxy."""
        return self._http_proxy

    @property
    def requests_proxies(self) -> Optional[dict[str, str]]:
        """Returns the HTTP proxy configuration for the Requests module or :py:data:`None` if no HTTP proxy is set.

        See Also:
            https://requests.readthedocs.io/en/master/user/advanced/#proxies

        """
        if not self._http_proxy:
            return None

        return {"http": self._http_proxy, "https": self._http_proxy}

    @property
    def irc_logger(self) -> Logger:
        """Returns the logger instance to write to IRC in the #wikimedia-operations channel."""
        return self._irc_logger

    @property
    def sal_logger(self) -> Logger:
        """Returns the logger instance to write to IRC in the #wikimedia-operations and logging to SAL."""
        return self._sal_logger

    @property
    def actions(self) -> ActionsDict:
        """Returns a dictionary to log and record cookbook actions."""
        return self._actions

    def icinga_master_host(self) -> RemoteHosts:
        """Returns the instance to execute commands on the Icinga master host."""
        return self.remote().query(self.dns().resolve_cname(ICINGA_DOMAIN))

    def netbox_master_host(self) -> RemoteHosts:
        """Returns the instance to execute commands on the Netbox master host."""
        dns = self.dns()
        netbox_hostname = dns.resolve_ptr(dns.resolve_ips("netbox.discovery.wmnet")[0])[0]
        return self.remote().query(netbox_hostname)

    def management_password(self) -> str:
        """Returns the management password.

        It will be asked to the user if not already cached by the current instance.

        """
        if not self._management_password:
            self._management_password = get_management_password()

        return self._management_password

    @property
    def authdns_servers(self) -> dict[str, str]:
        """Getter for the authoritative DNS nameservers currently active in production.

        Returns a dictionary where keys are the hostnames and values are the IPs of the active authoritative
        nameservers.
        """
        if not self._authdns_servers:
            self._authdns_servers = load_yaml_config(self._spicerack_config_dir / "discovery" / "authdns.yaml")

        return self._authdns_servers

    @property
    def authdns_active_hosts(self) -> RemoteHosts:
        """Get a RemoteHosts instance to target the active authoritative nameservers.

        Examples:
            ::

                >>> authdns_hosts = spicerack.authdns_active_hosts
                >>> authdns_hosts.run_sync('some command')

        """
        hosts = ",".join(self.authdns_servers.keys())
        return self.remote().query(f"D{{{hosts}}}")

    def run_cookbook(
        self, cookbook: str, args: Sequence[str] = (), *, raises: bool = False, confirm: bool = False
    ) -> int:
        """Run another Cookbook within the current run.

        The other Cookbook will be executed with the current setup and will log in the same file of the current
        Cookbook that is running. This includes the propagation of DRY-RUN mode to the called cookbooks.

        Arguments:
            cookbook: the path to the cookbook to execute, either in Spicerack's dot notation or the relative path to
                the Python file to execute.
            args: an iterable sequence of strings with the Cookbook's argument. The Cookbook will be executed with the
                same global arguments used for the current run.
            raises: if set to :py:data:`True` raises a :py:class:`spicerack.exceptions.RunCookbookError` exception in
                case the cookbook execution returns a non-zero exit code.
            confirm: if set to :py:data:`True` wraps the call of the cookbook in a
                :py:func:`wmflib.interactive.confirm_on_failure` call. It automatically sets `raises` to
                :py:data:`True`.

        Returns:
            The exit code of the Cookbook, 0 if successful, non-zero if not, unless ``raises`` is set to
            :py:data:`True`, in that case it will raise instead.

        Raises:
            spicerack.exceptions.RunCookbookError: if ``raises`` is set to :py:data:`True` and the cookbook execution
                returns a non-zero exit code.
            spicerack.exceptions.SpicerackError: if the ``get_cookbook_callback`` callback is not set or unable to find
                the cookbook with the given name.

        """
        if self._get_cookbook_callback is None:
            raise SpicerackError("Unable to run other cookbooks, get_cookbook_callback is not set.")

        cookbook_item = self._get_cookbook_callback(self, cookbook, args)
        if cookbook_item is None:
            raise SpicerackError(f"Unable to find cookbook {cookbook}")

        def run_cookbook_item() -> int:
            """Actually run the cookbook.

            Raises:
                spicerack.exceptions.RunCookbookError: if ``raises`` is set to :py:data:`True` and the cookbook
                    returned a non-zero exit code.

            Returns:
                the exit code of the cookbook.

            """
            exit_code = cookbook_item.run()
            if (raises or confirm) and exit_code != 0:
                raise RunCookbookError(
                    f"run_cookbook returned exit code {exit_code} when running cookbook {cookbook} with args: {args}"
                )

            return exit_code

        logger.debug("Executing cookbook %s with args: %s", cookbook, args)
        if confirm:
            exit_code = confirm_on_failure(run_cookbook_item)
        else:
            exit_code = run_cookbook_item()

        return exit_code

    def lock(self) -> Union[Lock, NoLock]:
        """Get a Lock instance to acquire custom locks with concurrency and TTL around specific lines of code.

        In case the locking support is disabled, a :py:class:`spicerack.locking.NoLock` instance is returned, with the
        same API of the :py:class:`spicerack.locking.Lock` class but that does nothing.

        Returns:
            The lock instance already initialized with a dedicated prefix for the keys.

        """
        return get_lock_instance(
            config_file=self._etcd_config, prefix=COOKBOOKS_CUSTOM_PREFIX, owner=self.owner, dry_run=self._dry_run
        )

    def host(self, name: str, *, netbox_read_write: bool = False) -> Host:
        """Get a Host instance that represents a single physical server or virtual machine.

        It exposes a series of accessors like Spicerack but tailored for a single host.

        Arguments:
            name: the short hostname of the host as present in Netbox.
            netbox_read_write: if the Netbox token used should allow read-write operations or not.

        Returns:
            the Host instance.

        Raises:
            spicerack.hosts.HostError: if unable to instantiate the Host instance.

        """
        return Host(name, self, netbox_read_write=netbox_read_write)

    def remote(self, installer: bool = False) -> Remote:
        """Get a Remote instance.

        Arguments:
            installer: whether to use the special configuration to connect to a Debian installer or freshly re-imaged
                host prior to its first Puppet run.

        """
        return Remote(self._cumin_installer_config if installer else self._cumin_config, dry_run=self._dry_run)

    def confctl(self, entity_name: str) -> ConftoolEntity:
        """Get a Conftool specific entity instance.

        Arguments:
            entity_name: the name of a Conftool entity. Possible values: ``node``, ``service``, ``discovery``,
                ``mwconfig``.

        """
        if self._confctl is None:
            self._confctl = Confctl(
                config=self._conftool_config,
                schema=self._conftool_schema,
                dry_run=self._dry_run,
            )

        return self._confctl.entity(entity_name)

    def dbctl(self) -> Dbctl:
        """Get a Dbctl instance to interact with dbctl."""
        return Dbctl(config=self._conftool_config, schema=self._conftool_schema, dry_run=self._dry_run)

    def dhcp(self, datacenter: str) -> DHCP:
        """Return a DHCP configuration manager for the specified datacenter.

        Arguments:
            datacenter: the datacenter for which the DHCP servers will be targeted.

        """
        remote = self.remote()
        try:
            dhcp_hosts = remote.query(f"A:installserver and A:{datacenter}")
        except RemoteError:  # Fallback to eqiad's install server if the above fails, i.e. for a new DC
            datacenter = "eqiad"
            dhcp_hosts = remote.query(f"A:installserver and A:{datacenter}")

        return DHCP(dhcp_hosts, datacenter=datacenter, lock=self._spicerack_lock, dry_run=self._dry_run)

    def dns(self) -> Dns:
        """Get a Dns instance that will use the operating system default nameserver(s)."""
        return Dns()

    def discovery(self, *records: str) -> Discovery:
        """Get a Discovery instance for the given records.

        Arguments:
            *records: arbitrary positional arguments, each one must be a Discovery DNS record name.

        """
        return Discovery(
            conftool=self.confctl("discovery"),
            authdns_servers=self.authdns_servers,
            records=list(records),
            dry_run=self._dry_run,
        )

    def kubernetes(self, group: str, cluster: str) -> Kubernetes:
        """Get a kubernetes client for the specified cluster.

        Arguments:
            group: the cluster group.
            cluster: the kubernetes cluster.

        """
        return Kubernetes(group, cluster, dry_run=self._dry_run)

    def mediawiki(self) -> MediaWiki:
        """Get a MediaWiki instance."""
        return MediaWiki(
            self.confctl("mwconfig"),
            self.remote(),
            self._username,
            dry_run=self._dry_run,
        )

    def mysql(self) -> Mysql:
        """Get a Mysql instance."""
        return Mysql(self.remote(), dry_run=self._dry_run)

    def redis_cluster(self, cluster: str) -> RedisCluster:
        """Get a RedisCluster instance.

        Arguments:
            cluster: the name of the cluster.

        """
        return RedisCluster(
            cluster,
            self._spicerack_config_dir / "redis_cluster",
            dry_run=self._dry_run,
        )

    def reposync(self, name: str) -> RepoSync:
        """Get a Reposync instance.

        Arguments:
            name: the name of the repo to sync.

        """
        config = load_yaml_config(self._spicerack_config_dir / "reposync" / "config.yaml")
        if name not in config["repos"]:
            raise SpicerackError(f"Unknown repo {name}")

        repo_dir = Path(config["base_dir"], name)
        query = ",".join(config["remotes"])
        remote_hosts = self.remote().query(query)

        if not repo_dir.is_dir():
            raise SpicerackError(f"The repo directory ({repo_dir}) does not exist")
        repo = Repo(repo_dir)
        if not repo.bare:
            raise SpicerackError(f"The repo directory ({repo_dir}) is not a bare git repository")

        return RepoSync(repo, self.username, remote_hosts, dry_run=self._dry_run)

    def elasticsearch_clusters(
        self, clustergroup: str, write_queue_datacenters: Sequence[str]
    ) -> ElasticsearchClusters:
        """Get an ElasticsearchClusters instance.

        Arguments:
            clustergroup: name of cluster group e.g ``search_eqiad``.
            write_queue_datacenters: Sequence of which core DCs to query write queues for.

        """
        if sys.version_info >= (3, 10):
            raise SpicerackError("The elasticsearch module is not yet supported on bookworm, use a bullseye host")

        configuration = load_yaml_config(self._spicerack_config_dir / "elasticsearch" / "config.yaml")

        return create_elasticsearch_clusters(
            configuration,
            clustergroup,
            write_queue_datacenters,
            self.remote(),
            self.prometheus(),
            dry_run=self._dry_run,
        )

    def admin_reason(self, reason: str, task_id: Optional[str] = None) -> Reason:
        """Get an administrative Reason instance.

        Arguments:
            reason: the reason to use to justify an administrative action. See
                :py:class:`spicerack.administrative.Reason` for all the details.
            task_id: the task ID to mention in the reason.

        """
        return Reason(reason, self._username, self._current_hostname, task_id=task_id)

    def icinga_hosts(self, target_hosts: TypeHosts, *, verbatim_hosts: bool = False) -> IcingaHosts:
        """Get an IcingaHosts instance.

        Note:
            To interact with both Icinga and Alertmanager alerts, use
            :py:meth:`spicerack.Spicerack.alerting_hosts` instead.

        Arguments:
            target_hosts: the target hosts either as a NodeSet instance or a sequence of strings.
            verbatim_hosts: if :py:data:`True` use the hosts passed verbatim as is, if instead :py:data:`False`, the
                default, consider the given target hosts as FQDNs and extract their hostnames to be used in Icinga.

        """
        return IcingaHosts(
            self.icinga_master_host(), target_hosts, verbatim_hosts=verbatim_hosts, dry_run=self._dry_run
        )

    def puppet(self, remote_hosts: RemoteHosts) -> PuppetHosts:
        """Get a PuppetHosts instance for the given remote hosts.

        Arguments:
            remote_hosts: the instance with the target hosts.

        """
        return PuppetHosts(remote_hosts)

    def puppet_server(self) -> PuppetServer:
        """Get a PuppetServer instance to manage hosts and certificates from a Puppet master."""
        # We only have one CA so it doesn't matter which site we lookup
        domain = "eqiad.wmnet"
        return PuppetServer(self.remote().query(get_ca_via_srv_record(domain)))

    def puppet_master(self) -> PuppetMaster:
        """Get a PuppetMaster instance to manage hosts and certificates from a Puppet master."""
        return PuppetMaster(self.remote().query(get_puppet_ca_hostname()))

    def ipmi(self, target: str) -> Ipmi:
        """Get an Ipmi instance to send remote IPMI commands to management consoles.

        Arguments:
            target: the management console FQDN or IP to target.

        """
        return Ipmi(target, self.management_password(), dry_run=self._dry_run)

    def phabricator(self, bot_config_file: str, section: str = "phabricator_bot") -> Phabricator:
        """Get a Phabricator instance to interact with a Phabricator website.

        The Phabricator object is instantiated with ``allow_empty_identifiers=True``, so that it can be a NOOP when
        executed with an empty string task ID or other identifier.

        Arguments:
            bot_config_file: the path to the configuration file for the Phabricator bot, with the following structure::

                    [section_name]
                    host = https://phabricator.example.com/api/
                    username = phab-bot
                    token = api-12345

            section: the name of the section of the configuration file where to find the required parameters.

        """
        # Allow to specify the configuration file as opposed to other methods so that different clients can use
        # different Phabricator BOT accounts, potentially with different permissions.
        return create_phabricator(bot_config_file, section=section, allow_empty_identifiers=True, dry_run=self._dry_run)

    def prometheus(self) -> Prometheus:
        """Get a Prometheus instance."""
        return Prometheus()

    def thanos(self) -> Thanos:
        """Get a Thanos instance."""
        return Thanos()

    def debmonitor(self) -> Debmonitor:
        """Get a Debmonitor instance to interact with a Debmonitor website.

        Raises:
            KeyError: if any configuration option is missing.

        """
        options = load_ini_config(self._debmonitor_config).defaults()
        return Debmonitor(options["server"], options["cert"], options["key"], dry_run=self._dry_run)

    def ganeti(self) -> Ganeti:
        """Get an instance to interact with Ganeti.

        Raises:
            KeyError: If the configuration file does not contain the correct keys.

        """
        configuration = load_yaml_config(self._spicerack_config_dir / "ganeti" / "config.yaml")

        return Ganeti(
            configuration["username"],
            configuration["password"],
            configuration["timeout"],
            self.remote(),
            self.netbox(),
        )

    def netbox(self, *, read_write: bool = False) -> Netbox:
        """Get a Netbox instance to interact with Netbox's API.

        Arguments:
            read_write: whether to use a read-write token.

        """
        config = load_yaml_config(self._spicerack_config_dir / "netbox" / "config.yaml")
        if read_write and not self._dry_run:
            token = config["api_token_rw"]
        else:
            token = config["api_token_ro"]

        return Netbox(config["api_url"], token, dry_run=self._dry_run)

    def netbox_server(self, hostname: str, *, read_write: bool = False) -> NetboxServer:
        """Get a NetboxServer instance to interact with a server in Netbox, both physical and virtual.

        Arguments:
            hostname: the hostname (not FQDN) of the server to manage.
            read_write: whether to use a read-write token.

        Raises:
            spicerack.netbox.NetboxError: if unable to find or load the server.

        """
        return self.netbox(read_write=read_write).get_server(hostname)

    def requests_session(self, name: str, **kwargs: Any) -> requests.Session:
        """Return a new requests Session with timeout and retry logic.

        Params:
            according to :py:func:`wmflib.requests.http_session`.

        """
        name = f"Spicerack/{__version__} {name}"
        return requests.http_session(name, **kwargs)

    def api_client(self, base_url: str, accept_header: str = "application/json", **kwargs: Any) -> APIClient:
        """Return a generic APIClient instance with the given base URL and HTTP session based on the parameters.

        Arguments:
            base_url: the full base URL for the API. It must include the scheme and the domain and can include the
                API path prefix if there is one.
            accept_header: an optional HTTP ``Accept`` header to set in the HTTP session. By default a JSON API is
                assumed.
            **kwargs: arbitrary keyword arguments passed directly to :py:func:`wmflib.requests.http_session` to
                customize the HTTP session used for this API.

        Returns:
            A generic API client instance with DRY-RUN support.

        """
        session = self.requests_session("APIClient", **kwargs)
        session.headers.update({"Accept": accept_header})
        return APIClient(base_url, session, dry_run=self._dry_run)

    def etcdctl(self, *, remote_host: RemoteHosts) -> EtcdctlController:
        """Add etcdctl control capabilities to the given RemoteHost.

        Params:
            remote_host: Single remote host (that should map one single host)
                to add capabilities to.

        Returns:
            A wrapped RemoteHost with the etcdctl control related methods.

        """
        return EtcdctlController(remote_host=remote_host)

    def kafka(self) -> Kafka:
        """Get an instance to interact with Kafka.

        Raises:
            KeyError: If the configuration file does not contain the correct keys.

        """
        configuration = load_yaml_config(self._spicerack_config_dir / "kafka" / "config.yaml")

        return Kafka(kafka_config=configuration, dry_run=self._dry_run)

    def redfish(self, hostname: str, username: str = "root", password: str = "") -> Redfish:  # nosec
        """Get an instance to talk to the Redfish API of a physical server.

        Notes:
            At the moment only Dell hardware is supported.

        Arguments:
            hostname: the hostname (not FQDN) of the physical server to manage.
            username: the username for the management console.
            password: the password for the management console for the given user. If empty or not provided would use
                the production management password and ask the user for it if not already in memory.

        Raises:
            spicerack.exceptions.SpicerackError: if not a physical server or unable to find the management IP.

        """
        if not password:
            password = self.management_password()

        netbox = self.netbox()
        server_metadata = netbox.get_server(hostname)
        if server_metadata.virtual:
            raise SpicerackError(f"Host {hostname} is not a Physical server, Redfish is not supported.")

        netbox_ip = netbox.api.ipam.ip_addresses.get(device=hostname, interface=MANAGEMENT_IFACE_NAME)

        manufacturer = server_metadata.as_dict()["device_type"]["manufacturer"]["slug"]
        if manufacturer == "dell":
            redfish_class: type[Redfish] = RedfishDell
        elif manufacturer == "supermicro":
            redfish_class = RedfishSupermicro
        else:
            raise SpicerackError(f"The manufacturer {manufacturer} set in Netbox for {hostname} is not supported.")
        return redfish_class(hostname, ip_interface(netbox_ip.address), username, password, dry_run=self._dry_run)

    def alertmanager_hosts(
        self, target_hosts: TypeHosts, *, instance_name: str = "", verbatim_hosts: bool = False
    ) -> AlertmanagerHosts:
        """Get an AlertmanagerHosts instance.

        Note:
            To interact with both Icinga and Alertmanager alerts, use
            :py:meth:`spicerack.Spicerack.alerting_hosts` instead.

        Arguments:
            target_hosts: the target hosts either as a NodeSet instance or a sequence of strings.
            instance_name: the Alertmanager instance defined in the alertmanager/config.yaml config file to interact
                with
            verbatim_hosts: if :py:data:`True` use the hosts passed verbatim as is, if instead :py:data:`False`, the
                default, consider the given target hosts as FQDNs and extract their hostnames to be used in Icinga.

        """
        return self.alertmanager(instance_name=instance_name).hosts(target_hosts, verbatim_hosts=verbatim_hosts)

    def alertmanager(self, instance_name: str = "") -> Alertmanager:
        """Get an Alertmanager instance.

        Arguments:
            instance_name: the Alertmanager instance defined in the alertmanager/config.yaml config file to interact
                with
        Note:
            To interact with Alertmanager alerts attached to an ``instance`` use
            :py:meth:`spicerack.Spicerack.alertmanager_hosts` instead.

        """
        configuration = load_yaml_config(self._spicerack_config_dir / "alertmanager" / "config.yaml")
        if not instance_name:
            instance_name = configuration.get("default_instance", "")
        if not instance_name:
            raise SpicerackError("An alertmanager instance name must be specified when no default is set in config")

        instance = configuration.get("instances", {}).get(instance_name)
        if not instance:
            raise SpicerackError(f"No such alertmanager instance '{instance_name}' found in config")

        http_authentication = None
        if "http_username" in instance and "http_password" in instance:
            http_authentication = HTTPBasicAuth(username=instance["http_username"], password=instance["http_password"])
        http_proxies = self.requests_proxies if instance.get("http_use_proxy") else None

        return Alertmanager(
            alertmanager_urls=instance.get("urls", []),
            http_authentication=http_authentication,
            http_proxies=http_proxies,
            dry_run=self._dry_run,
        )

    def alerting_hosts(self, target_hosts: TypeHosts, *, verbatim_hosts: bool = False) -> AlertingHosts:
        """Get an AlertingHosts instance.

        Arguments:
            target_hosts: the target hosts either as a NodeSet instance or a sequence of strings.
            verbatim_hosts: if :py:data:`True` use the hosts passed verbatim as is, if instead :py:data:`False`, the
                default, consider the given target hosts as FQDNs and extract their hostnames to be used in Icinga.

        """
        return AlertingHosts(
            self.alertmanager_hosts(target_hosts, verbatim_hosts=verbatim_hosts),
            self.icinga_hosts(target_hosts, verbatim_hosts=verbatim_hosts),
        )

    def service_catalog(self, *, refresh: bool = False) -> Catalog:
        """Get a Catalog instance that reflects Puppet's service::catalog hieradata variable.

        The catalog is cached until explicitly refreshed.

        Arguments:
            refresh: when set to :py:data:`True` forces a refresh of the catalog data from disk and caches the new one.

        Returns:
            The service catalog data and caches it.

        """
        if self._service_catalog is None or refresh:
            config = load_yaml_config(self._spicerack_config_dir / "service" / "service.yaml")
            self._service_catalog = Catalog(
                config,
                alertmanager=self.alertmanager(),
                confctl=self.confctl("discovery"),
                authdns_servers=self.authdns_servers,
                dry_run=self._dry_run,
            )

        return self._service_catalog

    def peeringdb(self, *, ttl: int = 86400) -> PeeringDB:
        """Get a PeeringDB instance to interact with the PeeringDB API.

        Arguments:
            ttl: the cache timeout in seconds. If cached items are older than the given TTL they will be ignored and
                fetched again.

        """
        config = load_yaml_config(self._spicerack_config_dir / "peeringdb" / "config.yaml")
        token = config.get("api_token_ro", "")
        cachedir = config.get("cachedir")
        if cachedir is not None:
            cachedir = Path(cachedir)

        return PeeringDB(cachedir=cachedir, ttl=ttl, proxies=self.requests_proxies, token=token)

    def apt_get(self, remote_hosts: RemoteHosts) -> AptGetHosts:
        """Get an APTGet instance for the given remote hosts.

        Examples:
            ::

                >>> hosts = spicerack.remote().query('A:myalias')
                >>> apt_get = spicerack.apt_get(hosts)

        Arguments:
            remote_hosts: the instance with the target hosts.

        """
        return AptGetHosts(remote_hosts)

    def orchestrator(self) -> Orchestrator:
        """Get an instance to interact with the Orchestrator APIs.

        Returns:
            the orcestrator instance.

        """
        # Do not retry on 500 as Orchestrator returns 500 with a JSON for missing objects
        retry_codes = tuple(i for i in requests.DEFAULT_RETRY_STATUS_CODES if i != 500)
        session = self.requests_session("Orchestrator", retry_codes=retry_codes)
        session.headers.update({"Accept": "application/json"})
        return Orchestrator("https://orchestrator.wikimedia.org/api", session, dry_run=self._dry_run)


class SpicerackExtenderBase:
    """Base class to create a Spicerack extender. Necessary when the ``external_modules_dir`` configuration is set."""

    def __init__(self, *, spicerack: Spicerack):
        """Initialize the instance.

        Arguments:
            spicerack: the Spicerack instance.

        """
        self._spicerack = spicerack
