"""PeeringDB module."""

import json
import logging
import time
from collections.abc import MutableMapping
from pathlib import Path
from typing import Optional, cast

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

    baseurl: str = "https://www.peeringdb.com/api/"
    """The PeeringDB base API URL."""

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
            ttl: TTL for cached objects.
            cachedir: Root path for objects caching.
            proxies: Proxies for Internet access.
            token: PeeringDB read-only token.

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
    def _get_cache_key(resource: str, *, resource_id: Optional[int] = None, filters: Optional[dict] = None) -> str:
        """Return a cache key based on the resource requested.

        Arguments:
            resource: The PeeringDB resource requested.
            resource_id: Optional resource number.
            filters: A dictionary of addtional filter parameters.

        """
        if resource_id is None and filters is None:
            return f"{resource}/index"
        if filters is None:
            return f"{resource}/{str(resource_id)}"
        filter_key = "/".join("/".join([k, str(v)]) for k, v in filters.items())
        if resource_id is None:
            return f"{resource}/{filter_key}"
        return f"{resource}/{str(resource_id)}/{filter_key}"

    def fetch_asn(self, asn: int) -> dict:
        """Fetch a specific asn data.

        Arguments:
            asn: The Autonomous system number.

        """
        return self.fetch("net", filters={"asn": asn, "depth": 2})

    def fetch(self, resource: str, resource_id: Optional[int] = None, filters: Optional[dict] = None) -> dict:
        """Get a PeeringDB resource.

        Arguments:
            resource: The PeeringDB resource requested.
            resource_id: Optional resource number.
            filters: A dictionary of addtional filter parameters.

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
            cache_key: The on-disk path of the resource.

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

    def _cache_put(self, content: dict, cache_key: str) -> None:
        """Write the resource to the on disk cache if configured to do so.

        Arguments:
            content: Dictionary of data to cache.
            cache_key: The on-disk path of the resource.

        """
        if not self.use_cache:
            return

        cachefile = self.cachedir / cache_key
        cachefile.parent.mkdir(exist_ok=True, parents=True)
        cachefile.write_text(json.dumps(content, indent=2))
