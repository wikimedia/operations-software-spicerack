"""Alertmanager module."""

import logging
import re
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional, Union

from cumin import NodeSet, nodeset_fromlist
from requests import Response
from requests.auth import AuthBase
from requests.exceptions import RequestException
from wmflib.requests import DEFAULT_RETRY_STATUS_CODES, http_session

from spicerack.administrative import Reason
from spicerack.exceptions import SpicerackError
from spicerack.typing import TypeHosts

logger = logging.getLogger(__name__)
MatchersType = Sequence[dict[str, Union[str, int, float, bool]]]
PORT_REGEX: str = r"(\..+)?(:[0-9]+)?"
"""The regular expression used to match FQDNs and port numbers in the instance labels."""


class Alertmanager:
    """Operate on Alertmanager via its APIs."""

    def __init__(
        self,
        *,
        alertmanager_urls: Sequence[str],
        http_authentication: Optional[AuthBase] = None,
        http_proxies: Optional[dict[str, str]] = None,
        dry_run: bool = True,
    ) -> None:
        """Initialize the instance.

        When using Alertmanager in high availability (cluster) make sure to pass all hosts in your cluster as
        `alertmanager_urls`.

        Arguments:
            alertmanager_urls: list of Alertmanager instances to connect to.
            http_authentication: Requests authentication configuration to use to connect to the Alertmanager instances.
            http_proxies: HTTP proxies in requests format to use to connect to the Alertmanager instances.
            dry_run: whether this is a DRY-RUN.

        Raises:
            spicerack.alertmanager.AlertmanagerError: if `alertmanager_urls` is empty.

        """
        if not alertmanager_urls:
            raise AlertmanagerError("At least one alertmanager URL is required.")

        # Alertmanager API returns HTTP 500 (Internal Server Error) on some requests with a valid JSON response
        # For example when trying to delete a silence that doesn't exist or has already been deleted or is expired
        # Do not retry on 500 and accept it's first response.
        self._http_session = http_session(
            ".".join((self.__module__, self.__class__.__name__)),
            timeout=2,
            retry_codes=tuple(i for i in DEFAULT_RETRY_STATUS_CODES if i != 500),
        )
        self._alertmanager_urls = alertmanager_urls
        self._dry_run = dry_run

        self._http_authentication = http_authentication
        if http_authentication:
            self._http_session.auth = http_authentication
        self._http_proxies = http_proxies
        if http_proxies:
            self._http_session.proxies = http_proxies

    def _api_request(self, method: str, path: str, json: Optional[Mapping] = None) -> Response:
        """Perform an Alertmanager API request on multiple endpoints and return the requests response object.

        The request is performed on all configured alertmanager endpoints and returns at the first successful response.

        Arguments:
            method: the HTTP method to use for the request.
            path: the final API path to call, the base path is prefixed automatically.
            json: if present, the JSON payload to send in the request.

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

    @contextmanager
    def downtimed(
        self,
        reason: Reason,
        *,
        matchers: MatchersType,
        duration: timedelta = timedelta(hours=4),
        remove_on_error: bool = False,
    ) -> Iterator[None]:
        """Context manager to perform actions while the matching alerts are downtimed on Alertmanager.

        Arguments:
            reason: the reason to set for the downtime on Alertmanager.
            matchers: the list of matchers to be applied to the downtime. The downtime will match alerts that match
                **all** the matchers provided, as they are ANDed by AlertManager.
            duration: the length of the downtime period.
            remove_on_error: should the downtime be removed even if an exception was raised.

        Yields:
            None: it just yields control to the caller once Alertmanager has received the downtime and deletes the
            downtime once getting back the control.

        """
        downtime_id = self.downtime(reason, matchers=matchers, duration=duration)
        try:  # pylint: disable=no-else-raise
            yield
        except BaseException:
            if remove_on_error:
                self.remove_downtime(downtime_id)
            raise
        else:
            self.remove_downtime(downtime_id)

    def downtime(self, reason: Reason, *, matchers: MatchersType, duration: timedelta = timedelta(hours=4)) -> str:
        """Issue a new downtime.

        Arguments:
            reason: the downtime reason.
            matchers: the list of matchers to be applied to the downtime. The downtime will match alerts that match
                **all** the matchers provided, as they are ANDed by AlertManager.
            duration: the length of the downtime period.

        Returns:
            The downtime ID.

        Raises:
            spicerack.alertmanager.AlertmanagerError: if none of the `alertmanager_urls` API returned a success or the
            parameters are invalid.

        """
        if not matchers:
            raise AlertmanagerError("No matchers provided.")

        # Swagger API format for startsAt/endsAt is 'date-time' which includes a timezone.
        # Using astimezone() assumes that the given datetime is in local time, thus use
        # now() and not utcnow() as that will get converted to UTC anyways.
        start = datetime.now().astimezone(tz=timezone.utc)
        end = start + duration
        payload = {
            "matchers": list(matchers),
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
            downtime_id: the downtime ID to remove.

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

    def hosts(
        self,
        target_hosts: TypeHosts,
        *,
        verbatim_hosts: bool = False,
    ) -> "AlertmanagerHosts":
        """Returns an AlertmanagerHosts instance for the specified hosts.

        Arguments:
            target_hosts: the target hosts either as a NodeSet instance or a sequence of strings.
            verbatim_hosts: if :py:data:`True` use the hosts passed verbatim as is, if instead
                :py:data:`False`, the default, consider the given target hosts as FQDNs and extract their hostnames to
                be used in Alertmanager.

        Raises:
            spicerack.alertmanager.AlertmanagerError: if no target hosts are provided.

        """
        return AlertmanagerHosts(
            target_hosts=target_hosts,
            verbatim_hosts=verbatim_hosts,
            alertmanager_urls=self._alertmanager_urls,
            http_authentication=self._http_authentication,
            http_proxies=self._http_proxies,
            dry_run=self._dry_run,
        )


class AlertmanagerHosts(Alertmanager):
    """Operate on Alertmanager for a list of hosts via its APIs."""

    def __init__(
        self,
        target_hosts: TypeHosts,
        *,
        verbatim_hosts: bool = False,
        alertmanager_urls: Sequence[str],
        http_authentication: Optional[AuthBase] = None,
        http_proxies: Optional[dict[str, str]] = None,
        dry_run: bool = True,
    ) -> None:
        """Initialize the instance.

        Arguments:
            target_hosts: the target hosts either as a NodeSet instance or a sequence of strings.
            verbatim_hosts: if :py:data:`True` use the hosts passed verbatim as is, if instead
                :py:data:`False`, the default, consider the given target hosts as FQDNs and extract their hostnames to
                be used in Alertmanager.
            alertmanager_urls: list of Alertmanager instances to connect to.
            http_authentication: Requests authentication configuration to use to connect to the Alertmanager instances.
            http_proxies: HTTP proxies in requests format to use to connect to the Alertmanager instances.
            dry_run: whether this is a DRY-RUN.

        Raises:
            spicerack.alertmanager.AlertmanagerError: if no target hosts are provided.

        """
        super().__init__(
            alertmanager_urls=alertmanager_urls,
            http_authentication=http_authentication,
            http_proxies=http_proxies,
            dry_run=dry_run,
        )
        if not verbatim_hosts:
            target_hosts = [target_host.split(".")[0] for target_host in target_hosts]

        if isinstance(target_hosts, NodeSet):
            self._target_hosts = target_hosts
        else:
            self._target_hosts = nodeset_fromlist(target_hosts)

        if not self._target_hosts:
            raise AlertmanagerError("Got empty target hosts list.")

        self._verbatim_hosts = verbatim_hosts

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
            reason: the reason to set for the downtime on Alertmanager.
            matchers: an optional list of matchers to be applied to the downtime. They will be added to the matcher
                automatically generated to match the current instance ``target_hosts`` hosts. For this reason the
                provided matchers cannot be for the ``instance`` property. The downtime will match alerts that match
                **all** the matchers provided, as they are ANDed by AlertManager.
            duration: the length of the downtime period.
            remove_on_error: should the downtime be removed even if an exception was raised.

        Yields:
            None: it just yields control to the caller once Alertmanager has received the downtime and deletes the
            downtime once getting back the control.

        """
        # Keep this kinda duplicated method from the parent class for a few reasons:
        # * It needs a different default value for the matchers argument.
        # * It needs a different docstring for documenting the different behaviour of the matchers argument.
        # * Calling super() within a contextmanager is not that trivial and will de-facto require more code.
        downtime_id = self.downtime(reason, matchers=matchers, duration=duration)
        try:  # pylint: disable=no-else-raise
            yield
        except BaseException:
            if remove_on_error:
                self.remove_downtime(downtime_id)
            raise
        else:
            self.remove_downtime(downtime_id)

    def downtime(self, reason: Reason, *, matchers: MatchersType = (), duration: timedelta = timedelta(hours=4)) -> str:
        """Issue a new downtime for the given hosts.

        Arguments:
            reason: the downtime reason.
            matchers: an optional list of matchers to be applied to the downtime. They will be added to the matcher
                automatically generated to match the current instance ``target_hosts`` hosts. For this reason the
                provided matchers cannot be for the ``instance`` property. The downtime will match alerts that match
                **all** the matchers provided, as they are ANDed by AlertManager.
            duration: the length of the downtime period.

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
                target_hosts.append(rf"{re.escape(host)}{PORT_REGEX}")

        target_regex = "|".join(target_hosts)
        target_matchers = list(matchers)
        target_matchers.append({"name": "instance", "value": rf"^({target_regex}){group_port_regex}$", "isRegex": True})
        return super().downtime(reason, matchers=target_matchers, duration=duration)


class AlertmanagerError(SpicerackError):
    """Custom exception class for errors of this module."""

    def __init__(self, message: str, response: Optional[Response] = None) -> None:
        """Initializes an AlertmanagerError instance with the API response instance.

        Arguments:
            message: the actual exception message.
            response: the requests response object, if present.

        """
        super().__init__(message)
        self.response = response
