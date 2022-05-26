"""Manage updates to automated git repositories."""
import os
from contextlib import contextmanager
from distutils.dir_util import copy_tree
from logging import getLogger
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Generator, Optional

from git import Actor, Repo
from git.exc import GitError
from git.remote import PushInfo
from wmflib.interactive import ask_confirmation

from spicerack.constants import KEYHOLDER_SOCK
from spicerack.exceptions import SpicerackError
from spicerack.remote import RemoteHosts

logger = getLogger(__name__)


class RepoSyncError(SpicerackError):
    """Exception raised for push errors."""


class RepoSyncPushError(RepoSyncError):
    """Exception raised for push errors."""


class RepoSyncNoChangeError(RepoSyncError):
    """Exception raised for push errors."""


class RepoSync:
    """Class for syncing git repos."""

    _data_subdir: str = "data"
    _email: str = "noc@wikimedia.org"

    def __init__(self, repo: Repo, username: str, remote_hosts: RemoteHosts, *, dry_run: bool) -> None:
        """Initialise the object.

        Arguments:
            repo (git.repo.base.Repo): the path to the repo
            username (str): The username making the change
            remote_hosts (spicerack.remote.RemoteHosts): A remotes hosts object
                pointing to all git remote servers.  The servers are expected to
                have a valid KEYHOLDER_SOCK configured
            dry_run (bool): don't preform any write actions

        """
        self._hexsha: Optional[str] = None
        self._username = username
        self._remote_hosts = remote_hosts
        self._dry_run = dry_run
        self._repo = repo
        self._author = Actor(self._username, self._email)

    @property
    def hexsha(self) -> Optional[str]:
        """Returns the hexsha of the last commit."""
        return self._hexsha

    def _commit(self, working_repo: Repo, message: str) -> None:
        """Commit files in working repo.

        Arguments:
            working_repo (git.repo.base.Repo): The working git repo
            message (str): the commit message

        Raises:
            spicerack.reposync.RepoSyncNoChangeError: if no changes detected
            spicerack.reposync.RepoSyncError: If no hexsha returned for commit

        """
        # Don't use working_repo.index.add(".") as it adds the .git folder
        # https://github.com/gitpython-developers/GitPython/issues/292
        working_repo.git.add(A=True)
        if working_repo.head.is_valid() and not working_repo.index.diff(working_repo.head.commit):
            raise RepoSyncNoChangeError("Nothing to commit")
        commit = working_repo.index.commit(message, author=self._author, committer=self._author)
        if not isinstance(commit.hexsha, str):
            raise RepoSyncError("No valid commit hexsha from commit")
        logger.info("Committed changes: %s", commit.hexsha)
        self._hexsha = commit.hexsha

    def _push(self, working_repo: Optional[Repo] = None) -> None:
        """Push the committed changes to the repository's remote.

        Arguments:
            working_repo (git.repo.base.Repo): the repository with the commit to push.

        Raises:
            spicerack.reposync.RepoSyncPushError: if there was an error pushing

        """
        if working_repo is None:
            working_repo = self._repo

        if self._dry_run:
            logger.info("Would have pushed commit")
            return

        old_ssh_auth_sock = os.getenv("SSH_AUTH_SOCK")
        os.environ["SSH_AUTH_SOCK"] = KEYHOLDER_SOCK

        try:  # pylint: disable=too-many-nested-blocks
            for remote in working_repo.remotes:
                logger.debug("Attempt push to: %s", remote)
                try:
                    # TODO: later versions of git python have raise_if_error
                    push_info_list = remote.push()
                    for push_info in push_info_list:
                        msg = f"bitflags {push_info.flags}: {push_info.summary.strip()}"
                        for flag in [
                            PushInfo.REJECTED,
                            PushInfo.REMOTE_REJECTED,
                            PushInfo.REMOTE_FAILURE,
                            PushInfo.ERROR,
                        ]:
                            if push_info.flags & flag:
                                raise RepoSyncPushError(f"Error pushing to {remote}: {msg}")
                # remote.push returns an empty list on error
                except (StopIteration, GitError) as error:
                    raise RepoSyncPushError(f"Error pushing to {remote}: {error}") from error
                logger.info("Pushed to %s", remote)
        finally:
            if old_ssh_auth_sock is None:
                del os.environ["SSH_AUTH_SOCK"]
            else:
                os.environ["SSH_AUTH_SOCK"] = old_ssh_auth_sock

    def _update_local(self, working_dir: Path, message: str) -> None:
        """Update the repo with data from fetch_data.

        Arguments:
            working_dir (pathlib.Path): The temporary directory used to build diffs
            message (str): the commit message

        """
        repo_dir = working_dir / "repo"
        data_dir = working_dir / self._data_subdir
        working_repo = self._repo.clone(repo_dir)
        # Delete all existing files to ensure removal of stale data
        working_repo.git.rm("./", r=True, ignore_unmatch=True)
        # TODO: on python >= 3.8 we can use shutil.copytree with dirs_exist_ok=True
        copy_tree(str(data_dir), str(repo_dir), preserve_symlinks=1)
        self._commit(working_repo, message)
        print(working_repo.git.show(["--color=always", "HEAD"]))
        ask_confirmation(f"Ok to push changes to {self._repo.common_dir}")
        self._push(working_repo)

    def force_sync(self) -> None:
        """Force a sync of the repo on the current host to all remotes."""
        self._push()

    @contextmanager
    def update(self, message: str) -> Generator:
        """Context manager for updating a temporary directory with new data.

        The context manager will create and yield a temporary directory.  Users should populate
        this directory with fresh data to be committed to the main repository.

        Arguments:
            message (str): the commit message

        Yields:
            pathlib.Path: temporary directory to populate with data intended for the git repo

        Raises:
            spicerack.reposync.RepoSyncError: if unable to update local repo

        """
        with TemporaryDirectory() as tmp_dir:
            working_dir = Path(tmp_dir)
            data_dir = working_dir / self._data_subdir
            data_dir.mkdir()
            yield data_dir
            try:
                next(data_dir.iterdir())
            except StopIteration:
                raise RepoSyncError("No data written to data directory") from None
            self._update_local(working_dir, message)
        logger.debug("Push to remotes: %s", self._repo.remotes)
        self._push()
