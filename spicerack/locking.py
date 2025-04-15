"""Module to manage distributed locks."""

from __future__ import annotations

import json
import logging
import os
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator, Optional, Union

import etcd
from wmflib.config import load_yaml_config

from spicerack.decorators import retry
from spicerack.exceptions import SpicerackCheckError, SpicerackError

logger = logging.getLogger(__name__)
KEYS_BASE_PATH: str = "/spicerack/locks"
"""The base path for the lock keys."""
COOKBOOKS_PREFIX: str = "cookbooks"
"""The path prefix to use for the key of locks acquired by spicerack for each cookbook execution."""
COOKBOOKS_CUSTOM_PREFIX: str = "custom"
"""The path prefix to use for the key of locks acquired from inside a cookbook."""
SPICERACK_PREFIX: str = "modules"
"""The path prefix to use for the key of locks acquired from inside spicerack modules."""
ALLOWED_PREFIXES: tuple[str, ...] = (COOKBOOKS_PREFIX, COOKBOOKS_CUSTOM_PREFIX, SPICERACK_PREFIX)
"""The allowed values for the prefix parameter to be used as path prefix for the locks keys."""
ETCD_WRITER_LOCK_KEY: str = "etcd"
"""The path prefix of the short-term keys to acquire an exclusive lock to write to etcd."""


def get_lock_instance(
    *, config_file: Optional[Path], prefix: str, owner: str, dry_run: bool = True
) -> Union[Lock, NoLock]:
    """Get a lock instance based on the configuration file and prefix.

    Arguments:
        config_file: the path to the configuration file for the locking backend or :py:data:`None` to disable the
            locking support and return a :py:class:`spicerack.locking.NoLock` instance. When the configuration file is
            present a :py:class:`spicerack.locking.Lock` instance is returned instead. The configuration is also
            automatically merged with the ``~/.etcdrc`` config file of the running user, if present.
        prefix: the name of the directory to use to prefix the lock. Must be one of
            :py:const:`spicerack.locking.ALLOWED_PREFIXES`.
        owner: a way to identify the owner of the lock, usually in the form ``{user}@{hostname} [{pid}]``.
        dry_run: whether this is a DRY-RUN.

    Raises:
        spicerack.locking.LockError: if the provided prefix is not one of the allowed ones.

    Returns:
        The locking instance or a dummy instance that has the same API of the locking one but does nothing if the
        config_file.

    """
    if prefix not in ALLOWED_PREFIXES:
        raise LockError(f"Invalid prefix {prefix}, must be one of: {ALLOWED_PREFIXES}")

    if config_file is not None:
        user = os.environ.get("USER", "")
        config = load_yaml_config(config_file)
        config.update(load_yaml_config(Path(f"~{user}/.etcdrc").expanduser(), raises=False))
        return Lock(prefix=prefix, config=config, owner=owner, dry_run=dry_run)

    return NoLock()


class LockError(SpicerackError):
    """Generic exception for errors of this module."""


class InvalidLockError(LockError):
    """Exception raised when the parameters for a lock are invalid."""


class LockUnreadableError(LockError):
    """Exception raised when unable to properly parse an existing lock from the backend."""


class LockUnwritableError(LockError):
    """Exception raised when unable to properly serialize the lock in order to save it in the backend."""


class LockExistingError(LockError):
    """Exception raised if a lock with the same ID already exists for the given key."""


class EtcdLockUnavailableError(SpicerackCheckError):
    """Exception raised when unable to acquire the etcd lock, the operation should be retried."""


class LockUnavailableError(SpicerackCheckError):
    """Exception raised when unable to acquire the Spicerack lock, the operation should be retried."""


class Lock:
    """Manage a Spicerack lock.

    Example object created in the backend (etcd)::

        '/spicerack/locks/cookbooks/sre.foo.bar' => {
            '4e2677c7-541a-4f9e-afbb-cfdb69c440a1': {
                'created': '2023-07-16 16:46:52.161053',
                'owner': 'user@host [12345]',
                'concurrency': 5,
                'ttl': 120,
            }
        }

    """

    def __init__(self, *, config: dict, prefix: str, owner: str, dry_run: bool = True) -> None:
        """Initialize the instance.

        Arguments:
            config: the etcd configuration dictionary to be passed to the etcd client.
            prefix: the name of the directory to use to prefix the lock. Must be one of
                :py:const:`spicerack.locking.ALLOWED_PREFIXES`.
            owner: a way to identify the owner of the lock, usually in the form ``{user}@{hostname} [{pid}]``.
            dry_run: whether this is a DRY-RUN.

        Raises:
            spicerack.locking.LockError: if the provided prefix is not one of the allowed ones.

        """
        if prefix not in ALLOWED_PREFIXES:
            raise LockError(f"Invalid prefix {prefix}, must be one of: {ALLOWED_PREFIXES}")

        config["lock_prefix"] = KEYS_BASE_PATH  # Force the lock prefix
        self._etcd = etcd.Client(**config)
        self._owner = owner
        self._prefix = prefix
        self._dry_run = dry_run

    def get(self, name: str) -> KeyLocks:
        """Get the existing locks for the given name. If missing returns a new object with no locks.

        Arguments:
            name: the lock name, cannot contain ``/`` as that's a directory separator in the data structure.

        Raises:
            spicerack.locking.LockError: for any etcd errors beside the key not found one.

        Returns:
            the existing locks for the given name.

        """
        key = self._get_key(name)
        try:
            return KeyLocks.from_json(
                key, self._etcd.read(key, timeout=self._etcd.read_timeout).value  # pylint: disable=no-member
            )
        except (KeyError, etcd.EtcdKeyNotFound):  # Does not exist, create a new one without any locks
            return KeyLocks(key=key)
        except etcd.EtcdException as e:
            raise LockError(f"Failed to get key {key}") from e

    @contextmanager
    def acquired(self, name: str, *, concurrency: int, ttl: int) -> Iterator[None]:
        """Context manager to perform actions while holding a lock for the given name and parameters.

        Examples::

            # Get a lock for a given name allowing to have other 2 concurrent runs in parallel with a TTL of 30 minutes
            with lock.acquired("some.lock.identifier", concurrency=3, ttl=1800):
                # Do something

            # Acquire an exclusive lock for the given name with a TTL of 1 hour
            with lock.acquired("some.lock.identifier", concurrency=1, ttl=1800):
                # Do something

        Arguments:
            name: the lock name, cannot contain ``/`` as that's a directory separator in the data structure.
            concurrency: how many concurrent clients can hold the same lock. If set to zero it means that there is no
                concurrency limit and an infinite number of clients can run concurrently, but they are tracked.
            ttl: the amount of seconds this lock is valid for. All locks that have passed their TTL are considered
                expired and will be automatically removed.

        Yields:
            Nothing, it just gives back control to the client's code while holding the lock.

        """
        lock_id = self.acquire(name, concurrency=concurrency, ttl=ttl)
        try:
            yield
        finally:
            self.release(name, lock_id)

    def acquire(self, name: str, *, concurrency: int, ttl: int) -> str:
        """Acquire a lock for the given name and parameters and return the lock identifier.

        Examples::

            # Get a lock for a given name allowing to have other 2 concurrent runs in parallel with a TTL of 30 minutes
            lock_id = lock.acquire("some.lock.identifier", concurrency=3, ttl=1800)
            # Do something
            lock.release("some.lock.identifier", lock_id)

            # Acquire an exclusive lock for the given name with a TTL of 1 hour
            lock_id = lock.acquire("some.lock.identifier", concurrency=1, ttl=1800)
            # Do something
            lock.release("some.lock.identifier", lock_id)

        Arguments:
            name: the lock name, cannot contain ``/`` as that's a directory separator in the data structure.
            concurrency: how many concurrent clients can hold the same lock. If set to zero it means that there is no
                concurrency limit and an infinite number of clients can run concurrently, but they are tracked.
            ttl: the amount of seconds this lock is valid for. All locks that have passed their TTL are considered
                expired and will be automatically removed.

        Returns:
            the lock unique identifier.

        """
        lock = ConcurrentLock(concurrency=concurrency, owner=self._owner, ttl=ttl)
        logger.debug("Acquiring lock for key %s: %s", name, lock)
        self._acquire_lock(name, lock)

        return lock.uuid

    def release(self, name: str, lock_id: str) -> None:
        """Release the lock identified by the lock ID, best effort. The lock will expire anyway.

        See the documentation for :py:meth:`spicerack.locking.Lock.acquire` for usage examples.

        Arguments:
            name: the lock name, cannot contain ``/`` as that's a directory separator in the data structure.
            lock_id: the ID identifying the lock.

        """
        logger.debug("Releasing lock for key %s with ID %s", name, lock_id)
        try:
            with self._etcd_locked():
                key_lock = self.get(name)
                lock = key_lock.remove(lock_id)
                if lock is not None:
                    self._set(key_lock)
                    logger.info("Released lock for key %s: %s", key_lock.key, lock)

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Failed to release lock for key %s and ID %s: %s", self._get_key(name), lock_id, e)

    @contextmanager
    def _etcd_locked(self) -> Iterator[None]:
        """Perform an action while holding an exclusive write lock to etcd for operations in this module.

        Yields:
            Nothing, it just gives back control to the client's code.

        Raises:
            spicerack.locking.EtcdLockUnavailableError: if unable to acquire the etcd lock.

        """
        if self._dry_run:
            yield
        else:
            etcd_lock = self._acquire_etcd_lock()
            try:
                yield
            finally:
                etcd_lock.release()

    def _get_key(self, name: str) -> str:
        """Return the key to be used for the given lock name.

        Arguments:
            name: the lock name, cannot contain ``/`` as that's a directory separator in the data structure.

        Returns:
            the lock key.

        """
        if not name:
            raise InvalidLockError("The lock name cannot be empty")

        if "/" in name:
            raise InvalidLockError(f"The lock name cannot contain '/', got: {name}")

        if self._prefix == SPICERACK_PREFIX:  # Ensure the key represent a spicerack module
            if not name.startswith("spicerack."):
                raise InvalidLockError(
                    f"Locks with prefix '{SPICERACK_PREFIX}' must have names starting with 'spicerack.', got: {name}"
                )

        return "/".join([KEYS_BASE_PATH, self._prefix, name])

    def _set(self, lock: KeyLocks) -> None:
        """Set the locks for the given key, deletes the key if there are no more locks.

        Arguments:
            lock: the lock instance that represent the locks for a given key.

        """
        if self._dry_run:
            logger.info("Skipping lock acquire/release in DRY-RUN mode")
        else:
            if lock.locks:
                self._etcd.set(lock.key, lock.to_json())
            else:  # No locks present, delete the key to keep etcd clean
                self._etcd.delete(lock.key)

    @retry(  # Retry for 2 minutes
        tries=15,
        delay=timedelta(seconds=1),
        backoff_mode="linear",
        exceptions=(EtcdLockUnavailableError,),
        failure_message="Unable to acquire etcd lock",
    )
    def _acquire_etcd_lock(self) -> etcd.Lock:
        """Acquire the etcd lock to write the Spicerack lock objects.

        Returns:
            the lock object so it can get released after the Spicerack object has been saved.

        Raises:
            spicerack.locking.EtcdLockUnavailableError: if unable to acquire the etcd lock.

        """
        try:
            etcd_lock = etcd.Lock(self._etcd, ETCD_WRITER_LOCK_KEY)
            etcd_lock.acquire(blocking=False, lock_ttl=15)  # If blocking=True blocks forever even if setting timeout=N
        except etcd.EtcdException as e:
            try:  # Best effort to release the object in the lock queue
                etcd_lock.release()
            except etcd.EtcdException as release_exception:
                logger.warning(
                    "Failed to release etcd attempted lock queued in %s with value %s: %s",
                    etcd_lock.path,
                    etcd_lock.uuid,
                    release_exception,
                )

            raise EtcdLockUnavailableError(f"{e}") from e

        if not etcd_lock.is_acquired:
            try:  # Best effort to release the object in the lock queue
                etcd_lock.release()
            except etcd.EtcdException as e:
                logger.warning(
                    "Failed to release etcd lock queued in %s with value %s: %s", etcd_lock.path, etcd_lock.uuid, e
                )

            raise EtcdLockUnavailableError("Lock already taken")

        return etcd_lock

    @retry(  # Retry for more or less half an hour
        tries=27,
        delay=timedelta(seconds=5),
        backoff_mode="linear",
        exceptions=(LockUnavailableError,),
        failure_message="Unable to acquire lock",
    )
    def _acquire_lock(self, name: str, lock: ConcurrentLock) -> None:
        """Try to acquire the spicerack lock in etcd, retrying on failure for some time.

        Arguments:
            name: the lock name, cannot contain ``/`` as that's a directory separator in the data structure.
            lock: the lock to be acquired.

        Raises:
            spicerack.locking.LockUnavailableError: if unable to acquire the etcd lock to write the actual lock.

        """
        with self._etcd_locked():
            key_lock = self.get(name)
            key_lock.add(lock)
            self._set(key_lock)
            logger.info("Acquired lock for key %s: %s", key_lock.key, lock)


class NoLock:
    """A noop locking class that does nothing.

    Has the same APIs of the :py:class:`spicerack.locking.Lock`, to be used when locking support is disabled.

    """

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        """Initialize the instance.

        Arguments:
            *_args: accept any positional arguments that :py:meth:`spicerack.locking.Lock.__init__` accepts.
            **_kwargs: accept any keyword argument that :py:meth:`spicerack.locking.Lock.__init__` accepts.

        """

    def get(self, name: str, *_args: Any, **_kwags: Any) -> KeyLocks:
        """Dummy method that just returns an empty KeyLocks.

        Arguments:
            name: the lock name, cannot contain ``/`` as that's a directory separator in the data structure.
            *_args: accept any positional arguments that :py:meth:`spicerack.locking.Lock.acquire` accepts.
            **_kwargs: accept any keyword argument that :py:meth:`spicerack.locking.Lock.acquire` accepts.

        Returns:
            an empty instance.

        """
        return KeyLocks(key=name)

    @contextmanager
    def acquired(self, *_args: Any, **_kwargs: Any) -> Iterator[None]:
        """Context manager that just yields.

        Arguments:
            *_args: accept any positional arguments that :py:meth:`spicerack.locking.Lock.acquired` accepts.
            **_kwargs: accept any keyword argument that :py:meth:`spicerack.locking.Lock.acquired` accepts.

        Yields:
            Nothing, it just gives back control to the client's code.

        """
        yield

    def acquire(self, *_args: Any, **_kwags: Any) -> str:
        """Dummy method that just returns an empty string.

        Arguments:
            *_args: accept any positional arguments that :py:meth:`spicerack.locking.Lock.acquire` accepts.
            **_kwargs: accept any keyword argument that :py:meth:`spicerack.locking.Lock.acquire` accepts.

        Returns:
            an empty string.

        """
        return ""

    def release(self, *_args: Any, **_kwags: Any) -> None:
        """Dummy method that does nothing.

        Arguments:
            *_args: accept any positional arguments that :py:meth:`spicerack.locking.Lock.release` accepts.
            **_kwargs: accept any keyword argument that :py:meth:`spicerack.locking.Lock.release` accepts.

        """


@dataclass
class KeyLocks:
    """Manage a lock object for a given key with concurrent locks.

    Arguments:
        key: the lock full key path to be used in the backend.
        locks: the concurrent locks for the given key.

    """

    key: str
    locks: dict[str, ConcurrentLock] = field(default_factory=dict)

    @classmethod
    def from_json(cls, key: str, json_str: str) -> KeyLocks:
        """Create an instance of this class from a JSON string.

        Arguments:
            key: the lock full key path to be used in the backend.
            json_str: the JSON serialization of the lock object.

        Returns:
            the lock instance.

        Raises:
            spicerack.locking.LockUnreadableError: if unable to decode the JSON lock.

        """
        try:
            json_obj = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise LockUnreadableError(f"Unable to JSON-deserialize the lock for key {key}, got:\n{json_str}") from e

        locks = {lock_id: ConcurrentLock.from_dict(lock_id, lock_obj) for lock_id, lock_obj in json_obj.items()}
        return cls(key, locks)

    def to_json(self) -> str:
        """Return the JSON serialization of the current instance.

        Returns:
            a string with a JSON-serialized object.

        Raises:
            spicerack.locking.LockUnwritableError: if unable to convert the curent instance to JSON.

        """
        locks = {lock.uuid: lock.to_dict() for lock in self.locks.values()}
        try:
            return json.dumps(locks)
        except TypeError as e:
            raise LockUnwritableError("Unable to JSON-serialize the current instance") from e

    def add(self, lock: ConcurrentLock) -> None:
        """Add the concurrent lock to the lock object if all criteria are met.

        Arguments:
            lock: the concurrent lock to add.

        Raises:
            spicerack.locking.LockUnavailableError: when the max concurrency has been reached and is not possible to
                acquire a lock.
            spicerack.locking.LockExistingError: if a lock with the same ID already exists.

        """
        expired_uuids = []
        min_concurrency_lock = None
        for other_lock in self.locks.values():
            if other_lock.created + timedelta(seconds=other_lock.ttl) < datetime.utcnow():
                expired_uuids.append(other_lock.uuid)
                continue

            if (
                other_lock.concurrency != 0
                and len(self.locks) >= other_lock.concurrency
                and (min_concurrency_lock is None or other_lock.concurrency < min_concurrency_lock.concurrency)
            ):
                min_concurrency_lock = other_lock

        if min_concurrency_lock is not None:
            existing_locks = "\n".join(f"    {lock_obj.created}: {lock_obj.owner}" for lock_obj in self.locks.values())
            raise LockUnavailableError(
                f"{lock} for key {self.key}.\nThere are already {len(self.locks)} concurrent locks and the "
                f"concurrency allowed is {min_concurrency_lock.concurrency}:\n{existing_locks}"
            )

        for expired_uuid in expired_uuids:
            expired_lock = self.locks.pop(expired_uuid)
            logger.info("Releasing expired lock for key %s: %s", self.key, expired_lock)

        if lock.uuid in self.locks:
            raise LockExistingError(
                f"{lock} for key {self.key}. A lock with the same ID {lock.uuid} already exists: "
                f"{self.locks[lock.uuid]}"
            )

        if lock.concurrency != 0 and len(self.locks) >= lock.concurrency:
            raise LockUnavailableError(
                f"{lock} for key {self.key}. There are already {len(self.locks)} concurrent locks and a concurrency "
                f"of {lock.concurrency} was requested."
            )

        lock.update_created()
        self.locks[lock.uuid] = lock

    def remove(self, lock_id: str) -> Optional[ConcurrentLock]:
        """Remove the concurrent lock identified by the lock ID.

        Arguments:
            lock_id: the ID identifying the lock.

        Returns:
            the removed concurrent lock if the lock was found and removed from the instance, it means that the backend
            needs to be updated.
            :py:data:`None` if the concurrent lock was not found and there is no need to update the backend.

        """
        if lock_id in self.locks:
            return self.locks.pop(lock_id)

        logger.warning("Lock for key %s and ID %s not found. Unable to release it. Was expired?", self.key, lock_id)
        return None


@dataclass
class ConcurrentLock:
    """A single concurrent lock object.

    Arguments:
        concurrency: how many concurrent locks can be acquired for the same key. If set to zero it means that there is
            no concurrency limit and an infinite number of clients can run concurrently, but they are tracked.
        ttl: the time to live in seconds of the lock. If expired it will be automatically discarded.
        owner: a way to identify the owner of the lock, usually in the form ``{user}@{hostname} [{pid}]``.
        uuid: the unique identifier of the concurrent lock.
        created: when the lock has been created, used for checking if the TTL has expired.

    """

    concurrency: int
    owner: str
    ttl: int
    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))
    created: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self) -> None:
        """According to Python's dataclass API to validate the arguments.

        See Also:
            https://docs.python.org/3/library/dataclasses.html#post-init-processing

        """
        if self.concurrency < 0:
            raise InvalidLockError(
                "Unable to create concurrent lock, argument 'concurrency' must be a non-negative integer, got "
                f"{self.concurrency}."
            )
        if self.ttl <= 0:
            raise InvalidLockError(
                f"Unable to create concurrent lock, argument 'ttl' must be a positive integer, got {self.ttl}."
            )
        if self.created > datetime.utcnow():
            raise InvalidLockError(
                f"Unable to create concurrent lock, argument 'created' cannot be in the future, got {self.created}."
            )

    def __str__(self) -> str:
        """String representation of the concurrent lock.

        Returns:
            the dictionary representation of the lock object as string.

        """
        return str(self.to_dict())

    def update_created(self) -> None:
        """Update the created time to now."""
        self.created = datetime.utcnow()

    def to_dict(self) -> dict[str, Union[str, int]]:
        """Returns the dict representation of the object suitable for JSON serialization.

        Intentionally not using ``dataclasses.asdict()`` to skip self.uuid and to convert the created datetime to
        string.

        Returns:
            the object as dict with the created datetime converted to string.

        """
        return {"concurrency": self.concurrency, "created": str(self.created), "owner": self.owner, "ttl": self.ttl}

    @classmethod
    def from_dict(cls, lock_id: str, lock_obj: dict[str, Union[str, int]]) -> ConcurrentLock:
        """Get a ConcurrentLock instance from a dict, suitable to be used to JSON deserialize.

        Arguments:
            lock_id: the concurrent lock unique identifier.
            lock_obj: the lock dictionary object.

        Returns:
            a concurrent lock instance.

        Raises:
            spicerack.locking.InvalidLockError: if unable to parse the created datetime.

        """
        params: dict = {**lock_obj}
        params["uuid"] = lock_id
        try:
            params["created"] = datetime.fromisoformat(str(lock_obj["created"]))
        except ValueError as e:
            raise InvalidLockError(
                "Unable to create concurent lock from dict, key 'created' cannot be parsed as a datetime object, "
                f"got {lock_obj['created']}."
            ) from e

        return cls(**params)
