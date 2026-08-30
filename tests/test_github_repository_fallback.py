"""Failing tests for diff completeness and the runner-side clone fallback (master Task 7).

A missing GitHub patch is never an unchanged file. Each omitted patch carries a closed-set
OmissionReason. The clone that recovers a patch lives in runner/: it downloads private source,
which the hosted plane must never see. RepositoryFetcher is a Protocol only and may live in
github/. Path traversal, clone timeout, and clone size are tested here because an unbounded
hostile clone is a disk-fill, and ../../etc/something is arbitrary file write.

Imports of new modules stay inside test bodies.
"""

from __future__ import annotations

from pathlib import Path

import pytest

BASE_SHA = "a" * 40
HEAD_SHA = "b" * 40


def _identity():
    from pr_reviewer.contracts.github import RepositoryIdentity

    return RepositoryIdentity(
        installation_id=7202,
        repository_id=82002,
        owner="acme",
        name="widgets",
    )


def _snapshot(files: list[object]) -> object:
    from pr_reviewer.github.pull_request import PullRequestSnapshot

    identity = _identity()
    return PullRequestSnapshot(
        identity=identity,
        repo_owner=identity.owner,
        repo_name=identity.name,
        number=12,
        draft=False,
        base_sha=BASE_SHA,
        head_sha=HEAD_SHA,
        title="Add widget",
        body="",
        files=files,
    )


def test_omission_reason_is_a_closed_set_not_free_text() -> None:
    from pr_reviewer.contracts.github import OmissionReason

    values = {item.value for item in OmissionReason}
    assert "patch_omitted_by_github" in values
    assert "patch_truncated_by_github" in values
    assert "binary" in values
    assert "file_size_limit" in values
    assert "clone_timeout" in values
    with pytest.raises((ValueError, KeyError, TypeError)):
        OmissionReason("a stack trace from git clone")


def test_null_patch_is_recorded_as_omitted_not_as_an_empty_file() -> None:
    from pr_reviewer.contracts.github import OmissionReason, RepositoryIdentity
    from pr_reviewer.github.pull_request import PullRequestFile, ensure_complete_diff

    class EmptyFetcher:
        def recover_patch(
            self,
            identity: RepositoryIdentity,
            path: str,
            *,
            base_sha: str,
            head_sha: str,
        ) -> str | None:
            del identity, path, base_sha, head_sha
            return None

    snapshot = _snapshot(
        [PullRequestFile(path="src/a.py", status="modified", patch=None)]
    )
    completed = ensure_complete_diff(snapshot, EmptyFetcher())
    assert completed.files[0].patch != ""
    assert completed.files[0].omission_reason == OmissionReason.PATCH_OMITTED_BY_GITHUB


def test_truncated_patch_keeps_a_distinct_omission_reason() -> None:
    from pr_reviewer.contracts.github import OmissionReason, RepositoryIdentity
    from pr_reviewer.github.pull_request import PullRequestFile, ensure_complete_diff

    class EmptyFetcher:
        def recover_patch(
            self,
            identity: RepositoryIdentity,
            path: str,
            *,
            base_sha: str,
            head_sha: str,
        ) -> str | None:
            del identity, path, base_sha, head_sha
            return None

    snapshot = _snapshot(
        [
            PullRequestFile(
                path="src/a.py",
                status="modified",
                patch="@@ truncated",
                truncated=True,
            )
        ]
    )
    completed = ensure_complete_diff(snapshot, EmptyFetcher())
    assert completed.files[0].omission_reason == OmissionReason.PATCH_TRUNCATED_BY_GITHUB


def test_binary_file_is_omitted_as_binary_not_as_unchanged() -> None:
    from pr_reviewer.contracts.github import OmissionReason, RepositoryIdentity
    from pr_reviewer.github.pull_request import PullRequestFile, ensure_complete_diff

    class EmptyFetcher:
        def recover_patch(
            self,
            identity: RepositoryIdentity,
            path: str,
            *,
            base_sha: str,
            head_sha: str,
        ) -> str | None:
            del identity, path, base_sha, head_sha
            return None

    snapshot = _snapshot(
        [PullRequestFile(path="logo.png", status="added", patch=None, binary=True)]
    )
    completed = ensure_complete_diff(snapshot, EmptyFetcher())
    assert completed.files[0].omission_reason == OmissionReason.BINARY
    assert completed.files[0].patch in (None, "")


def test_clone_implementation_lives_in_runner_not_github() -> None:
    src = Path(__file__).resolve().parent.parent / "src" / "pr_reviewer"
    assert not (src / "github" / "repository_fallback.py").is_file()
    from pr_reviewer.runner.repository_fallback import BoundedCloneFetcher

    assert BoundedCloneFetcher is not None


def test_repository_fetcher_protocol_lives_in_the_shared_github_package() -> None:
    from pr_reviewer.github.pull_request import RepositoryFetcher

    assert hasattr(RepositoryFetcher, "recover_patch")


def test_clone_refuses_path_traversal_outside_the_work_directory(tmp_path: Path) -> None:
    from pr_reviewer.runner.repository_fallback import (
        BoundedCloneFetcher,
        UnsafeRepositoryPath,
    )

    work = tmp_path / "work"
    work.mkdir()
    outside = tmp_path / "etc" / "passwd"
    fetcher = BoundedCloneFetcher()
    with pytest.raises(UnsafeRepositoryPath):
        fetcher.materialize(
            _identity(),
            HEAD_SHA,
            work,
            ["../../etc/passwd"],
        )
    assert not outside.exists()
    leaked = list(tmp_path.rglob("passwd"))
    assert leaked == []


def test_clone_timeout_is_bounded_and_recorded(tmp_path: Path) -> None:
    from pr_reviewer.runner.repository_fallback import (
        CLONE_TIMEOUT_SECONDS,
        BoundedCloneFetcher,
        CloneTimeout,
    )

    assert 0 < CLONE_TIMEOUT_SECONDS <= 120
    fetcher = BoundedCloneFetcher(timeout_seconds=0.01)
    with pytest.raises(CloneTimeout):
        fetcher.materialize(_identity(), HEAD_SHA, tmp_path / "work", ["src/a.py"])


def test_clone_size_limit_is_bounded_and_recorded() -> None:
    from pr_reviewer.runner.repository_fallback import (
        CLONE_SIZE_LIMIT_BYTES,
        BoundedCloneFetcher,
        CloneSizeLimit,
    )

    assert 0 < CLONE_SIZE_LIMIT_BYTES <= 500 * 1024 * 1024
    fetcher = BoundedCloneFetcher(size_limit_bytes=1)
    with pytest.raises(CloneSizeLimit):
        fetcher.recover_patch(
            _identity(),
            "huge.bin",
            base_sha=BASE_SHA,
            head_sha=HEAD_SHA,
        )


def test_clone_depth_is_bounded() -> None:
    from pr_reviewer.runner.repository_fallback import CLONE_DEPTH

    assert 1 <= CLONE_DEPTH <= 50
