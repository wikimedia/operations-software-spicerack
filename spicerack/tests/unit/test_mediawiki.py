"""MediaWiki module tests."""
import json
from unittest import mock

import pytest
import requests

from spicerack.mediawiki import MediaWiki, MediaWikiCheckError, MediaWikiError
from spicerack.remote import RemoteExecutionError


class TestMediaWiki:
    """MediaWiki class tests."""

    def setup_method(self):
        """Initialize the test environment for MediaWiki."""
        # pylint: disable=attribute-defined-outside-init
        self.mocked_confctl = mock.MagicMock()
        self.mocked_remote = mock.MagicMock()
        self.mocked_remote.query.return_value.hosts = ["host1"]
        self.username = "user1"
        self.siteinfo_url = "https://api.svc.eqiad.wmnet/w/api.php"
        self.siteinfo_rw = {
            "batchcomplete": True,
            "query": {
                "general": {
                    "readonly": False,
                    "wmf-config": {
                        "wmfEtcdLastModifiedIndex": 123456,
                        "wmfMasterDatacenter": "eqiad",
                    },
                },
            },
        }
        self.siteinfo_ro = {
            "batchcomplete": True,
            "query": {
                "general": {
                    "readonly": True,
                    "readonlyreason": "MediaWiki is in read-only mode for maintenance.",
                    "wmf-config": {
                        "wmfEtcdLastModifiedIndex": 123456,
                        "wmfMasterDatacenter": "eqiad",
                    },
                },
            },
        }

        self.mediawiki = MediaWiki(self.mocked_confctl, self.mocked_remote, self.username, dry_run=False)
        self.mediawiki_dry_run = MediaWiki(self.mocked_confctl, self.mocked_remote, self.username)

    def test_check_config_line(self, requests_mock):
        """It should verify the config published at noc.wikimedia.org."""
        requests_mock.get("http://host1/conf/file1.php.txt", text="data")
        assert self.mediawiki.check_config_line("file1", "data") is True

    def test_get_master_datacenter(self):
        """It should return athe primary site."""
        self.mocked_confctl.get.return_value.__next__.return_value.val = "dc1"
        dc = self.mediawiki.get_master_datacenter()
        self.mocked_confctl.get.assert_called_once_with(scope="common", name="WMFMasterDatacenter")
        assert dc == "dc1"

    def test_get_siteinfo(self, requests_mock):
        """It should get the siteinfo API from a canary host."""
        requests_mock.get(self.siteinfo_url, text=json.dumps(self.siteinfo_ro))
        assert self.mediawiki.get_siteinfo("eqiad") == self.siteinfo_ro

    def test_check_siteinfo_ok(self, requests_mock):
        """It should check that a specific key in siteinfo API matches a value and not raise exception."""
        requests_mock.get(self.siteinfo_url, text=json.dumps(self.siteinfo_rw))
        self.mediawiki.check_siteinfo(
            "eqiad",
            {("query", "general", "wmf-config", "wmfEtcdLastModifiedIndex"): 123456},
        )

    def test_check_siteinfo_multi_ok(self, requests_mock):
        """It should check that multiple keys in siteinfo API matches multiple values and not raise exception."""
        requests_mock.get(self.siteinfo_url, text=json.dumps(self.siteinfo_rw))
        self.mediawiki.check_siteinfo(
            "eqiad",
            {
                ("query", "general", "wmf-config", "wmfEtcdLastModifiedIndex"): 123456,
                ("batchcomplete",): True,
                ("query", "general", "readonly"): False,
            },
        )

    @mock.patch("wmflib.decorators.time.sleep", return_value=None)
    def test_check_siteinfo_raise_check(self, mocked_sleep, requests_mock):
        """It should retry if it doesn't match and raise MediaWikiCheckError after all retries have failed."""
        requests_mock.get(self.siteinfo_url, text=json.dumps(self.siteinfo_ro))
        with pytest.raises(
            MediaWikiCheckError,
            match=r"Expected 'invalid', got 'True' for path: \('batchcomplete',\)",
        ):
            self.mediawiki.check_siteinfo("eqiad", {("batchcomplete",): "invalid"})

        assert mocked_sleep.called

    @mock.patch("wmflib.decorators.time.sleep", return_value=None)
    def test_check_siteinfo_raise_error(self, mocked_sleep, requests_mock):
        """It should retry if it fails and raise MediaWikiError after all retries have failed."""
        requests_mock.get(self.siteinfo_url, text=json.dumps(self.siteinfo_ro))
        with pytest.raises(MediaWikiError, match="Failed to traverse siteinfo for key invalid"):
            self.mediawiki.check_siteinfo("eqiad", {("invalid",): "invalid"})

        assert mocked_sleep.called

    @mock.patch("wmflib.decorators.time.sleep", return_value=None)
    def test_check_siteinfo_key_error(self, mocked_sleep, requests_mock):
        """It should raise MediaWikiError if the key is not present in siteinfo."""
        requests_mock.get(self.siteinfo_url, text=json.dumps(self.siteinfo_ro))
        with pytest.raises(MediaWikiError, match="Failed to traverse siteinfo for key invalid"):
            self.mediawiki.check_siteinfo("eqiad", {("invalid",): "invalid"})

        assert mocked_sleep.called

    @mock.patch("wmflib.decorators.time.sleep", return_value=None)
    def test_check_siteinfo_timeout(self, mocked_sleep, requests_mock):
        """It should raise MediaWikiError if it fails to get siteinfo."""
        requests_mock.get(self.siteinfo_url, exc=requests.exceptions.ConnectTimeout)
        with pytest.raises(MediaWikiError, match="Failed to get siteinfo"):
            self.mediawiki.check_siteinfo("eqiad", {("batchcomplete",): "invalid"})

        assert mocked_sleep.called

    def test_scap_sync_config_file(self):
        """It should run scap sync file on the deployment host."""
        self.mediawiki.scap_sync_config_file("file1", "deployed file1")
        self.mocked_remote.query.assert_called_once_with("C:Deployment::Rsync and R:Class%cron_ensure = absent")
        assert "scap sync-file" in self.mocked_remote.query.return_value.run_sync.call_args[0][0]

    def test_set_readonly(self, requests_mock):
        """It should set the readonly message in Conftool and verify it in siteinfo."""
        requests_mock.get(self.siteinfo_url, text=json.dumps(self.siteinfo_ro))
        message = self.siteinfo_ro["query"]["general"]["readonlyreason"]
        self.mediawiki.set_readonly("eqiad", message)
        self.mocked_confctl.set_and_verify.assert_called_once_with("val", message, name="ReadOnly", scope="eqiad")

    def test_set_readonly_dry_run(self, requests_mock):
        """It should not set the readonly message in Conftool and the siteinfo check should not raise."""
        requests_mock.get(self.siteinfo_url, text=json.dumps(self.siteinfo_ro))
        self.mediawiki_dry_run.set_readonly("eqiad", "invalid")

    @mock.patch("wmflib.decorators.time.sleep", return_value=None)
    def test_set_readonly_raise(self, mocked_sleep, requests_mock):
        """It should raise MediaWikiCheckError if unable to check the value has changed and not in dry_run."""
        requests_mock.get(self.siteinfo_url, text=json.dumps(self.siteinfo_ro))
        with pytest.raises(MediaWikiCheckError, match="Expected 'invalid', got"):
            self.mediawiki.set_readonly("eqiad", "invalid")

        assert mocked_sleep.called

    def test_set_readwrite(self, requests_mock):
        """It should set the readonly variale in Conftool to False and verify it in siteinfo."""
        requests_mock.get(self.siteinfo_url, text=json.dumps(self.siteinfo_rw))
        self.mediawiki.set_readwrite("eqiad")
        self.mocked_confctl.set_and_verify.assert_called_once_with("val", False, name="ReadOnly", scope="eqiad")

    def test_set_readwrite_dry_run(self, requests_mock):
        """It should not set the readonly variable in Conftool and the siteinfo check should not raise."""
        requests_mock.get(self.siteinfo_url, text=json.dumps(self.siteinfo_ro))
        self.mediawiki_dry_run.set_readwrite("eqiad")

    @mock.patch("wmflib.decorators.time.sleep", return_value=None)
    def test_set_readwrite_raise(self, mocked_sleep, requests_mock):
        """It should raise MediaWikiCheckError if unable to check the value has changed and not in dry_run."""
        requests_mock.get(self.siteinfo_url, text=json.dumps(self.siteinfo_ro))
        with pytest.raises(MediaWikiCheckError, match="Expected 'False', got 'True'"):
            self.mediawiki.set_readwrite("eqiad")

        assert mocked_sleep.called

    def test_set_master_datacenter(self, requests_mock):
        """It should set the master datacenter in Conftool."""
        requests_mock.get(self.siteinfo_url, text=json.dumps(self.siteinfo_ro))
        requests_mock.get(
            self.siteinfo_url.replace("eqiad", "codfw"),
            text=json.dumps(self.siteinfo_ro),
        )
        self.mediawiki.set_master_datacenter("eqiad")
        self.mocked_confctl.set_and_verify.assert_called_once_with(
            "val", "eqiad", name="WMFMasterDatacenter", scope="common"
        )

    def test_set_master_datacenter_dry_run(self, requests_mock):
        """It should not set the master datacenter in Conftool and not raise as the siteinfo check fails."""
        requests_mock.get(self.siteinfo_url, text=json.dumps(self.siteinfo_ro))
        requests_mock.get(
            self.siteinfo_url.replace("eqiad", "codfw"),
            text=json.dumps(self.siteinfo_ro),
        )
        self.mediawiki_dry_run.set_master_datacenter("codfw")

    @mock.patch("wmflib.decorators.time.sleep", return_value=None)
    def test_set_master_datacenter_raise(self, mocked_sleep, requests_mock):
        """It should raise MediaWikiCheckError if unable to check the value has changed and not in dry_run."""
        requests_mock.get(self.siteinfo_url, text=json.dumps(self.siteinfo_ro))
        requests_mock.get(
            self.siteinfo_url.replace("eqiad", "codfw"),
            text=json.dumps(self.siteinfo_ro),
        )
        with pytest.raises(MediaWikiCheckError, match="Expected 'codfw', got 'eqiad'"):
            self.mediawiki.set_master_datacenter("codfw")

        assert mocked_sleep.called

    def test_check_periodic_jobs_enabled(self):
        """It should ensure that the periodic jobs are present and not commented out."""
        self.mediawiki.check_periodic_jobs_enabled("dc1")
        self.mocked_remote.query.assert_called_with("A:mw-maintenance and A:dc1")
        assert "systemctl list-units" in self.mocked_remote.query.return_value.run_sync.call_args[0][0]

    def test_stop_periodic_jobs(self):
        """It should ensure that the periodic jobs are stopped and remaining processes are killed."""
        self.mediawiki.stop_periodic_jobs("dc1")
        self.mocked_remote.query.assert_called_with("A:mw-maintenance and A:dc1")
        assert "systemctl stop" in self.mocked_remote.query.return_value.run_async.call_args_list[0][0][0]
        assert "killall" in self.mocked_remote.query.return_value.run_async.call_args_list[1][0][-2].command
        assert "systemctl list-units" in self.mocked_remote.query.return_value.run_async.call_args_list[2][0][0].command

    def test_stop_periodic_jobs_stray_procs(self):
        """It should not fail is there are leftover php stray processes."""
        self.mocked_remote.query.return_value.run_sync.side_effect = [
            RemoteExecutionError(10, "failed"),
        ]
        self.mediawiki.stop_periodic_jobs("dc1")
