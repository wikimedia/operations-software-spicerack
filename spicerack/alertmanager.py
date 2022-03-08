"""Alertmanager module."""
import logging
import re
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, Iterator, Mapping, Optional, Tuple

from cumin import NodeSet
from requests import Response
from requests.exceptions import RequestException
from wmflib.requests import http_session

from spicerack.administrative import Reason
from spicerack.exceptions import SpicerackError
from spicerack.typing import TypeHosts

logger = logging.getLogger(__name__)

ALERTMANAGER_URLS: Tuple[str, str] = (
    "http://alertmanager-eqiad.wikimedia.org",
    "http://alertmanager-codfw.wikimedia.org",
)


def _matchers_from_hosts(hosts: NodeSet) -> Iterable[Dict]:
    matchers = []
    for host in hosts:
        m = {"name": "instance", "value": f"^{re.escape(host)}(:[0-9]+)?$", "isRegex": True}
        matchers.append(m)
    return matchers


class AlertmanagerHosts:
    """Operate on Alertmanager via its APIs."""

    def __init__(
        self,
        target_hosts: TypeHosts,
        *,
        verbatim_hosts: bool = False,
    ) -> None:
        """Initialize the instance.

        Arguments:
            target_hosts (spicerack.typing.TypeHosts): the target hosts either as a NodeSet instance or a sequence of
                strings.
            verbatim_hosts (bool, optional): if :py:data:`True` use the hosts passed verbatim as is, if instead
                :py:data:`False`, the default, consider the given target hosts as FQDNs and extract their hostnames to
                be used in Alertmanager.

        When using Alertmanager in high availability (cluster) make sure to pass all hosts in your cluster as
        `alertmanager_urls`.

        """
        if not verbatim_hosts:
            target_hosts = [target_host.split(".")[0] for target_host in target_hosts]

        if isinstance(target_hosts, NodeSet):
            self._target_hosts = target_hosts
        else:
            self._target_hosts = NodeSet.fromlist(target_hosts)

        if not self._target_hosts:
            raise AlertmanagerError("Got empty target hosts list.")

        self._http_session = http_session(".".join((self.__module__, self.__class__.__name__)), timeout=2)

        self._alertmanager_urls = ALERTMANAGER_URLS
        self._verbatim_hosts = verbatim_hosts
        self._matchers = _matchers_from_hosts(self._target_hosts)

    @contextmanager
    def downtimed(
        self, reason: Reason, *, duration: timedelta = timedelta(hours=4), remove_on_error: bool = False
    ) -> Iterator[None]:
        """Context manager to perform actions while the hosts are downtimed on Alertmanager.

        Arguments:
            reason (spicerack.administrative.Reason): the reason to set for the downtime on Alertmanager.
            duration (datetime.timedelta, optional): the length of the downtime period.
            remove_on_error: should the downtime be removed even if an exception was raised.

        Yields:
            None: it just yields control to the caller once Alertmanager has
            received the downtime and deletes the downtime once getting back the
            control.

        """
        downtime_id = self.downtime(reason, duration=duration)
        try:
            yield
        except BaseException:
            if remove_on_error:
                self.remove_downtime(downtime_id)
            raise
        else:
            self.remove_downtime(downtime_id)

    def _api_request(self, method: str, path: str, json: Optional[Mapping] = None) -> Response:
        for am_url in self._alertmanager_urls:
            url = f"{am_url}/api/v2/{path}"
            try:
                res = self._http_session.request(method, url, json=json)
                res.raise_for_status()
                return res
            except RequestException as e:
                logger.error("Failed to %s to %s: %s", method.upper(), url, e)
        raise AlertmanagerError(f"Unable to {method.upper()} to any Alertmanager: {self._alertmanager_urls}")

    def downtime(self, reason: Reason, *, duration: timedelta = timedelta(hours=4)) -> str:
        """Issue a new downtime.

        Arguments:
            reason (Reason): the downtime reason.
            duration (datetime.timedelta): how long to downtime for.

        Returns:
            str: the downtime ID.

        Raises:
            AlertmanagerError: if none of the `alertmanager_urls` API returned a success.

        """
        # Swagger API format for startsAt/endsAt is 'date-time' which includes a timezone.
        start = datetime.utcnow().astimezone(tz=timezone.utc)
        end = start + duration
        payload = {
            "matchers": self._matchers,
            "startsAt": start.isoformat(),
            "endsAt": end.isoformat(),
            "comment": str(reason),
            "createdBy": reason.owner,
        }
        response = self._api_request("post", "silences", json=payload)
        silence = response.json()["silenceID"]
        logger.info("Created silence ID %s", silence)
        return silence

    def remove_downtime(self, downtime_id: str) -> None:
        """Remove a downtime.

        Arguments:
            downtime_id (str): the downtime ID to remove.

        Raises:
            AlertmanagerError: if none of the `alertmanager_urls` API returned a success.

        """
        self._api_request("delete", f"silence/{downtime_id}")
        logger.info("Deleted silence ID %s", downtime_id)


class AlertmanagerError(SpicerackError):
    """Custom exception class for errors of this module."""