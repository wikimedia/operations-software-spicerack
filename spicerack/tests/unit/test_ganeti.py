"""Ganeti Module test."""

import json

import pytest
import requests

from spicerack.exceptions import SpicerackError
from spicerack.ganeti import CLUSTER_SVC_URL, CLUSTERS_AND_ROWS, Ganeti, GanetiError, GanetiRAPI
from spicerack.tests import get_fixture_path, requests_mock_not_available


class TestGaneti:
    """Ganeti tests class."""

    def setup_method(self):
        """Setup test environment."""
        # pylint: disable=attribute-defined-outside-init

        self.ganeti = Ganeti(username='fake', password='password123', timeout=10)  # nosec

        self.cluster = 'eqiad'
        self.base_url = CLUSTER_SVC_URL.format(dc=self.cluster) + '/2'

        # load test fixtures
        with open(get_fixture_path('ganeti', 'info.json'), encoding='utf-8') as info_json:
            self.info = info_json.read()
        with open(get_fixture_path('ganeti', '404.json'), encoding='utf-8') as fourohfour_json:
            self.fourohfour = fourohfour_json.read()
        with open(get_fixture_path('ganeti', 'instance.json'), encoding='utf-8') as instance_json:
            self.instance_info = instance_json.read()
        with open(get_fixture_path('ganeti', 'bogus.json'), encoding='utf-8') as bogus_json:
            self.bogus_data = bogus_json.read()

    @pytest.mark.parametrize('cluster', CLUSTERS_AND_ROWS.keys())
    def test_ganeti_clusters(self, cluster):
        """Ganeti.rapi() should return a GanetiRAPI object."""
        assert isinstance(self.ganeti.rapi(cluster), GanetiRAPI)

    def test_ganeti_clusters_failure(self):
        """If a cluster that doesn't exist is passed to Ganeti.rapi(), it should except with a SpicerackError."""
        with pytest.raises(SpicerackError, match=r'Cannot find cluster bogus cluster \(expected .*'):
            self.ganeti.rapi('bogus cluster')

    @pytest.mark.skipif(requests_mock_not_available(), reason='Requires requests-mock fixture')
    def test_ganeti_rapi_master_success(self, requests_mock):
        """The master property of a RAPI should be the hostname for the master of this cluster."""
        requests_mock.get(self.base_url + '/info', text=self.info)

        master = json.loads(self.info)['master']
        rapi = self.ganeti.rapi(self.cluster)
        assert rapi.master == master

    @pytest.mark.skipif(requests_mock_not_available(), reason='Requires requests-mock fixture')
    def test_ganeti_rapi_master_failure(self, requests_mock):
        """If a master is not specified by the uptsream API, the value of master on a RAPI should be None."""
        requests_mock.get(self.base_url + '/info', text=self.bogus_data)
        rapi = self.ganeti.rapi(self.cluster)
        assert rapi.master is None

    @pytest.mark.skipif(requests_mock_not_available(), reason='Requires requests-mock fixture')
    def test_ganeti_rapi_instance_notfound(self, requests_mock):
        """A RAPI object should raise a GanetiError if a requested host does not exist."""
        rapi = self.ganeti.rapi(self.cluster)
        requests_mock.get(
            self.base_url + '/instances/testhost_404', text=self.fourohfour, status_code=requests.codes['not_found']
        )
        with pytest.raises(GanetiError, match=r'Non-200 from API: 404:.*'):
            rapi.fetch_instance('testhost_404')

    @pytest.mark.skipif(requests_mock_not_available(), reason='Requires requests-mock fixture')
    def test_ganeti_rapi_instance_timeout(self, requests_mock):
        """A RAPI object should raise a GanetiError if a request times out."""
        rapi = self.ganeti.rapi(self.cluster)
        requests_mock.get(
            self.base_url + '/instances/timeouthost', exc=requests.exceptions.ConnectTimeout
        )
        with pytest.raises(GanetiError, match='Timeout performing request to RAPI'):
            rapi.fetch_instance('timeouthost')

    @pytest.mark.skipif(requests_mock_not_available(), reason='Requires requests-mock fixture')
    def test_ganeti_rapi_instance_invalid(self, requests_mock):
        """If no mac is present in host data, fetch_instance_mac should raise a GanetiError."""
        rapi = self.ganeti.rapi(self.cluster)
        requests_mock.get(self.base_url + '/instances/testhost_invalid', text=self.bogus_data)
        with pytest.raises(GanetiError, match=''):
            rapi.fetch_instance_mac('testhost_invalid')

    @pytest.mark.skipif(requests_mock_not_available(), reason='Requires requests-mock fixture')
    def test_ganeti_rapi_instance_valid(self, requests_mock):
        """The MAC returned by RAPI.fetch_instance_mac should match the data returned by the API."""
        rapi = self.ganeti.rapi(self.cluster)
        requests_mock.get(self.base_url + '/instances/testhost', text=self.instance_info)
        mac = json.loads(self.instance_info)['nic.macs'][0]
        assert mac == rapi.fetch_instance_mac('testhost')
