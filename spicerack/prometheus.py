"""Prometheus module."""

import logging

from typing import Dict, List, Optional, Union

import requests

from spicerack.constants import ALL_DATACENTERS
from spicerack.exceptions import SpicerackError


logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


class PrometheusError(SpicerackError):
    """Custom exception class for errors of this module."""


class Prometheus:
    """Class to interact with the Prometheus server."""

    _prometheus_api = 'http://prometheus.svc.{site}.wmnet/ops/api/v1/query'

    def query(self, query: str, site: str, *, timeout: Optional[Union[float, int]] = 10) -> List[Dict]:
        """Preform a generic query.

        Arguments:
            query (str): a prometheus query
            site (str): The site to use for queries. Must be one of
                :py:const:`spicerack.constants.ALL_DATACENTERS`
            timeout (float, int, None, optional): How many seconds to wait for the prometheus to
                send data before giving up, as a float or int. Alternatively None to indicate an
                infinite timeout.

        Returns:
            list: returns an empty list if there are no results otherwise return a list of
            results of the form: {'metric': {}, 'value': [$timestamp, $value]}

        Raises:
            spicerack.prometheus.PrometheusError: on error

        """
        if site not in ALL_DATACENTERS:
            msg = 'site ({site}) must be one of spicerack.constants.ALL_DATACENTERS {dcs}'.format(
                site=site, dcs=ALL_DATACENTERS)
            raise PrometheusError(msg)

        url = self._prometheus_api.format(site=site)
        response = requests.get(url, params={'query': query}, timeout=timeout)
        if response.status_code != requests.codes['ok']:
            msg = 'Unable to get metric: HTTP {code}: {text}'.format(
                code=response.status_code, text=response.text)
            raise PrometheusError(msg)

        result = response.json()

        if result.get('status', 'error') == 'error':
            msg = 'Unable to get metric: {error}'.format(error=result.get('error', 'unknown'))
            raise PrometheusError(msg)

        return result['data']['result']
