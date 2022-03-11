"""Reposync module tests."""
import os
import random
from unittest import mock

import pytest
from git import Repo
from git.objects.commit import Commit
from git.remote import PushInfo

from spicerack.remote import RemoteHosts
from spicerack.reposync import RepoSync, RepoSyncError, RepoSyncNoChangeError


# pylint: disable=protected-access
class TestReposync:
    """Reposync tests class."""

    @pytest.fixture(autouse=True)
    def setup_method(self, tmp_path):
        """Setup test environment."""
        # pylint: disable=attribute-defined-outside-init
        remote_hosts = mock.MagicMock(spec_set=RemoteHosts)
        repo_dir = tmp_path / "bare_repo"
        self.bare_repo = Repo.init(repo_dir, bare=True)
        self.reposync = RepoSync(self.bare_repo, "user", remote_hosts, dry_run=False)

    def test_init(self):
        """It should be an initialised instance."""
        assert isinstance(self.reposync, RepoSync)

    def test_hexsha(self):
        """Test the hexsha property."""
        assert self.reposync.hexsha is None
        self.reposync._hexsha = "newhexsha"
        assert self.reposync.hexsha == "newhexsha"

    @pytest.mark.parametrize("commit_twice, set_env", ((False, False), (True, False), (False, True)))
    @mock.patch("spicerack.reposync.ask_confirmation")
    def test_update(self, mock_ask_confirmation, commit_twice, set_env, monkeypatch):
        """Test adding some data to the repo."""
        file_content = f"test data: {random.random()}"  # nosec
        if set_env:
            monkeypatch.setenv("SSH_AUTH_SOCK", file_content)
            assert os.environ["SSH_AUTH_SOCK"] == file_content
        with self.reposync.update("test add random data") as working_dir:
            (working_dir / "test_file.txt").write_text(file_content)
        if commit_twice:
            with pytest.raises(RepoSyncNoChangeError):
                with self.reposync.update("test add random data") as working_dir:
                    (working_dir / "test_file.txt").write_text(file_content)
        mock_ask_confirmation.assert_called_once_with(f"Ok to push changes to {self.bare_repo.common_dir}")
        assert not self.bare_repo.is_dirty()
        assert len(list(self.bare_repo.iter_commits())) == 1
        commit = next(self.bare_repo.iter_commits())
        assert commit.author.email == "noc@wikimedia.org"
        assert commit.message == "test add random data"
        # TODO: there must be a better way...
        assert f"+{file_content}" in self.bare_repo.git.show(commit.hexsha).splitlines()
        if set_env:
            monkeypatch.setenv("SSH_AUTH_SOCK", file_content)
            assert os.environ["SSH_AUTH_SOCK"] == file_content
        else:
            assert "SSH_AUTH_SOCK" not in os.environ

    @mock.patch("spicerack.reposync.ask_confirmation")
    def test_update_nochange(self, mock_ask_confirmation):
        """Test adding no data to the repo."""
        with pytest.raises(RepoSyncError):
            with self.reposync.update("test commit"):
                pass
        mock_ask_confirmation.assert_not_called()
        assert not self.bare_repo.is_dirty()
        assert len(self.bare_repo.refs) == 0

    @mock.patch("spicerack.reposync.ask_confirmation")
    def test_update_drydurn(self, mock_ask_confirmation):
        """Test adding some data to the repo."""
        self.reposync._dry_run = True
        file_content = f"test data: {random.random()}"  # nosec
        with self.reposync.update("test add random data") as working_dir:
            (working_dir / "test_file.txt").write_text(file_content)
        mock_ask_confirmation.assert_called_once_with(f"Ok to push changes to {self.bare_repo.common_dir}")
        assert not self.bare_repo.is_dirty()
        assert len(self.bare_repo.refs) == 0

    @mock.patch("spicerack.reposync.ask_confirmation")
    def test_update_bad_push(self, mock_ask_confirmation):
        """Test bad push flags."""
        file_content = f"test data: {random.random()}"  # nosec
        self.reposync._repo.create_remote("bad_remote", "/nonexistent/example.git")
        with pytest.raises(RepoSyncError):
            with self.reposync.update("test add random data") as working_dir:
                (working_dir / "test_file.txt").write_text(file_content)
        mock_ask_confirmation.assert_called_once_with(f"Ok to push changes to {self.bare_repo.common_dir}")

    @mock.patch("git.Remote.push")
    @mock.patch("spicerack.reposync.ask_confirmation")
    def test_update_bad_pushinfo(self, mock_ask_confirmation, mock_push):
        """Test bad push flags."""
        self.reposync._repo.create_remote("bad_remote", "/nonexistent/example.git")
        push_info = mock.MagicMock(spec_set=PushInfo)
        push_info.flags = PushInfo.ERROR
        mock_push.return_value = [push_info]

        file_content = f"test data: {random.random()}"  # nosec
        with pytest.raises(RepoSyncError):
            with self.reposync.update("test add random data") as working_dir:
                (working_dir / "test_file.txt").write_text(file_content)
        mock_ask_confirmation.assert_called_once_with(f"Ok to push changes to {self.bare_repo.common_dir}")

    @mock.patch("spicerack.reposync.RepoSync._push")
    def test_force_sync(self, mock_push):
        """Test force_sync."""
        self.reposync.force_sync()
        mock_push.assert_called_once_with()

    def test_commit_no_hexsha(self):
        """Test push with missmatch sha1."""
        repo = mock.MagicMock(spec_set=Repo)
        commit = mock.MagicMock(spec_set=Commit)
        commit.hexsha = None
        with pytest.raises(RepoSyncError):
            self.reposync._commit(repo, "foobar")
