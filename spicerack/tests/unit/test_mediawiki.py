"""MediaWiki module tests."""
import json

from collections import namedtuple
from unittest import mock

import pytest

from spicerack.mediawiki import MediaWiki, MediaWikiError
from spicerack.remote import RemoteExecutionError

from spicerack.tests import caplog_not_available, requests_mock_not_available


ConftoolObj = namedtuple('ConftoolObj', ['key', 'val'])


class TestMediaWiki:
    """MediaWiki class tests."""

    def setup_method(self):
        """Initialize the test environment for MediaWiki."""
        # pylint: disable=attribute-defined-outside-init
        self.mocked_confctl = mock.MagicMock()
        self.mocked_remote = mock.MagicMock()
        self.mocked_remote.query.return_value.hosts = ['host1']
        self.user = 'user1'
        self.siteinfo = {
            'batchcomplete': True,
            'query': {
                'general': {
                    'readonly': True,
                    'readonlyreason': 'MediaWiki is in read-only mode for maintenance.',
                    'wmf-config': {'wmfEtcdLastModifiedIndex': 123456, 'wmfMasterDatacenter': 'eqiad'},
                },
            },
        }
        self.siteinfo_url = 'http://api.svc.eqiad.wmnet/w/api.php'

        self.mediawiki = MediaWiki(self.mocked_confctl, self.mocked_remote, self.user, dry_run=False)
        self.mediawiki_dry_run = MediaWiki(self.mocked_confctl, self.mocked_remote, self.user)

    @pytest.mark.skipif(requests_mock_not_available(), reason='Requires requests-mock fixture')
    def test_check_config_line(self, requests_mock):
        """It should verify the config published at noc.wikimedia.org."""
        requests_mock.get('http://host1/conf/file1.php.txt', text='data')
        assert self.mediawiki.check_config_line('file1', 'data') is True

    @pytest.mark.skipif(requests_mock_not_available(), reason='Requires requests-mock fixture')
    def test_get_siteinfo(self, requests_mock):
        """It should get the siteinfo API from a canary host."""
        requests_mock.get(self.siteinfo_url, text=json.dumps(self.siteinfo))
        assert MediaWiki.get_siteinfo('eqiad') == self.siteinfo

    @pytest.mark.skipif(requests_mock_not_available(), reason='Requires requests-mock fixture')
    def test_check_siteinfo_ok(self, requests_mock):
        """It should check that a specific key in siteinfo API matches a value and not raise exception."""
        requests_mock.get(self.siteinfo_url, text=json.dumps(self.siteinfo))
        self.mediawiki.check_siteinfo('eqiad', ['query', 'general', 'wmf-config', 'wmfEtcdLastModifiedIndex'], 123456)

    @pytest.mark.skipif(requests_mock_not_available(), reason='Requires requests-mock fixture')
    @mock.patch('spicerack.decorators.time.sleep', return_value=None)
    def test_check_siteinfo_raise(self, mocked_sleep, requests_mock):
        """It should retry if it doesn't match and raise MediaWikiError after all retries have failed."""
        requests_mock.get(self.siteinfo_url, text=json.dumps(self.siteinfo))
        with pytest.raises(MediaWikiError, match=r"Expected 'invalid', got 'True' for path: \['batchcomplete'\]"):
            self.mediawiki.check_siteinfo('eqiad', ['batchcomplete'], 'invalid')

        assert mocked_sleep.called

    @pytest.mark.skipif(caplog_not_available() or requests_mock_not_available(),
                        reason='Requires caplog and requests-mock fixtures')
    def test_check_siteinfo_dry_run(self, requests_mock, caplog):
        """It should retry if it doesn't match and not raise if failed but in dry-run."""
        requests_mock.get(self.siteinfo_url, text=json.dumps(self.siteinfo))
        self.mediawiki_dry_run.check_siteinfo('eqiad', ['batchcomplete'], 'invalid')
        assert "Expected 'invalid', got 'True' for path: ['batchcomplete']" in caplog.text

    @pytest.mark.skipif(caplog_not_available() or requests_mock_not_available(),
                        reason='Requires caplog and requests-mock fixtures')
    @mock.patch('spicerack.decorators.time.sleep', return_value=None)
    def test_check_siteinfo_key_error(self, mocked_sleep, requests_mock):
        """It should retry if it doesn't match and not raise if failed but in dry-run."""
        requests_mock.get(self.siteinfo_url, text=json.dumps(self.siteinfo))
        with pytest.raises(KeyError):
            self.mediawiki.check_siteinfo('eqiad', ['invalid'], 'invalid')

        assert not mocked_sleep.called

    def test_scap_sync_config_file(self):
        """It should run scap sync file on the deployment host."""
        self.mediawiki.scap_sync_config_file('file1', 'deployed file1')
        self.mocked_remote.query.assert_called_once_with('C:Deployment::Rsync and R:Class%cron_ensure = absent')
        assert 'scap sync-file' in self.mocked_remote.query.return_value.run_sync.call_args[0][0]

    def test_set_readonly(self):
        """It should set the readonly message in Conftool."""
        self.mediawiki.set_readonly('dc1', 'readonly message')
        self.mocked_confctl.update.assert_called_once_with({'val': 'readonly message'}, name='ReadOnly', scope='dc1')

    def test_set_master_datacenter(self):
        """It should set the master datacenter in Conftool."""
        self.mediawiki.set_master_datacenter('dc1')
        self.mocked_confctl.update.assert_called_once_with({'val': 'dc1'}, name='WMFMasterDatacenter', scope='common')
        self.mocked_confctl.get.assert_called_once_with(scope='common', name='WMFMasterDatacenter')

    def test_set_master_datacenter_fail(self):
        """It should raise MediaWikiError if failed to verify the new value."""
        self.mocked_confctl.get.return_value = [ConftoolObj(key='key1', val='invalid_value')]
        with pytest.raises(
                MediaWikiError, match='MediaWiki config WMFMasterDatacenter record was not set for scope common'):
            self.mediawiki.set_master_datacenter('dc1')

    def test_set_master_datacenter_fail_dry_run(self):
        """It should not raise MediaWikiError if failed to verify the new value in DRY-RUN mode."""
        self.mocked_confctl.get.return_value = [ConftoolObj(key='key1', val='invalid_value')]
        self.mediawiki_dry_run.set_master_datacenter('dc1')

    def test_check_cronjobs_enabled(self):
        """It should ensure that the cronjobs are present and not commented out."""
        self.mediawiki.check_cronjobs_enabled('dc1')
        self.mocked_remote.query.assert_called_once_with('P{O:mediawiki_maintenance} and A:dc1')
        assert 'crontab -u www-data -l' in self.mocked_remote.query.return_value.run_sync.call_args[0][0]

    def test_stop_cronjobs(self):
        """It should ensure that the cronjobs are present and not commented out."""
        self.mediawiki.stop_cronjobs('dc1')
        self.mocked_remote.query.assert_called_once_with('P{O:mediawiki_maintenance} and A:dc1')
        assert 'crontab -u www-data -r' in self.mocked_remote.query.return_value.run_async.call_args[0][0]

    def test_stop_cronjobs_stray_procs(self):
        """It should not fail is there are leftover php stray processes."""
        self.mocked_remote.query.return_value.run_sync.side_effect = [0, RemoteExecutionError(10, 'failed')]
        self.mediawiki.stop_cronjobs('dc1')
