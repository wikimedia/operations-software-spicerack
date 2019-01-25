"""Spicerack package."""
import os

from socket import gethostname

from pkg_resources import DistributionNotFound, get_distribution

from spicerack import interactive, puppet
from spicerack.administrative import Reason
from spicerack.confctl import Confctl
from spicerack.config import load_ini_config
from spicerack.debmonitor import Debmonitor
from spicerack.dns import Dns
from spicerack.dnsdisc import Discovery
from spicerack.elasticsearch_cluster import create_elasticsearch_clusters
from spicerack.icinga import Icinga, ICINGA_DOMAIN
from spicerack.ipmi import Ipmi
from spicerack.log import irc_logger
from spicerack.management import Management
from spicerack.mediawiki import MediaWiki
from spicerack.mysql import Mysql
from spicerack.phabricator import create_phabricator
from spicerack.redis_cluster import RedisCluster
from spicerack.remote import Remote


try:
    __version__ = get_distribution('wikimedia-spicerack').version  # Must be the same used as 'name' in setup.py
    """:py:class:`str`: the version of the current Spicerack module."""
except DistributionNotFound:  # pragma: no cover - this should never happen during tests
    pass  # package is not installed


class Spicerack:
    """Spicerack service locator."""

    def __init__(self, *, verbose=False, dry_run=True, cumin_config='/etc/cumin/config.yaml',
                 conftool_config='/etc/conftool/config.yaml', conftool_schema='/etc/conftool/schema.yaml',
                 debmonitor_config='/etc/debmonitor.conf',
                 spicerack_config_dir='/etc/spicerack'):
        """Initialize the service locator for the Spicerack library.

        Arguments:
            verbose (bool, optional): whether to set the verbose mode.
            dry_run (bool, optional): whether this is a DRY-RUN.
            cumin_config (str, optional): the path to Cumin's configuration file.
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
        """
        # Attributes
        self._verbose = verbose
        self._dry_run = dry_run
        self._cumin_config = cumin_config
        self._conftool_config = conftool_config
        self._conftool_schema = conftool_schema
        self._debmonitor_config = debmonitor_config
        self._spicerack_config_dir = spicerack_config_dir

        self._username = interactive.get_username()
        self._current_hostname = gethostname()
        self._irc_logger = irc_logger
        self._confctl = None

    @property
    def dry_run(self):
        """Getter for the ``dry_run`` property.

        Returns:
            bool: True if the DRY-RUN mode is set, False otherwise.

        """
        return self._dry_run

    @property
    def verbose(self):
        """Getter for the ``verbose`` property.

        Returns:
            bool: True if the verbose mode is set, False otherwise.

        """
        return self._verbose

    @property
    def username(self):
        """Getter for the current username.

        Returns:
            str: the name of the effective running user.

        """
        return self._username

    @property
    def irc_logger(self):
        """Getter for the ``irc_logger`` property.

        Returns:
            logging.Logger: the logger instance to write to IRC.

        """
        return self._irc_logger

    @property
    def icinga_master_host(self):
        """Getter for the ``icinga_master_host`` property.

        Returns:
            spicerack.remote.RemoteHosts: the instance to execute commands on the Icinga master host.

        """
        return self.remote().query(self.dns().resolve_cname(ICINGA_DOMAIN))

    def remote(self):
        """Get a Remote instance.

        Returns:
            spicerack.remote.Remote: the Remote instance.

        """
        return Remote(self._cumin_config, dry_run=self._dry_run)

    def confctl(self, entity_name):
        """Access a Conftool specific entity instance.

        Arguments:
            entity_name (str): the name of a Conftool entity. Possible values: ``node``, ``service``, ``discovery``,
                ``mwconfig``.

        Returns:
            spicerack.confctl.ConftoolEntity: the confctl entity instance.

        """
        if self._confctl is None:
            self._confctl = Confctl(config=self._conftool_config, schema=self._conftool_schema, dry_run=self._dry_run)

        return self._confctl.entity(entity_name)

    def dns(self):  # pylint: disable=no-self-use
        """Get a Dns instance.

        Returns:
            spicerack.dns.Dns: a Dns instance that will use the operating system default namserver(s).

        """
        return Dns()

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
            spicerack.mediawiki.MediaWiki: the MediaWiki instance.

        """
        return MediaWiki(self.confctl('mwconfig'), self.remote(), self._username, dry_run=self._dry_run)

    def mysql(self):
        """Get a Mysql instance.

        Returns:
            spicerack.mysql.Mysql: the Mysql instance.

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
            clustergroup (str): name of cluster group e.g ``search_eqiad``.

        Returns:
            spicerack.elasticsearch_cluster.ElasticsearchClusters: ElasticsearchClusters instance.

        """
        return create_elasticsearch_clusters(clustergroup, self.remote(), dry_run=self._dry_run)

    def admin_reason(self, reason, task_id=None):
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
        return Icinga(self.icinga_master_host)

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

    def ipmi(self):
        """Get an Ipmi instance to send remote IPMI commands to management consoles.

        Returns:
            spicerack.ipmi.Ipmi: the instance to run ipmitool commands.

        """
        return Ipmi(interactive.get_management_password(), dry_run=self._dry_run)

    def phabricator(self, bot_config_file, section='phabricator_bot'):
        """Get a Phabricator instance to interact with a Phabricator website.

        Arguments:
            bot_config_file (str): the path to the configuration file for the Phabricator bot, with the following
                structure::

                    [section_name]
                    host = https://phabricator.example.org/api/
                    username = phab-bot
                    token = api-12345

            section (str, optional): the name of the section of the configuration file where to find the required
                parameters.

        Returns:
            spicerack.phabricator.Phabricator: the instance.

        """
        # Allow to specify the configuration file as opposed to other methods so that different clients can use
        # different Phabricator BOT accounts, potentially with different permissions.
        return create_phabricator(bot_config_file, section=section, dry_run=self._dry_run)

    def debmonitor(self):
        """Get a Debmonitor instance to interact with a Debmonitor website.

        Returns:
            spicerack.debmonitor.Debmonitor: the instance.

        Raises:
            KeyError: if any configuration option is missing.

        """
        options = load_ini_config(self._debmonitor_config).defaults()
        return Debmonitor(options['server'], options['cert'], options['key'], dry_run=self._dry_run)

    def management(self):
        """Get a Management instance to interact with the management interfaces.

        Returns:
            spicerack.management.Management: the instance.

        """
        return Management(self.dns())
