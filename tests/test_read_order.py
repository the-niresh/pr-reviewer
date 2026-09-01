"""Agents read changed files in commit-time order."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pr_reviewer.reviewer.read_order import (
    CommitFileTouch,
    assert_commits_in_time_order,
    order_files_by_commit_time,
    ordered_file_reads,
)

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
T1 = datetime(2026, 1, 1, 13, 0, tzinfo=UTC)
T2 = datetime(2026, 1, 1, 14, 0, tzinfo=UTC)


def _touch(
    when: datetime,
    sha: str,
    *paths: str,
) -> CommitFileTouch:
    return CommitFileTouch(committed_at=when, sha=sha, paths=paths)


def test_ordered_file_reads_follows_commit_time() -> None:
    commits = (
        _touch(T0, "aaa", "app.py", "lib/util.py"),
        _touch(T1, "bbb", "README.md"),
        _touch(T2, "ccc", "app.py", "tests/test_app.py"),
    )

    assert ordered_file_reads(commits) == (
        "app.py",
        "lib/util.py",
        "README.md",
        "tests/test_app.py",
    )


def test_order_files_by_commit_time_filters_without_reordering() -> None:
    commits = (
        _touch(T0, "aaa", "app.py", "lib/util.py"),
        _touch(T1, "bbb", "README.md"),
        _touch(T2, "ccc", "tests/test_app.py"),
    )

    assert order_files_by_commit_time(commits, ["README.md", "app.py"]) == (
        "app.py",
        "README.md",
    )


def test_assert_commits_in_time_order_rejects_out_of_order_input() -> None:
    commits = (
        _touch(T1, "bbb", "README.md"),
        _touch(T0, "aaa", "app.py"),
    )

    with pytest.raises(ValueError, match="commit-time order"):
        assert_commits_in_time_order(commits)


def test_ordered_file_reads_rejects_unsorted_commits() -> None:
    commits = (
        _touch(T1, "bbb", "README.md"),
        _touch(T0, "aaa", "app.py"),
    )

    with pytest.raises(ValueError, match="commit-time order"):
        ordered_file_reads(commits)
