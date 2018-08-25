"""Spicerack package."""
from spicerack import interactive
from spicerack.confctl import Confctl
from spicerack.dnsdisc import Discovery
from spicerack.log import irc_logger
from spicerack.mediawiki import MediaWiki
from spicerack.mysql import Mysql
from spicerack.remote import Remote


class Spicerack:
    """Spicerack service locator."""

    def __init__(self, *, verbose=False, dry_run=True, cumin_config='/etc/cumin/config.yaml',
                 conftool_config='/etc/conftool/config.yaml', conftool_schema='/etc/conftool/schema.yaml'):
        """Initialize the service locator for the Spicerack library.

        Arguments:
            verbose (bool, optional): whether to set the verbose mode.
            dry_run (bool, optional): whether this is a DRY-RUN.
            cumin_config (str): the path of Cumin's configuration file.
            conftool_config (str, optional): the path of Conftool's configuration file.
            conftool_schema (str, optional): the path of Conftool's schema file.
        """
        # Attributes
        self._verbose = verbose
        self._dry_run = dry_run
        self._cumin_config = cumin_config
        self._conftool_config = conftool_config
        self._conftool_schema = conftool_schema

        self._user = interactive.get_user()
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
    def user(self):
        """Getter for the user property.

        Returns:
            str: the name of the effective running user.

        """
        return self._user

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
        return MediaWiki(self.confctl('mwconfig'), self.remote(), self._user, dry_run=self._dry_run)

    def mysql(self):
        """Get a Mysql instance.

        Returns:
            spicerack.mysql.Mysql: the pre-configured Mysql instance.

        """
        return Mysql(self.remote(), dry_run=self._dry_run)
