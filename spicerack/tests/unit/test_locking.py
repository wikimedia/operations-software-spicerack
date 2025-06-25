"""locking module tests."""

import json
import logging
import re
import uuid
from datetime import datetime, timedelta
from unittest import mock

import pytest

from spicerack import locking
from spicerack.tests import get_fixture_path

CREATED_DATETIME = datetime(2023, 1, 1, 12, 34, 56, 123456)
CONCURRENT_LOCK_ARGS = {"concurrency": 2, "owner": "user@host [123]", "ttl": 60}
SAMPLE_UUID = "4734a179-0062-436d-a9d5-4cf0c24a12d7"
KEY_LOCKS_JSON = f"""
{{
    "{SAMPLE_UUID}": {{
        "concurrency": 2, "created": "2023-01-01 12:34:56.123456", "owner": "user@host [123]", "ttl": 60
        }}
}}
"""


@pytest.mark.parametrize("stem", ("config", "non-existent"))
def test_get_lock_instance(stem, monkeypatch):
    """It should return a Lock instance."""
    monkeypatch.setenv("USER", "")
    config_file = get_fixture_path("locking", "config.yaml")
    with mock.patch("spicerack.locking.Path") as mocked_path:
        mocked_path.return_value = config_file.with_stem(stem)
        lock = locking.get_lock_instance(
            config_file=config_file,
            prefix="cookbooks",
            owner="user@host [123]",
            dry_run=False,
        )
        mocked_path.assert_called_once_with("~/.etcdrc")

    assert isinstance(lock, locking.Lock)


def test_get_lock_instance_dry_run():
    """It should return a NoLock instance."""
    lock = locking.get_lock_instance(config_file=None, prefix="modules", owner="user@host [123]", dry_run=True)
    assert isinstance(lock, locking.NoLock)


def test_get_lock_instance_invalid_prefix():
    """It should raise a LockError exception if the prefix is invalid."""
    with pytest.raises(locking.LockError, match="Invalid prefix invalid, must be one of:"):
        locking.get_lock_instance(config_file=None, prefix="invalid", owner="user@host [123]", dry_run=True)


class TestLock:
    """Test the Lock class."""

    # Adding an additional mock here for Lock or trying to mock the whole etcd module doens't work as expected
    @mock.patch("spicerack.locking.etcd.Client", autospec=True)
    def setup_method(self, _, mocked_client):
        """Initialize the test environment."""
        # pylint: disable=attribute-defined-outside-init
        self.mocked_client = mocked_client.return_value
        self.mocked_client.read_timeout = 10
        self.full_key = "/spicerack/locks/cookbooks/key"
        self.lock = locking.Lock(config={}, prefix="cookbooks", owner="user@host [123]", dry_run=False)
        self.lock_dry_run = locking.Lock(config={}, prefix="modules", owner="user@host [123]", dry_run=True)
        self.mocked_client.reset_mock()

    def test_init_ok(self):
        """It should create an instance of the Lock class."""
        assert isinstance(self.lock, locking.Lock)

    def test_init_fail(self):
        """It should raise a LockError exception if the prefix is not valid."""
        with pytest.raises(locking.LockError, match="Invalid prefix invalid, must be one of"):
            locking.Lock(config={}, prefix="invalid", owner="user@host [123]", dry_run=True)

    def test_get_ok(self):
        """It should return the existing key if present."""
        self.mocked_client.read.return_value.value = KEY_LOCKS_JSON
        obj = self.lock.get("key")
        assert isinstance(obj, locking.KeyLocks)
        assert obj.key == self.full_key
        assert obj.locks[SAMPLE_UUID].concurrency == 2

    def test_get_missing(self):
        """It should return an empty KeyLocks instance if the key is missing."""
        self.mocked_client.read.side_effect = KeyError
        obj = self.lock.get("key")
        assert isinstance(obj, locking.KeyLocks)
        assert obj.key == self.full_key
        assert not obj.locks

    @pytest.mark.parametrize(
        "name, error",
        (
            ("", "The lock name cannot be empty"),
            ("invalid/name", "The lock name cannot contain '/', got: invalid/name"),
            ("key", "Locks with prefix 'modules' must have names starting with 'spicerack.', got: key"),
        ),
    )
    def test_get_invalid_name(self, name, error):
        """It should raise an InvalidLockError exception if the name contains a slash."""
        self.mocked_client.read.return_value.value = KEY_LOCKS_JSON
        with pytest.raises(locking.InvalidLockError, match=re.escape(error)):
            self.lock_dry_run.get(name)

    def test_get_fail(self):
        """It should raise a LockError exception if there is a failure."""
        self.mocked_client.read.side_effect = locking.etcd.EtcdException
        with pytest.raises(locking.LockError, match=f"Failed to get key {self.full_key}"):
            self.lock.get("key")

    @mock.patch("spicerack.locking.etcd.Lock", autospec=True)
    @mock.patch("uuid.uuid4", return_value="b8dfe73c-0d2c-4406-b783-f7118911014f")
    def test_acquired_ok(self, mocked_uuid, mocked_lock, caplog):
        """It should acquire the lock on the backend, give back control and then release it."""
        mocked_lock.return_value.is_acquired = True
        lock_payload = KEY_LOCKS_JSON.replace(SAMPLE_UUID, mocked_uuid())
        type(self.mocked_client.read.return_value).value = mock.PropertyMock(side_effect=[KEY_LOCKS_JSON, lock_payload])
        executed = False
        mocked_uuid.reset_mock()

        with caplog.at_level(logging.INFO):
            with self.lock.acquired("key", concurrency=2, ttl=60):
                executed = True

        mocked_uuid.assert_called_once()
        self.mocked_client.set.assert_called_once()
        self.mocked_client.delete.assert_called_once_with(self.full_key)
        assert self.mocked_client.set.call_args.args[0] == self.full_key
        saved_payload = json.loads(self.mocked_client.set.call_args.args[1])
        assert len(saved_payload) == 1
        assert saved_payload[mocked_uuid()]["concurrency"] == 2
        assert saved_payload[mocked_uuid()]["owner"] == "user@host [123]"
        assert saved_payload[mocked_uuid()]["ttl"] == 60
        assert executed
        assert f"Acquired lock for key {self.full_key}:" in caplog.text
        assert f"Released lock for key {self.full_key}:" in caplog.text

    def test_acquire_dry_run_ok(self, caplog):
        """It should mimic acquiring the lock on the backend without actually writing to it."""
        self.mocked_client.read.return_value.value = KEY_LOCKS_JSON
        with caplog.at_level(logging.INFO):
            self.lock_dry_run.acquire("spicerack.module.name", concurrency=2, ttl=60)

        self.mocked_client.set.assert_not_called()
        assert "Skipping lock acquire/release in DRY-RUN mode" in caplog.text
        assert "/spicerack/locks/modules/spicerack.module.name" in caplog.text

    @mock.patch("spicerack.locking.etcd.Lock", autospec=True)
    def test_acquire_ok(self, mocked_lock, caplog):
        """It should acquire the lock on the backend."""
        mocked_lock.return_value.is_acquired = True
        self.mocked_client.read.return_value.value = KEY_LOCKS_JSON
        with caplog.at_level(logging.INFO):
            lock_id = self.lock.acquire("key", concurrency=2, ttl=60)

        uuid.UUID(lock_id)  # Raises if it's not a valid UUID
        self.mocked_client.set.assert_called_once()
        assert f"Acquired lock for key {self.full_key}:" in caplog.text

    @mock.patch("spicerack.locking.etcd.Lock", autospec=True)
    @mock.patch("time.sleep", return_value=None)
    def test_acquire_fail_release_ok(self, mocked_sleep, mocked_lock, caplog):
        """It should raise a EtcdLockUnavailableError exception if unable to acquire the lock."""
        mocked_lock.return_value.acquire.side_effect = locking.etcd.EtcdException("##FAILED##")
        with caplog.at_level(logging.INFO):
            with pytest.raises(locking.EtcdLockUnavailableError, match="##FAILED##"):
                self.lock.acquire("key", concurrency=2, ttl=60)

        assert mocked_sleep.call_count == 14
        self.mocked_client.set.assert_not_called()
        assert "Acquired lock" not in caplog.text

    @mock.patch("spicerack.locking.etcd.Lock", autospec=True)
    @mock.patch("time.sleep", return_value=None)
    def test_acquire_fail_release_fail(self, mocked_sleep, mocked_lock, caplog):
        """It should raise a EtcdLockUnavailableError exception if unable to acquire the lock and log a warning."""
        mocked_lock.return_value.acquire.side_effect = locking.etcd.EtcdException("##FAILED##")
        mocked_lock.return_value.release.side_effect = locking.etcd.EtcdException("##FAILED_RELEASE##")
        mocked_lock.return_value.path = "##LOCK_PATH##"
        with caplog.at_level(logging.INFO):
            with pytest.raises(locking.EtcdLockUnavailableError, match="##FAILED##"):
                self.lock.acquire("key", concurrency=2, ttl=60)

        assert mocked_sleep.call_count == 14
        self.mocked_client.set.assert_not_called()
        assert "Acquired lock" not in caplog.text
        assert "Failed to release etcd attempted lock queued" in caplog.text
        assert "##FAILED_RELEASE##" in caplog.text

    @mock.patch("spicerack.locking.etcd.Lock", autospec=True)
    @mock.patch("time.sleep", return_value=None)
    def test_acquire_not_acquired_release_ok(self, mocked_sleep, mocked_lock, caplog):
        """It should raise a EtcdLockUnavailableError exception if the lock is already taken."""
        mocked_lock.return_value.is_acquired = False
        with caplog.at_level(logging.INFO):
            with pytest.raises(locking.EtcdLockUnavailableError, match="Lock already taken"):
                self.lock.acquire("key", concurrency=2, ttl=60)

        assert mocked_sleep.call_count == 14
        self.mocked_client.set.assert_not_called()
        assert "Acquired lock" not in caplog.text

    @mock.patch("spicerack.locking.etcd.Lock", autospec=True)
    @mock.patch("time.sleep", return_value=None)
    def test_acquire_not_acquired_release_fail(self, mocked_sleep, mocked_lock, caplog):
        """It should raise a EtcdLockUnavailableError exception if the lock is already taken."""
        mocked_lock.return_value.is_acquired = False
        mocked_lock.return_value.release.side_effect = locking.etcd.EtcdException("##FAILED_RELEASE##")
        mocked_lock.return_value.path = "##LOCK_PATH##"
        with caplog.at_level(logging.INFO):
            with pytest.raises(locking.EtcdLockUnavailableError, match="Lock already taken"):
                self.lock.acquire("key", concurrency=2, ttl=60)

        assert mocked_sleep.call_count == 14
        self.mocked_client.set.assert_not_called()
        assert "Acquired lock" not in caplog.text
        assert "Failed to release etcd lock queued" in caplog.text
        assert "##FAILED_RELEASE##" in caplog.text

    @mock.patch("spicerack.locking.etcd.Lock", autospec=True)
    def test_release_ok(self, mocked_lock, caplog):
        """It should acquire and then delete the lock on the backend."""
        mocked_lock.return_value.is_acquired = True
        self.mocked_client.read.return_value.value = KEY_LOCKS_JSON
        lock_id = self.lock.acquire("key", concurrency=2, ttl=60)
        self.mocked_client.reset_mock()
        self.mocked_client.read.return_value.value = KEY_LOCKS_JSON.replace(SAMPLE_UUID, lock_id)

        with caplog.at_level(logging.INFO):
            self.lock.release("key", lock_id)

        self.mocked_client.delete.assert_called_once_with(self.full_key)
        assert f"Released lock for key {self.full_key}:" in caplog.text

    @mock.patch("spicerack.locking.etcd.Lock", autospec=True)
    def test_release_remaining_ok(self, mocked_lock, caplog):
        """It should acquire and then release the lock on the backend keeping the existing one."""
        locks = json.loads(KEY_LOCKS_JSON)
        locks[SAMPLE_UUID]["created"] = str(datetime.utcnow())
        mocked_lock.return_value.is_acquired = True
        self.mocked_client.read.return_value.value = json.dumps(locks)
        lock_id = self.lock.acquire("key", concurrency=2, ttl=60)
        self.mocked_client.reset_mock()
        locks[lock_id] = locks[SAMPLE_UUID].copy()
        locks[lock_id]["created"] = str(datetime.utcnow())
        self.mocked_client.read.return_value.value = json.dumps(locks)

        with caplog.at_level(logging.INFO):
            self.lock.release("key", lock_id)

        del locks[lock_id]
        self.mocked_client.set.assert_called_once_with(self.full_key, json.dumps(locks))
        assert f"Released lock for key {self.full_key}:" in caplog.text

    @mock.patch("spicerack.locking.etcd.Lock", autospec=True)
    @mock.patch("time.sleep", return_value=None)
    def test_release_fail(self, mocked_sleep, mocked_lock, caplog):
        """It should not raise an exception if the lock release fails."""
        mocked_lock.return_value.is_acquired = False
        with caplog.at_level(logging.ERROR):
            self.lock.release("key", SAMPLE_UUID)

        assert mocked_sleep.call_count == 14
        self.mocked_client.set.assert_not_called()
        assert f"Failed to release lock for key {self.full_key} and ID {SAMPLE_UUID}: Lock already taken" in caplog.text

    @mock.patch("spicerack.locking.etcd.Lock", autospec=True)
    def test_release_missing(self, mocked_lock, caplog):
        """It should not write to the backend if the lock has been already removed."""
        mocked_lock.return_value.is_acquired = True
        self.mocked_client.read.return_value.value = "{}"
        with caplog.at_level(logging.WARNING):
            self.lock.release("key", "missing")

        self.mocked_client.set.assert_not_called()
        assert "Released lock for key" not in caplog.text
        assert (
            f"Lock for key {self.full_key} and ID missing not found. Unable to release it. Was expired?" in caplog.text
        )

    def test_release_dry_run_ok(self, caplog):
        """It should mimic releasing the lock on the backend without actually writing to it."""
        self.mocked_client.read.return_value.value = KEY_LOCKS_JSON
        with caplog.at_level(logging.INFO):
            self.lock_dry_run.release("spicerack.module.name", SAMPLE_UUID)

        self.mocked_client.set.assert_not_called()
        assert "Skipping lock acquire/release in DRY-RUN mode" in caplog.text


class TestNoLock:
    """Test the NoLock class."""

    def setup_method(self):
        """Initialize the test environment."""
        # pylint: disable=attribute-defined-outside-init
        self.lock = locking.NoLock(config={}, prefix="prefix", owner="user@host [123]", dry_run=False)

    def test_get(self):
        """It should return an empty KeyLocks instance."""
        key_locks = self.lock.get("name")
        assert key_locks.key == "name"
        assert not key_locks.locks

    def test_acquired(self):
        """It should just give back control to the user."""
        executed = False
        with self.lock.acquired():
            executed = True

        assert executed

    def test_acquire(self):
        """It should just do nothing and return an empty lock id."""
        lock_id = self.lock.acquire()
        assert lock_id == ""

    def test_release(self):
        """It should just do nothing."""
        self.lock.release("")


class TestKeyLocks:
    """Test the KeyLocks class."""

    def setup_method(self):
        """Initialize the test environment."""
        # pylint: disable=attribute-defined-outside-init
        self.key = "test.key"
        self.lock = locking.KeyLocks(key=self.key)
        self.concurrent_lock = locking.ConcurrentLock(
            uuid=SAMPLE_UUID, created=CREATED_DATETIME, **CONCURRENT_LOCK_ARGS
        )

    def test_from_json_ok(self):
        """It should create a KeyLocks instance from a JSON payload."""
        lock = locking.KeyLocks.from_json(self.key, KEY_LOCKS_JSON)
        assert isinstance(lock, locking.KeyLocks)
        assert lock.key == self.key
        assert lock.locks[SAMPLE_UUID].created == CREATED_DATETIME

    def test_from_json_fail(self):
        """It should raise a LockUnreadableError exception if unable to parse the JSON lock."""
        with pytest.raises(
            locking.LockUnreadableError, match=re.escape(f"Unable to JSON-deserialize the lock for key {self.key}")
        ):
            locking.KeyLocks.from_json(self.key, "invalid")

    def test_to_json_ok(self):
        """It should return the JSON-serialized object as a string."""
        # Prevent the date to get updated
        self.concurrent_lock.update_created = mock.Mock()
        self.lock.add(self.concurrent_lock)
        assert self.lock.to_json() == json.dumps(json.loads(KEY_LOCKS_JSON))  # Removes the pretty printing

    def test_to_json_fail(self):
        """It should raise a LockUnwritableError exception if unable to serialize the object."""
        self.concurrent_lock.uuid = uuid.uuid4()  # Replace it with an instance, not a string
        self.lock.add(self.concurrent_lock)
        with pytest.raises(locking.LockUnwritableError, match="Unable to JSON-serialize the current instance"):
            self.lock.to_json()

    def test_add_ok(self):
        """It should add the concurrent lock to the instance and update its created time."""
        self.lock.add(self.concurrent_lock)
        assert len(self.lock.locks) == 1
        lock = self.lock.locks[SAMPLE_UUID]
        assert lock.created > datetime.utcnow() - timedelta(seconds=10)
        assert lock == self.concurrent_lock

    def test_add_concurrency_already_reached(self):
        """It should raise a LockUnavailableError exception if there are already lock with reached concurrency."""
        lock1 = locking.ConcurrentLock(owner="##1##", concurrency=2, ttl=10)
        lock2 = locking.ConcurrentLock(owner="##2##", concurrency=2, ttl=10)
        self.lock.add(lock1)
        self.lock.add(lock2)
        expected = (
            f"for key {self.key}.\n"
            "There are already 2 concurrent locks and the concurrency allowed is 2:\n"
            f"    {lock1.created}: ##1##\n"
            f"    {lock2.created}: ##2##"
        )
        with pytest.raises(locking.LockUnavailableError, match=re.escape(expected)):
            self.lock.add(locking.ConcurrentLock(owner="##3##", concurrency=5, ttl=10))

    def test_add_removes_expired(self, caplog):
        """It should remove the expired locks if there is any."""
        kwargs = CONCURRENT_LOCK_ARGS.copy()
        kwargs["concurrency"] = 5
        for i in range(4):
            kwargs["owner"] = f"##{i}##"
            lock = locking.ConcurrentLock(**kwargs)
            self.lock.add(lock)

        for lock in self.lock.locks.values():
            lock.created = CREATED_DATETIME

        with caplog.at_level(logging.INFO):
            self.lock.add(locking.ConcurrentLock(**kwargs))

        assert caplog.text.count(f"Releasing expired lock for key {self.key}:") == 4
        for i in range(4):
            assert f"##{i}##" in caplog.text

    def test_add_duplicate_id(self):
        """It should raise a LockExistingError exception if there is already a lock with the same ID."""
        self.lock.add(self.concurrent_lock)
        with pytest.raises(
            locking.LockExistingError,
            match=re.escape(f"for key {self.key}. A lock with the same ID {SAMPLE_UUID} already exists:"),
        ):
            self.lock.add(self.concurrent_lock)

    def test_add_concurrency_reached(self):
        """It should raise a LockUnavailableError exception if there are already concurrency locks."""
        self.lock.add(self.concurrent_lock)
        kwargs = CONCURRENT_LOCK_ARGS.copy()
        kwargs["concurrency"] = 1
        with pytest.raises(
            locking.LockUnavailableError,
            match=re.escape(
                f"for key {self.key}. There are already 1 concurrent locks and a concurrency of 1 was requested"
            ),
        ):
            self.lock.add(locking.ConcurrentLock(**kwargs))

    def test_remove_ok(self):
        """It should remove the concurent lock from the current instance and return it."""
        self.lock.add(self.concurrent_lock)
        lock = self.lock.remove(self.concurrent_lock.uuid)
        assert lock == self.concurrent_lock
        assert not self.lock.locks

    def test_remove_missing(self, caplog):
        """It should return None and log a warning message."""
        self.lock.add(self.concurrent_lock)
        prev_len = len(self.lock.locks)
        with caplog.at_level(logging.WARNING):
            lock = self.lock.remove("non-existent")

        assert prev_len == len(self.lock.locks)
        assert lock is None
        assert f"Lock for key {self.key} and ID non-existent not found. Unable to release it." in caplog.text


class TestConcurrentLock:
    """Test the ConcurrentLock class."""

    def setup_method(self):
        """Initialize the test environment."""
        # pylint: disable=attribute-defined-outside-init
        self.uuid = str(uuid.uuid4())
        self.lock = locking.ConcurrentLock(created=CREATED_DATETIME, **CONCURRENT_LOCK_ARGS)

    @pytest.mark.parametrize(
        "kwargs, message",
        (
            (
                {"concurrency": -1, "owner": "user@host [123]", "ttl": 60},
                "argument 'concurrency' must be a non-negative integer, got -1",
            ),
            (
                {"concurrency": 1, "owner": "user@host [123]", "ttl": 0},
                "argument 'ttl' must be a positive integer, got 0",
            ),
            (
                {
                    "concurrency": 1,
                    "owner": "user@host [123]",
                    "ttl": 60,
                    "created": datetime.utcnow() + timedelta(seconds=60),
                },
                "argument 'created' cannot be in the future",
            ),
        ),
    )
    def test_init_fail(self, kwargs, message):
        """Instantiating a new ConcurrentLock object shuould fail if the parameters are not correct."""
        with pytest.raises(locking.InvalidLockError, match=re.escape(message)):
            locking.ConcurrentLock(**kwargs)

    def test_str(self):
        """Test the string representation of the object."""
        assert (
            str(self.lock)
            == "{'concurrency': 2, 'created': '2023-01-01 12:34:56.123456', 'owner': 'user@host [123]', 'ttl': 60}"
        )

    def test_update_created(self):
        """It should update the created property to now."""
        self.lock.update_created()
        assert self.lock.created >= datetime.utcnow() - timedelta(seconds=10)

    def test_to_dict(self):
        """If should return the dictionary custom representation of the object suitable for the locking backend."""
        assert self.lock.to_dict() == {"created": str(CREATED_DATETIME), **CONCURRENT_LOCK_ARGS}

    def test_from_dict_ok(self):
        """It should create an instance of ConcurrentLock from a dictionary."""
        lock = locking.ConcurrentLock.from_dict(self.uuid, {"created": str(CREATED_DATETIME), **CONCURRENT_LOCK_ARGS})
        assert isinstance(lock, locking.ConcurrentLock)
        assert lock.uuid == self.uuid
        assert lock.created == CREATED_DATETIME

    def test_from_dict_fail(self):
        """It should fail to create an instance of ConcurrentLock from a dictionary if the date cannot be parsed."""
        with pytest.raises(locking.InvalidLockError, match="key 'created' cannot be parsed as a datetime object"):
            locking.ConcurrentLock.from_dict(self.uuid, {"created": "invalid", **CONCURRENT_LOCK_ARGS})
