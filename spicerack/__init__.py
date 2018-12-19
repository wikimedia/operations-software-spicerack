"""Spicerack package."""
import os

from socket import gethostname

from pkg_resources import DistributionNotFound, get_distribution

from spicerack import interactive, puppet
from spicerack.administrative import Reason
from spicerack.confctl import Confctl
from spicerack.dns import Dns
from spicerack.dnsdisc import Discovery
from spicerack.elasticsearch_cluster import create_elasticsearch_clusters
from spicerack.icinga import Icinga, ICINGA_DOMAIN
from spicerack.ipmi import Ipmi
from spicerack.log import irc_logger
from spicerack.mediawiki import MediaWiki
from spicerack.mysql import Mysql
from spicerack.redis_cluster import RedisCluster
from spicerack.remote import Remote


try:
    __version__ = get_distribution(__name__).version
    """:py:class:`str`: the version of the current Spicerack module."""
except DistributionNotFound:  # pragma: no cover - this should never happen during tests
    pass  # package is not installed


class Spicerack:
    """Spicerack service locator."""

    def __init__(self, *, verbose=False, dry_run=True, cumin_config='/etc/cumin/config.yaml',
                 conftool_config='/etc/conftool/config.yaml', conftool_schema='/etc/conftool/schema.yaml',
                 spicerack_config_dir='/etc/spicerack'):
        """Initialize the service locator for the Spicerack library.

        Arguments:
            verbose (bool, optional): whether to set the verbose mode.
            dry_run (bool, optional): whether this is a DRY-RUN.
            cumin_config (str): the path of Cumin's configuration file.
            conftool_config (str, optional): the path of Conftool's configuration file.
            conftool_schema (str, optional): the path of Conftool's schema file.
            spicerack_config_dir (str, optional): the path for the root configuration directory for Spicerack.
                Module-specific configuration will be loaded from `config_dir/module_name/`.
        """
        # Attributes
        self._verbose = verbose
        self._dry_run = dry_run
        self._cumin_config = cumin_config
        self._conftool_config = conftool_config
        self._conftool_schema = conftool_schema
        self._spicerack_config_dir = spicerack_config_dir

        self._username = interactive.get_username()
        self._current_hostname = gethostname()
        self._irc_logger = irc_logger
        self._confctl = None

    @property
    def dry_run(self):
        """Getter for the dry_run property.

        Returns:
            bool: True if the DRY-RUN mode is set, False otherwise.

        """
        return self._dry_run

    @property
    def verbose(self):
        """Getter for the dry_run property.

        Returns:
            bool: True if the verbose mode is set, False otherwise.

        """
        return self._verbose

    @property
    def username(self):
        """Getter for the username property.

        Returns:
            str: the name of the effective running user.

        """
        return self._username

    @property
    def irc_logger(self):
        """Getter for the irc_logger property.

        Returns:
            logging.Logger: the logger instance to write to IRC.

        """
        return self._irc_logger

    def remote(self):
        """Get a Remote instance.

        Returns:
            spicerack.remote.Remote: the pre-configured Remote instance.

        """
        return Remote(self._cumin_config, dry_run=self._dry_run)

    def confctl(self, entity_name):
        """Access a Conftool specific entity instance.

        Arguments:
            entity_name (str): the name of a Conftool entity. Available values: node, service, discovery, mwconfig.

        Returns:
            spicerack.confctl.ConftoolEntity: the confctl entity instance.

        """
        if self._confctl is None:
            self._confctl = Confctl(config=self._conftool_config, schema=self._conftool_schema, dry_run=self._dry_run)

        return self._confctl.entity(entity_name)

    def dns(self):
        """Get a Dns instance.

        Returns:
            spicerack.dns.Dns: a Dns instance that will use the operating system default namserver(s).

        """
        return Dns(dry_run=self._dry_run)

    def discovery(self, *records):
        """Get a Discovery instance.

        Arguments:
            *records (str): arbitrary positional arguments, each one must be a Discovery DNS record name.

        Returns:
            spicerack.dnsdisc.Discovery: the pre-configured Discovery instance for the given records.

        """
        return Discovery(self.confctl('discovery'), self.remote(), records, dry_run=self._dry_run)

    def mediawiki(self):
        """Get a MediaWiki instance.

        Returns:
            spicerack.mediawiki.MediaWiki: the pre-configured MediaWiki instance.

        """
        return MediaWiki(self.confctl('mwconfig'), self.remote(), self._username, dry_run=self._dry_run)

    def mysql(self):
        """Get a Mysql instance.

        Returns:
            spicerack.mysql.Mysql: the pre-configured Mysql instance.

        """
        return Mysql(self.remote(), dry_run=self._dry_run)

    def redis_cluster(self, cluster):
        """Get a RedisCluster instance.

        Arguments:
            cluster (str): the name of the cluster.

        Returns:
            spicerack.redis_cluster.RedisCluster: the cluster instance.

        """
        return RedisCluster(cluster, os.path.join(self._spicerack_config_dir, 'redis_cluster'), dry_run=self._dry_run)

    def elasticsearch_clusters(self, clustergroup):
        """Get an ElasticsearchClusters instance.

        Arguments:
            clustergroup (str): name of cluster group e.g search_eqiad

        Returns:
            spicerack.elasticsearch_cluster.ElasticsearchClusters: ElasticsearchClusters instance

        """
        return create_elasticsearch_clusters(clustergroup, self.remote(), dry_run=self._dry_run)

    def admin_reason(self, reason, task_id=''):
        """Get an administrative Reason instance.

        Arguments:
            reason (str): the reason to use to justify an administrative action. See `spicerack.administrative.Reason`
                for all the details.
            task_id (str, optional): the task ID to mention in the reason.

        Returns:
            spicerack.administrative.Reason: the administrative Reason instance.

        """
        return Reason(reason, self._username, self._current_hostname, task_id=task_id)

    def icinga(self):
        """Get an Icinga instance.

        Returns:
            spicerack.icinga.Icinga: Icinga instance.

        """
        icinga_host = self.remote().query(self.dns().resolve_cname(ICINGA_DOMAIN))
        return Icinga(icinga_host)

    def puppet(self, remote_hosts):  # pylint: disable=no-self-use
        """Get a PuppetHosts instance for the given remote hosts.

        Arguments:
            remote_hosts (spicerack.remote.RemoteHosts): the instance with the target hosts.

        Returns:
            spicerack.puppet.PuppetHosts: the instance to manage Puppet on the target hosts.

        """
        return puppet.PuppetHosts(remote_hosts)

    def puppet_master(self):
        """Get a PuppetMaster instance to manage hosts and certificates from a Puppet master.

        Returns:
            spicerack.puppet.PuppetMaster: the instance to manage Puppet hosts and certificates.

        """
        return puppet.PuppetMaster(self.remote().query(puppet.get_puppet_ca_hostname()))

    def ipmi(self):  # pylint: disable=no-self-use
        """Get an Ipmi instance to send remote IPMI commands to management consoles.

        Returns:
            spicerack.ipmi.Ipmi: the instance to run ipmitool commands.

        """
        return Ipmi(interactive.get_management_password())
