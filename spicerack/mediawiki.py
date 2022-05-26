"""MediaWiki module."""
import logging
from typing import Any, Dict, Tuple

from cumin.transports import Command
from wmflib.requests import http_session

from spicerack.confctl import ConftoolEntity
from spicerack.constants import CORE_DATACENTERS
from spicerack.decorators import retry
from spicerack.exceptions import SpicerackCheckError, SpicerackError
from spicerack.remote import Remote, RemoteExecutionError, RemoteHosts

logger = logging.getLogger(__name__)


class MediaWikiError(SpicerackError):
    """Custom exception class for errors in this module."""


class MediaWikiCheckError(SpicerackCheckError):
    """Custom exception class for checking errors in this module."""


class MediaWiki:
    """Class to manage MediaWiki-specific resources."""

    _siteinfo_url: str = "https://api.svc.{dc}.wmnet/w/api.php?action=query&meta=siteinfo&format=json&formatversion=2"

    def __init__(self, conftool: ConftoolEntity, remote: Remote, user: str, dry_run: bool = True) -> None:
        """Initialize the instance.

        Arguments:
            conftool (spicerack.confctl.ConftoolEntity): the conftool instance for the mwconfig type objects.
            remote (spicerack.remote.Remote): the Remote instance.
            user (str): the name of the effective running user.
            dry_run (bool, optional): whether this is a DRY-RUN.

        """
        self._conftool = conftool
        self._remote = remote
        self._user = user
        self._dry_run = dry_run
        self._http_session = http_session(".".join((self.__module__, self.__class__.__name__)), timeout=10)

    def check_config_line(self, filename: str, expected: str) -> bool:
        """Check that a MediaWiki configuration file contains some value.

        Arguments:
            filename (str): filename without extension in wmf-config.
            expected (str): string expected to be found in the configuration file.

        Returns:
            bool: True if the expected string is found in the configuration file, False otherwise.

        Raises:
            requests.exceptions.RequestException: on error.

        """
        noc_server = self._remote.query("O:Noc::Site").hosts[0]
        url = f"http://{noc_server}/conf/{filename}.php.txt"
        mwconfig = self._http_session.get(url, headers={"Host": "noc.wikimedia.org"})
        found = expected in mwconfig.text
        logger.debug(
            "Checked message (found=%s) in MediaWiki config %s:\n%s",
            found,
            url,
            expected,
        )

        return found

    def get_siteinfo(self, datacenter: str) -> Dict:
        """Get the JSON paylod for siteinfo from a random host in a given datacenter.

        Arguments:
            datacenter (str): the DC where to query for siteinfo.

        Returns:
            dict: the parsed JSON from siteinfo.

        Raises:
            requests.exceptions.RequestException: on failure.

        """
        url = MediaWiki._siteinfo_url.format(dc=datacenter)
        headers = {"Host": "en.wikipedia.org"}

        response = self._http_session.get(url, headers=headers, timeout=3)
        response.raise_for_status()

        return response.json()

    def check_siteinfo(self, datacenter: str, checks: Dict[Tuple[str, ...], Any], samples: int = 1) -> None:
        """Check that a specific value in siteinfo matches the expected ones, on multiple hosts.

        Arguments:
            datacenter (str): the DC where to query for siteinfo.
            checks (dict): dictionary of items to check, in which the keys are tuples with the path of keys to traverse
                the siteinfo dictionary to get the value and the values are the expected values to check. To check
                ``siteinfo[key1][key2]`` for a value ``value``, use::

                    {('key1', 'key2'): 'value'}

            samples (int, optional): the number of different calls to siteinfo to perform.

        Raises:
            MediaWikiError: if unable to get siteinfo or unable to traverse the siteinfo dictionary after all tries.
            MediaWikiCheckError: if the value doesn't match after all tries.

        """
        for i in range(1, samples + 1):  # Randomly check different hosts from the load balancer
            logger.debug("Checking siteinfo %d/%d", i, samples)
            self._check_siteinfo(datacenter, checks)

    def scap_sync_config_file(self, filename: str, message: str) -> None:
        """Execute scap sync-file to deploy a specific configuration file of wmf-config.

        Arguments:
            filename (str): the filename without extension of wmf-config.
            message (str): the message to use for the scap sync-file execution.

        Raises:
            spicerack.remote.RemoteExecutionError: on error.

        """
        logger.debug("Syncing MediaWiki wmf-config/%s.php", filename)
        query = "C:Deployment::Rsync and R:Class%cron_ensure = absent"
        command = f"su - {self._user} -c 'scap sync-file --force wmf-config/{filename}.php \"{message}\"'"
        self._remote.query(query).run_sync(command)

    def set_readonly(self, datacenter: str, message: str) -> None:
        """Set the Conftool readonly variable for MediaWiki config in a specific datacenter.

        Arguments:
            datacenter (str): the DC for which the configuration must be changed.
            message (str): the readonly message string to set in MediaWiki.

        Raises:
            spicerack.confctl.ConfctlError: on Conftool errors and failed validation.
            spicerack.mediawiki.MediaWikiError: on failed siteinfo validation.

        """
        self._conftool.set_and_verify("val", message, scope=datacenter, name="ReadOnly")
        self._check_siteinfo_dry_run_aware(
            datacenter,
            {
                ("query", "general", "readonly"): True,
                ("query", "general", "readonlyreason"): message,
            },
            samples=10,
        )

    def set_readwrite(self, datacenter: str) -> None:
        """Set the Conftool readonly variable for MediaWiki config to False to make it read-write.

        Arguments:
            datacenter (str): the DC for which the configuration must be changed.

        Raises:
            spicerack.confctl.ConfctlError: on Conftool errors and failed validation.
            spicerack.mediawiki.MediaWikiError: on failed siteinfo validation.

        """
        self._conftool.set_and_verify("val", False, scope=datacenter, name="ReadOnly")
        self._check_siteinfo_dry_run_aware(datacenter, {("query", "general", "readonly"): False}, samples=10)

    def get_master_datacenter(self) -> str:
        """Return a string representing the primary DC.

        Returns:
            str: the primary DC

        """
        return next(self._conftool.get(scope="common", name="WMFMasterDatacenter")).val

    def set_master_datacenter(self, datacenter: str) -> None:
        """Set the MediaWiki config master datacenter variable in Conftool.

        Arguments:
            datacenter (str): the new master datacenter.

        Raises:
            spicerack.confctl.ConfctlError: on error.

        """
        self._conftool.set_and_verify("val", datacenter, scope="common", name="WMFMasterDatacenter")
        for dc in CORE_DATACENTERS:
            self._check_siteinfo_dry_run_aware(
                dc,
                {("query", "general", "wmf-config", "wmfMasterDatacenter"): datacenter},
                samples=10,
            )

    def get_maintenance_host(self, datacenter: str) -> RemoteHosts:
        """Get an instance to execute commands on the maintenance hosts in a given datacenter.

        Arguments:
            datacenter (str): the datacenter to filter for.

        Returns:
            spicerack.remote.RemoteHosts: the instance for the target host.

        """
        return self._remote.query("A:mw-maintenance and A:" + datacenter)

    def check_periodic_jobs_enabled(self, datacenter: str) -> None:
        """Check that MediaWiki periodic jobs are enabled in the given DC.

        Arguments:
            datacenter (str): the name of the datacenter to work on.

        Raises:
            spicerack.remote.RemoteExecutionError: on failure.

        """
        self.get_maintenance_host(datacenter).run_sync(
            # List all timers that start with mediawiki_job_
            "systemctl list-units 'mediawiki_job_*' --no-legend "
            # Just get the timer name
            "| awk '{print $1}' "
            # For each, check `systemd is-enabled`, which will fail if
            # the unit is disabled. xargs will exit with failure if
            # any of the is-enabled checks fail
            "| xargs -n 1 sh -c 'systemctl is-enabled $0'",
            is_safe=True,
        )

    def check_periodic_jobs_disabled(self, datacenter: str) -> None:
        """Check that MediaWiki periodic jobs are not enabled in the given DC.

        Arguments:
            datacenter (str): the name of the datacenter to work on.

        Raises:
            spicerack.remote.RemoteExecutionError: on failure.

        """
        targets = self.get_maintenance_host(datacenter)
        targets.run_async(
            Command(
                # List all timers that start with mediawiki_job_
                "systemctl list-units 'mediawiki_job_*' --no-legend "
                # Just get the timer name
                "| awk '{print $1}' "
                # For each, check `systemd is-enabled`, which will pass if
                # the unit is enabled. Invert the status code so only disabled
                # pass. 255 instructs xargs to immediately abort.
                "| xargs -n 1 sh -c 'systemctl is-enabled $0 && exit 255 || exit 0'",
            ),
            is_safe=True,
        )

    def stop_periodic_jobs(self, datacenter: str) -> None:
        """Remove and ensure MediaWiki periodic jobs are disabled in the given DC.

        Arguments:
            datacenter (str): the name of the datacenter to work on.

        Raises:
            spicerack.remote.RemoteExecutionError: on failure.

        """
        targets = self.get_maintenance_host(datacenter)
        logger.info("Disabling MediaWiki periodic jobs in %s", datacenter)

        pkill_ok_codes = [0, 1]  # Accept both matches and no matches
        # Stop all systemd job units and timers
        targets.run_async("systemctl stop mediawiki_job_*")
        targets.run_async(
            # Kill MediaWiki wrappers, in case someone has started one manually. See modules/scap/manifests/scripts.pp
            # in the Puppet repo.
            Command('pkill --full "/usr/local/bin/foreachwiki"', ok_codes=pkill_ok_codes),
            Command(
                'pkill --full "/usr/local/bin/foreachwikiindblist"',
                ok_codes=pkill_ok_codes,
            ),
            Command('pkill --full "/usr/local/bin/expanddblist"', ok_codes=pkill_ok_codes),
            Command('pkill --full "/usr/local/bin/mwscript"', ok_codes=pkill_ok_codes),
            Command('pkill --full "/usr/local/bin/mwscriptwikiset"', ok_codes=pkill_ok_codes),
            # Kill all remaining PHP (but not php-fpm) processes for all users
            Command("killall -r 'php$'", ok_codes=[]),
            "sleep 5",
            # No more time to be gentle
            Command("killall -9 -r 'php$'", ok_codes=[]),
            "sleep 1",
        )
        self.check_periodic_jobs_disabled(datacenter)

        try:
            # Look for remaining PHP (but not php-fpm) processes. php-fpm is used for
            # serving noc.wikimedia.org, which is independent of periodic jobs
            targets.run_sync("! pgrep -c 'php$'", is_safe=True)
        except RemoteExecutionError:
            # We just log an error, don't actually report a failure to the system. We can live with this.
            logger.error("Stray php processes still present on the %s maintenance host, please check", datacenter)

    @retry(
        tries=5,
        backoff_mode="constant",
        exceptions=(MediaWikiError, MediaWikiCheckError),
    )
    def _check_siteinfo(self, datacenter: str, checks: Dict[Tuple[str], Any]) -> None:
        """Check that a specific value in siteinfo matches the expected ones, retrying if doesn't match.

        Arguments:
            datacenter (str): the DC where to query for siteinfo.
            checks (dict): dictionary of items to check, in which the keys are tuples with the path of keys to traverse
                the siteinfo dictionary to get the value and the values are the expected values to check. To check
                ``siteinfo[key1][key2]`` for a value ``value``, use::

                    {('key1', 'key2'): 'value'}

        Raises:
            MediaWikiError: if unable to get siteinfo or unable to traverse the siteinfo dictionary after all tries.
            MediaWikiCheckError: if the value doesn't match after all tries.

        """
        try:
            siteinfo = self.get_siteinfo(datacenter)
        except Exception as e:
            raise MediaWikiError("Failed to get siteinfo") from e

        for path, expected in checks.items():
            value = siteinfo.copy()  # No need for deepcopy, it will not be modified
            for key in path:
                try:
                    value = value[key]
                except (KeyError, TypeError) as e:
                    raise MediaWikiError(f"Failed to traverse siteinfo for key {key}") from e

            if value != expected:
                raise MediaWikiCheckError(f"Expected '{expected}', got '{value}' for path: {path}")

    def _check_siteinfo_dry_run_aware(
        self, datacenter: str, checks: Dict[Tuple[str, ...], Any], samples: int = 1
    ) -> None:
        """Dry-run mode aware check_siteinfo. See check_siteinfo() documentation for more details.

        Arguments:
            datacenter (str): the DC where to query for siteinfo.
            checks (dict): dictionary of items to check, in which the keys are tuples with the path of keys to traverse
                the siteinfo dictionary to get the value and the values are the expected values to check. To check
                ``siteinfo[key1][key2]`` for a value ``value``, use::

                    {('key1', 'key2'): 'value'}

            samples (int, optional): the number of different calls to siteinfo to perform.

        Raises:
            MediaWikiError: if unable to get siteinfo or unable to traverse the siteinfo dictionary after all tries.
            MediaWikiCheckError: if the value doesn't match after all tries.

        """
        if self._dry_run:
            logger.debug("Reset samples to check_siteinfo from %s to 1 in dry-run mode", samples)
            samples = 1

        try:
            self.check_siteinfo(datacenter, checks, samples=samples)
        except (MediaWikiError, MediaWikiCheckError) as e:
            if self._dry_run:
                logger.info(e)
            else:
                raise
