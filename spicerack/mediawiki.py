"""MediaWiki module."""
import logging

import requests

from spicerack.exceptions import SpicerackError
from spicerack.remote import RemoteExecutionError


logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


class MediaWikiError(SpicerackError):
    """Custom exception class for errors in this module."""


class MediaWiki:
    """Class to manage MediaWiki-specific resources."""

    _list_cronjobs_command = '"$(crontab -u www-data -l | sed -r \'/^(#|$)/d\')"'

    def __init__(self, conftool, remote, user, dry_run=True):
        """Initialize the instance.

        Arguments:
            conftool (spicerack.confctl.ConftoolEntity): the conftool instance for the mwconfig type objects.
            remote (spicerack.remote.Remote): the Remote instance, pre-initialized.
            user (str): the name of the effective running user.
            dry_run (bool, optional): whether this is a DRY-RUN.
        """
        self._conftool = conftool
        self._remote = remote
        self._user = user
        self._dry_run = dry_run

    def check_config_line(self, filename, expected):
        """Check that a MediaWiki configuration file contains some value.

        Arguments:
            filename (str): filename without extension in wmf-config.
            expected (str): string expected to be found in the configuration file.

        Returns:
            bool: True if the expected string is found in the configuration file, False otherwise.

        Raises:
            requests.exceptions.RequestException: on error.

        """
        noc_server = self._remote.query('O:Noc::Site').hosts[0]
        url = 'http://{noc}/conf/{filename}.php.txt'.format(noc=noc_server, filename=filename)
        mwconfig = requests.get(url, headers={'Host': 'noc.wikimedia.org'})
        found = (expected in mwconfig.text)
        logger.debug('Checked message (found=%s) in MediaWiki config %s:\n%s', found, url, expected)

        return found

    def scap_sync_config_file(self, filename, message):
        """Execute scap sync-file to deploy a specific configuration file of wmf-config.

        Arguments:
            filename (str): the filename without extension of wmf-config.
            message (str): the message to use for the scap sync-file execution.

        Raises:
            spicerack.remote.RemoteExecutionError: on error.

        """
        logger.debug('Syncing MediaWiki wmf-config/%s.php', filename)
        query = 'C:Deployment::Rsync and R:Class%cron_ensure = absent'
        command = 'su - {user} -c \'scap sync-file --force wmf-config/{filename}.php "{message}"\''.format(
            user=self._user, filename=filename, message=message)
        self._remote.query(query).run_sync(command)

    def set_readonly(self, datacenter, readonly):
        """Set the Conftool readonly variable for MediaWiki config in a specific datacenter.

        Arguments:
            datacenter (str): the DC for which the configuration must be changed.
            readonly (str, bool): the readonly message to set it read-only, False to set it read-write.
                It follows MediaWiki logic.

        Raises:
            spicerack.mediawiki.MediaWikiError: on error.

        """
        self._set_and_verify_conftool(scope=datacenter, name='ReadOnly', value=readonly)

    def set_master_datacenter(self, datacenter):
        """Set the MediaWiki config master datacenter variable in Conftool.

        Arguments:
            datacenter (str): the new master datacenter.

        Raises:
            spicerack.mediawiki.MediaWikiError: on error.

        """
        self._set_and_verify_conftool(scope='common', name='WMFMasterDatacenter', value=datacenter)

    def check_cronjobs_enabled(self, datacenter):
        """Check that MediaWiki cronjobs are set in the given DC.

        Arguments:
            datacenter (str): the name of the datacenter to work on.

        Raises:
            spicerack.remote.RemoteExecutionError: on failure.

        """
        targets = self._remote.query('R:class = role::mediawiki_maintenance and A:{dc}'.format(dc=datacenter))
        targets.run_sync('test ' + self._list_cronjobs_command, is_safe=True)

    def stop_cronjobs(self, datacenter):
        """Remove and ensure MediaWiki cronjobs are not present in the given DC.

        Arguments:
            datacenter (str): the name of the datacenter to work on.

        Raises:
            spicerack.remote.RemoteExecutionError: on failure.

        """
        targets = self._remote.query('R:class = role::mediawiki_maintenance and A:{dc}'.format(dc=datacenter))
        logger.info('Disabling MediaWiki cronjobs in %s', datacenter)
        targets.run_async('crontab -u www-data -r', 'killall -r php', 'sleep 5', 'killall -9 -r php')
        targets.run_sync('test -z ' + self._list_cronjobs_command, is_safe=True)

        try:
            targets.run_sync('! pgrep -c php', is_safe=True)
        except RemoteExecutionError:
            # We just log an error, don't actually report a failure to the system. We can live with this.
            logger.error('Stray php processes still present on the maintenance host, please check')

    def _set_and_verify_conftool(self, *, scope, name, value):
        """Set the MediaWiki config Conftool value.

        Arguments:
            scope (str): the Conftool mwconfig scope.
            name (str): the Conftool mwconfig variable name (key).
            value (str): the value to set the variable to.

        Raises:
            spicerack.mediawiki.MediaWikiError: on error.

        """
        self._conftool.update({'val': value}, name=name, scope=scope)
        for obj in self._conftool.get(name=name, scope=scope):
            if obj.val != value and not self._dry_run:
                raise MediaWikiError(
                    'MediaWiki config {name} record was not set for scope {scope}: {record}'.format(
                        name=name, scope=scope, record=obj.key))
