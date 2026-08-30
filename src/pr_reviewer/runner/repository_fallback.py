"""Bounded shallow-clone fallback for omitted GitHub patches (master Task 7).

A clone downloads the customer's private source tree, so this module lives in runner/,
not github/. control_plane already cannot import runner/, which makes hosted cloning
structurally impossible. Repository access uses an installation token minted by the
Task 4 broker and handed to the runner. This module never imports control_plane and
never touches the GitHub App private key.

Path traversal is checked on the resolved path, before any write. A PR branch can
contain ../../etc/something, an absolute path, or a symlink out of the work directory;
any of those is arbitrary file write on the user's machine. Depth, size, and timeout
are hard bounds: an unbounded clone of a hostile repository fills the disk.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from pr_reviewer.contracts.github import RepositoryIdentity

CLONE_DEPTH = 1
CLONE_TIMEOUT_SECONDS = 60
CLONE_SIZE_LIMIT_BYTES = 100 * 1024 * 1024
_MIN_CLONE_BYTES = 2


class UnsafeRepositoryPath(Exception):
    """A repository path resolved outside the allocated work directory."""


class CloneTimeout(Exception):
    """A clone exceeded the configured time bound."""


class CloneSizeLimit(Exception):
    """A clone or recovered file exceeded the configured size bound."""


class BoundedCloneFetcher:
    """Shallow-clone fallback that stays inside work_dir and inside the three bounds.

    `token` is a GitHub installation access token already minted by the hosted token
    broker. It is optional so tests can exercise path and bound guards without a
    network. Passing the App private key here would be a boundary failure.
    """

    def __init__(
        self,
        *,
        token: str | None = None,
        timeout_seconds: float = CLONE_TIMEOUT_SECONDS,
        size_limit_bytes: int = CLONE_SIZE_LIMIT_BYTES,
        clone_depth: int = CLONE_DEPTH,
        git_executable: str = "git",
    ) -> None:
        self._token = token
        self._timeout_seconds = timeout_seconds
        self._size_limit_bytes = size_limit_bytes
        self._clone_depth = clone_depth
        self._git_executable = git_executable

    def __repr__(self) -> str:
        return (
            "BoundedCloneFetcher("
            f"timeout_seconds={self._timeout_seconds!r}, "
            f"size_limit_bytes={self._size_limit_bytes!r}, "
            f"clone_depth={self._clone_depth!r}, "
            f"token_present={self._token is not None})"
        )

    def materialize(
        self,
        identity: RepositoryIdentity,
        head_sha: str,
        work_dir: Path,
        paths: list[str],
    ) -> Path:
        work_dir.mkdir(parents=True, exist_ok=True)
        work_resolved = work_dir.resolve()
        for relative_path in paths:
            assert_path_stays_inside(work_resolved, relative_path)
        self._assert_size_budget()
        self._clone(identity, work_resolved)
        self._checkout(work_resolved, head_sha)
        self._assert_tree_stays_inside(work_resolved)
        self._assert_directory_within_size(work_resolved)
        for relative_path in paths:
            assert_path_stays_inside(work_resolved, relative_path)
        return work_resolved

    def recover_patch(
        self,
        identity: RepositoryIdentity,
        path: str,
        *,
        base_sha: str,
        head_sha: str,
    ) -> str | None:
        del base_sha
        with TemporaryDirectory() as tmp:
            work = Path(tmp) / "work"
            work.mkdir()
            assert_path_stays_inside(work.resolve(), path)
            self._assert_size_budget()
            self.materialize(identity, head_sha, work, [path])
            target = assert_path_stays_inside(work.resolve(), path)
            if not target.is_file():
                return None
            size = target.stat().st_size
            if size > self._size_limit_bytes:
                raise CloneSizeLimit(f"{path} is {size} bytes, over the clone size limit")
            return target.read_text(encoding="utf-8", errors="replace")

    def _assert_size_budget(self) -> None:
        if self._size_limit_bytes < _MIN_CLONE_BYTES:
            raise CloneSizeLimit("clone size limit cannot fit a repository")

    def _clone(self, identity: RepositoryIdentity, work_dir: Path) -> None:
        url = self._clone_url(identity)
        try:
            self._run_git(
                [
                    "clone",
                    f"--depth={self._clone_depth}",
                    "--",
                    url,
                    str(work_dir),
                ],
                cwd=None,
            )
        except subprocess.TimeoutExpired as error:
            raise CloneTimeout("clone exceeded timeout") from error

    def _checkout(self, work_dir: Path, head_sha: str) -> None:
        try:
            self._run_git(["checkout", head_sha], cwd=work_dir)
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            return

    def _run_git(self, args: list[str], cwd: Path | None) -> None:
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GIT_ASKPASS"] = "echo"
        env["GIT_CONFIG_NOSYSTEM"] = "1"
        if self._token is not None:
            # Keep the token in env, never in argv. TimeoutExpired and
            # CalledProcessError both record cmd, and a URL-embedded token would leak.
            env["GIT_CONFIG_COUNT"] = "1"
            env["GIT_CONFIG_KEY_0"] = "http.extraHeader"
            env["GIT_CONFIG_VALUE_0"] = f"Authorization: Bearer {self._token}"
        subprocess.run(
            [self._git_executable, *args],
            cwd=cwd,
            timeout=self._timeout_seconds,
            check=True,
            capture_output=True,
            env=env,
        )

    def _clone_url(self, identity: RepositoryIdentity) -> str:
        return f"https://github.com/{identity.owner}/{identity.name}.git"

    def _assert_tree_stays_inside(self, work_resolved: Path) -> None:
        for current_root, dir_names, file_names in os.walk(work_resolved, followlinks=False):
            for name in (*dir_names, *file_names):
                path = Path(current_root) / name
                resolved = path.resolve()
                if not _is_inside(work_resolved, resolved):
                    raise UnsafeRepositoryPath(str(path))

    def _assert_directory_within_size(self, root: Path) -> None:
        total = 0
        for path in root.rglob("*"):
            if path.is_symlink() or not path.is_file():
                continue
            total += path.stat().st_size
            if total > self._size_limit_bytes:
                raise CloneSizeLimit("clone exceeded size limit")


def assert_path_stays_inside(work_dir: Path, relative_path: str) -> Path:
    """Resolve relative_path against work_dir and require the result stay inside it.

    The check uses the resolved path, not the literal string, so ../../etc/passwd,
    an absolute path, and a symlink out of the sandbox all fail before any write.
    """
    if "\x00" in relative_path:
        raise UnsafeRepositoryPath(relative_path)
    raw = Path(relative_path)
    if raw.is_absolute() or raw.anchor:
        raise UnsafeRepositoryPath(relative_path)
    work_resolved = work_dir.resolve()
    target = (work_resolved / relative_path).resolve()
    if not _is_inside(work_resolved, target):
        raise UnsafeRepositoryPath(relative_path)
    return target


def _is_inside(parent: Path, child: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True
