"""Alertmanager module."""
import logging
import re
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterator, Mapping, Optional, Sequence, Tuple, Union

from cumin import NodeSet
from requests import Response
from requests.exceptions import RequestException
from wmflib.requests import DEFAULT_RETRY_STATUS_CODES, http_session

from spicerack.administrative import Reason
from spicerack.exceptions import SpicerackError
from spicerack.typing import TypeHosts

logger = logging.getLogger(__name__)
MatchersType = Sequence[Dict[str, Union[str, int, float, bool]]]
PORT_REGEX = "(:[0-9]+)?"
ALERTMANAGER_URLS: Tuple[str, str] = (
    "http://alertmanager-eqiad.wikimedia.org",
    "http://alertmanager-codfw.wikimedia.org",
)


class AlertmanagerHosts:
    """Operate on Alertmanager via its APIs."""

    def __init__(
        self,
        target_hosts: TypeHosts,
        *,
        verbatim_hosts: bool = False,
        dry_run: bool = True,
    ) -> None:
        """Initialize the instance.

        When using Alertmanager in high availability (cluster) make sure to pass all hosts in your cluster as
        `alertmanager_urls`.

        Arguments:
            target_hosts (spicerack.typing.TypeHosts): the target hosts either as a NodeSet instance or a sequence of
                strings.
            verbatim_hosts (bool, optional): if :py:data:`True` use the hosts passed verbatim as is, if instead
                :py:data:`False`, the default, consider the given target hosts as FQDNs and extract their hostnames to
                be used in Alertmanager.
            dry_run (bool, optional): set to False to cause writes to Alertmanager occur.

        Raises:
            spicerack.alertmanager.AlertmanagerError: if no target hosts are provided.

        """
        if not verbatim_hosts:
            target_hosts = [target_host.split(".")[0] for target_host in target_hosts]

        if isinstance(target_hosts, NodeSet):
            self._target_hosts = target_hosts
        else:
            self._target_hosts = NodeSet.fromlist(target_hosts)

        if not self._target_hosts:
            raise AlertmanagerError("Got empty target hosts list.")

        # Alertmanager API return HTTP 500 (Internal Server Error) on some requests with a valid JSON response
        # For example when trying to delete a silence that doesn't exist or has already been deleted or is expired
        # Do not retry on 500 and accept it's first response.
        self._http_session = http_session(
            ".".join((self.__module__, self.__class__.__name__)),
            timeout=2,
            retry_codes=tuple(i for i in DEFAULT_RETRY_STATUS_CODES if i != 500),
        )

        self._alertmanager_urls = ALERTMANAGER_URLS
        self._verbatim_hosts = verbatim_hosts
        self._dry_run = dry_run

    @contextmanager
    def downtimed(
        self,
        reason: Reason,
        *,
        matchers: MatchersType = (),
        duration: timedelta = timedelta(hours=4),
        remove_on_error: bool = False,
    ) -> Iterator[None]:
        """Context manager to perform actions while the hosts are downtimed on Alertmanager.

        Arguments:
            reason (spicerack.administrative.Reason): the reason to set for the downtime on Alertmanager.
            matchers (list, optional): an optional list of matchers to be applied to the downtime. They will be added
                to the matcher automatically generated to match the current instance ``target_hosts`` hosts. For this
                reason the provided matchers cannot be for the instance property. The downtime will match alerts that
                match **all** the matchers provided, as they are ANDed by AlertManager.
            duration (datetime.timedelta, optional): the length of the downtime period.
            remove_on_error: should the downtime be removed even if an exception was raised.

        Yields:
            None: it just yields control to the caller once Alertmanager has
            received the downtime and deletes the downtime once getting back the
            control.

        """
        downtime_id = self.downtime(reason, matchers=matchers, duration=duration)
        try:
            yield
        except BaseException:
            if remove_on_error:
                self.remove_downtime(downtime_id)
            raise
        else:
            self.remove_downtime(downtime_id)

    def _api_request(self, method: str, path: str, json: Optional[Mapping] = None) -> Response:
        """Perform an Alertmanager API request on multiple endpoints and return the requests response object.

        The request is performed on all configured alertmanager endpoints and returns at the first successful response.

        Arguments:
            method (str): the HTTP method to use for the request.
            path (str): the final API path to call, the base path is prefixed automatically.
            json (typing.Mapping, optional): if present, the JSON payload to send in the request.

        Returns:
            requests.Response: the requests response object.

        Raises:
            spicerack.alertmanager.AlertmanagerError: if unable to perform the request on any alertmanager endpoint.

        """
        response = None
        for am_url in self._alertmanager_urls:
            url = f"{am_url}/api/v2/{path}"
            if self._dry_run and method.lower() not in ("head", "get"):
                logger.debug("Would have called %s %s", method.upper(), url)
                response = Response()
                response.status_code = 200
                return response

            try:
                response = self._http_session.request(method, url, json=json)
                response.raise_for_status()
                return response
            except RequestException as e:
                logger.error("Failed to %s to %s: %s", method.upper(), url, e)

        raise AlertmanagerError(f"Unable to {method.upper()} to any Alertmanager: {self._alertmanager_urls}", response)

    def downtime(self, reason: Reason, *, matchers: MatchersType = (), duration: timedelta = timedelta(hours=4)) -> str:
        """Issue a new downtime.

        Arguments:
            reason (Reason): the downtime reason.
            matchers (list, optional): an optional list of matchers to be applied to the downtime. They will be added
                to the matcher automatically generated to match the current instance ``target_hosts`` hosts. For this
                reason the provided matchers cannot be for the instance property. The downtime will match alerts that
                match **all** the matchers provided, as they are ANDed by AlertManager.
            duration (datetime.timedelta, optional): the length of the downtime period.

        Returns:
            str: the downtime ID.

        Raises:
            spicerack.alertmanager.AlertmanagerError: if none of the `alertmanager_urls` API returned a success or the
            parameters are invalid.

        """
        if any(item.get("name") == "instance" for item in matchers):
            raise AlertmanagerError("Matchers cannot target the instance property.")

        # If none of the hosts has the port embedded, put the port regex only once at the end
        group_port = all(":" not in host for host in self._target_hosts)
        group_port_regex = PORT_REGEX if group_port else ""
        target_hosts = []
        for host in sorted(self._target_hosts):
            if group_port or ":" in host:
                target_hosts.append(re.escape(host))
            else:
                target_hosts.append(f"{re.escape(host)}{PORT_REGEX}")

        target_regex = "|".join(target_hosts)
        target_matchers = list(matchers)
        target_matchers.append({"name": "instance", "value": f"^({target_regex}){group_port_regex}$", "isRegex": True})

        # Swagger API format for startsAt/endsAt is 'date-time' which includes a timezone.
        start = datetime.utcnow().astimezone(tz=timezone.utc)
        end = start + duration
        payload = {
            "matchers": target_matchers,
            "startsAt": start.isoformat(),
            "endsAt": end.isoformat(),
            "comment": str(reason),
            "createdBy": reason.owner,
        }
        response = self._api_request("post", "silences", json=payload)
        if self._dry_run:  # Bail out earlier as the next statement would fail
            return ""

        silence = response.json()["silenceID"]
        logger.info("Created silence ID %s", silence)
        return silence

    def remove_downtime(self, downtime_id: str) -> None:
        """Remove a downtime.

        Arguments:
            downtime_id (str): the downtime ID to remove.

        Raises:
            spicerack.alertmanager.AlertmanagerError: if none of the `alertmanager_urls` API returned a success.

        """
        try:
            self._api_request("delete", f"silence/{downtime_id}")
            logger.info("Deleted silence ID %s", downtime_id)
        except AlertmanagerError as e:
            if (
                e.response is not None
                and e.response.status_code == 500
                and "silence" in e.response.json()
                and "already expired" in e.response.json()
            ):
                logger.warning("Silence ID %s has been already deleted or is expired", downtime_id)
            else:
                raise


class AlertmanagerError(SpicerackError):
    """Custom exception class for errors of this module."""

    def __init__(self, message: str, response: Optional[Response] = None) -> None:
        """Initializes an AlertmanagerError instance with the API response instance.

        Arguments:
            message (str): the actual exception message.
            response (requests.Response, optional): the requests response object, if present.

        """
        super().__init__(message)
        self.response = response
