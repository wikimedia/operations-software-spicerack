"""Generic API client module."""

import logging
from typing import Any

from requests import Response, Session
from requests.exceptions import RequestException

from spicerack.exceptions import SpicerackError

logger = logging.getLogger(__name__)


class APIClientError(SpicerackError):
    """General errors raised by this module."""


class APIClientResponseError(APIClientError):
    """Exception class for failed responses to API requests."""

    def __init__(self, response: Response, message: str = "") -> None:
        """Override parent constructor to add the requests's response object.

        Arguments:
            response: the requests's response object.
            message: an optional exception message. A default message with the HTTP method, URL and status code will
                be prefixed before this message.

        """
        method = str(response.request.method).upper()
        super().__init__(f"{method} {response.request.url} returned HTTP {response.status_code} {message}".strip())
        self.response = response


class APIClient:
    """Generic API client class with DRY-RUN support. API-specific classes should derive from this one."""

    def __init__(self, base_url: str, http_session: Session, *, dry_run: bool = True) -> None:
        """Initialize the instance.

        Arguments:
            base_url: the full base URL for the API. It must include the scheme and the domain and can include the
                API path prefix if there is one.
            http_session: the requests's session to use to make the API calls.
            dry_run: whether this is a DRY-RUN.

        """
        self._base_url = base_url
        self._http_session = http_session
        self._dry_run = dry_run

    @property
    def http_session(self) -> Session:
        """Getter for the HTTP session request object to adjust it's configuration if needed.

        Returns:
            the pre-configured session.

        """
        return self._http_session

    def request(self, method: str, uri: str, **kwargs: Any) -> Response:
        """Perform a request against the HTTP session with the provided HTTP method and data.

        Arguments:
            method: the HTTP method to use (e.g. "get").
            uri: the relative URI to request.
            **kwargs: arbitrary keyword arguments, to be passed to the requests library.

        Raises:
            spicerack.apiclient.APIClientError: if the given uri does not start with a slash (/) or the request
                couldn't be performed.
            spicerack.apiclient.APIClientResponseError: if the response status code is not ok, between 400 and 600.

        Returns:
            The API response object if not in DRY-RUN mode or the request is read-only (GET/HEAD/OPTIONS). When in
            DRY-RUN mode and a read-write request is made the API will not be called and a dummy HTTP 200 response
            will be returned.

        """
        if uri[0] != "/":
            raise APIClientError(f"Invalid uri '{uri}', it must start with a /")

        url = f"{self._base_url}{uri}"

        if self._dry_run and method.lower() not in ("head", "get", "options"):  # RW call
            logger.info("Would have called %s on %s", method, url)
            return self._get_dummy_response()

        try:
            response = self._http_session.request(method, url, **kwargs)
        except RequestException as e:
            message = f"Failed to perform {method.upper()} request to {url}"
            if self._dry_run:
                logger.error("%s: %s", message, e)
                return self._get_dummy_response()

            raise APIClientError(message) from e

        if not response.ok:
            raise APIClientResponseError(response)

        return response

    @staticmethod
    def _get_dummy_response() -> Response:
        """Return a dummy requests's Response to be used in DRY-RUN mode."""
        response = Response()
        response.status_code = 200
        return response
