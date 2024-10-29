"""Orchestrator API module."""

import logging
from typing import Any, Type, Union

from requests import Response

try:  # JSONDecodeError present since requests 2.27.0, bullseye has 2.25.1
    from requests.exceptions import JSONDecodeError

    CompatJSONDecodeError: Union[Type[ValueError], Type[JSONDecodeError]] = JSONDecodeError
except ImportError:
    CompatJSONDecodeError = ValueError

from spicerack.apiclient import APIClient, APIClientResponseError
from spicerack.exceptions import SpicerackError

logger = logging.getLogger(__name__)
DEFAULT_PORT = 3306


class OrchestratorError(SpicerackError):
    """General errors raised by this module."""


class Orchestrator(APIClient):
    """Orchestrator API class."""

    def request(self, *args: Any, **kwargs: Any) -> Response:
        """Perform an API request to Orchestrator based on the given parameters.

        See :py:meth:`spicerack.apiclient.APIClient.request` for all the arguments and return values.

        Raises:
            spicerack.apiclient.APIClientError: if the given uri does not start with a slash (/) or if the request
                couldn't be performed.
            spicerack.orchestrator.OrchestratorError: if the response status code is not ok, between 400 and 600.
                It will parse the JSON response and use it in the exception message if present.

        """
        try:
            return super().request(*args, **kwargs)
        except APIClientResponseError as e:
            try:  # Orchestrator tends to response 500 with a JSON on some errors
                response = e.response.json()
                message = f"[{response['Code']}] {response['Message']}"
                if response["Details"]:
                    message += f" {response['Details']}"
            except CompatJSONDecodeError:  # but also responds text on other errors like 404
                message = f"{e.response.text}"

            raise OrchestratorError(message) from e

    def clusters(self) -> dict[str, dict]:
        """Get the current clusters and their metadata.

        Returns:
            a dictionary of clusters with cluster names as keys and cluster metadata as values.

        Raises:
            spicerack.apiclient.APIClient: if the request fails for any reason.

        """
        return {cluster["ClusterAlias"]: cluster for cluster in self.request("get", "/clusters-info").json()}

    def instance(self, instance: str) -> dict:
        """Get the metadata of an instance. It will automatically splits the port if present or use the default if not.

        Arguments:
            instance: the instance name as reported in orchestrator (``FQDN:PORT``). If the port is not present it will
                automatically use the :py:const:`spicerack.orchestrator.DEFAULT_PORT`.

        Returns:
            a dictionary with the instance metadata.

        Raises:
            spicerack.apiclient.APIClient: if the request fails for any reason or the instance does not exists.

        """
        host, port = instance.rsplit(":", 1) if ":" in instance else (instance, str(DEFAULT_PORT))
        return self.request("get", f"/instance/{host}/{port}").json()
