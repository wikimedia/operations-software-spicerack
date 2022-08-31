"""PeeringDB module."""
import json
import logging
import time
from pathlib import Path
from typing import Dict, MutableMapping, Optional, cast

from wmflib.requests import http_session

from spicerack.exceptions import SpicerackError

logger = logging.getLogger(__name__)


class PeeringDBError(SpicerackError):
    """Custom exception class for errors of the PeeringDB class."""


class CacheMiss(SpicerackError):
    """Custom exception class for cache management."""


class PeeringDB:
    """Basic dumb wrapper over the PeeringDB API.

    Implements the beta/v0 PeeringDB API. Tries to be smart by:

        a) keeping a persistent keep-alived session for multiple requests
        b) operating a local filesystem cache, if so desired.

    """

    baseurl = "https://www.peeringdb.com/api/"

    def __init__(
        self,
        *,
        ttl: int = 86400,
        cachedir: Optional[Path] = None,
        proxies: Optional[MutableMapping[str, str]] = None,
        token: str = "",
    ):
        """Initiliaze the module.

        Arguments:
            ttl (int): TTL for cached objects.
            cachedir (Path, optional): Root path for objects caching.
            proxies (MutableMapping, optional): Proxies for Internet access.
            token (str, optional): PeeringDB read-only token.

        """
        self.session = http_session(".".join((self.__module__, self.__class__.__name__)))
        if token:
            self.session.headers.update({"Authorization": f"Api-Key {token}"})

        if proxies:
            self.session.proxies = proxies

        self.ttl = ttl
        self.use_cache = cachedir is not None and self.ttl > 0

        self.cachedir: Path
        if cachedir is not None:
            self.cachedir = cast(Path, cachedir)
            self.cachedir.mkdir(exist_ok=True)

    @staticmethod
    def _get_cache_key(resource: str, *, resource_id: Optional[int] = None, filters: Optional[Dict] = None) -> str:
        """Return a cache key based on the resource requested.

        Arguments:
            resource (str): The PeeringDB resource requested
            resource_id (int): Optional resource number
            filters (dict): A dictionary of addtional filter parameters

        Returns:
            str: a path like string encoding all the arguments

        """
        if resource_id is None and filters is None:
            return f"{resource}/index"
        if filters is None:
            return f"{resource}/{str(resource_id)}"
        filter_key = "/".join("/".join([k, str(v)]) for k, v in filters.items())
        if resource_id is None:
            return f"{resource}/{filter_key}"
        return f"{resource}/{str(resource_id)}/{filter_key}"

    def fetch_asn(self, asn: int) -> Dict:
        """Fetch a specific asn.

        Arguments:
            asn (int): The Autonomous system number

        Returns
            dict: A dictionary representing the data

        """
        return self.fetch("net", filters={"asn": asn, "depth": 2})

    def fetch(self, resource: str, resource_id: Optional[int] = None, filters: Optional[Dict] = None) -> Dict:
        """Get a PeeringDB resource.

        Arguments:
            resource (str): The PeeringDB resource requested
            resource_id (int): Optional resource number
            filters (dict): A dictionary of addtional filter parameters

        Returns
            dict: A dictionary representing the data

        """
        if resource_id is None:
            endpoint = resource
        else:
            endpoint = f"{resource}/{str(resource_id)}"

        cache_key = self._get_cache_key(resource=resource, resource_id=resource_id, filters=filters)
        try:
            json_response = self._cache_get(cache_key)
        except CacheMiss as e:
            url = self.baseurl + endpoint
            logging.debug("Fetching %s from PeeringDB (params: %s)", url, filters)
            raw_response = self.session.get(url, params=filters)
            if not raw_response.ok:
                raise PeeringDBError(
                    f"Server response with status {raw_response.status_code}" f" ({raw_response.text})"
                ) from e
            json_response = raw_response.json()
            self._cache_put(json_response, cache_key)
        return json_response["data"]

    def _cache_get(self, cache_key: str) -> dict:
        """Get the resource from the on disk cache if present.

        Arguments:
            cache_key (str): The on-disk path of the resource

        Returns
            dict: A dictionary representing the data

        """
        if not self.use_cache:
            raise CacheMiss()

        cachefile = self.cachedir / cache_key
        try:
            mtime = cachefile.stat().st_mtime
            age = time.time() - mtime
            if age > self.ttl:
                raise CacheMiss()
            return json.loads(cachefile.read_text())

        except OSError as e:
            raise CacheMiss() from e

    def _cache_put(self, content: Dict, cache_key: str) -> None:
        """Write the resource to the on disk cache if configured to do so.

        Arguments:
            content (dict): Dictionary of data to cache
            cache_key (str): The on-disk path of the resource

        """
        if not self.use_cache:
            return

        cachefile = self.cachedir / cache_key
        cachefile.parent.mkdir(exist_ok=True, parents=True)
        cachefile.write_text(json.dumps(content, indent=2))
