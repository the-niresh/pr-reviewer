"""Order file reads by commit time for live review."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class CommitFileTouch:
    committed_at: datetime
    sha: str
    paths: tuple[str, ...]


def assert_commits_in_time_order(commits: Sequence[CommitFileTouch]) -> None:
    for previous, current in zip(commits, commits[1:], strict=False):
        if current.committed_at < previous.committed_at:
            raise ValueError("commits must be in commit-time order")


def ordered_file_reads(commits: Sequence[CommitFileTouch]) -> tuple[str, ...]:
    """Return each path once, in the order it first appears across commits."""
    assert_commits_in_time_order(commits)
    seen: set[str] = set()
    ordered: list[str] = []
    for commit in commits:
        for path in commit.paths:
            if path in seen:
                continue
            seen.add(path)
            ordered.append(path)
    return tuple(ordered)


def order_files_by_commit_time(
    commits: Sequence[CommitFileTouch],
    files: Iterable[str],
) -> tuple[str, ...]:
    """Keep only the requested files while preserving commit-time read order."""
    requested = set(files)
    return tuple(path for path in ordered_file_reads(commits) if path in requested)
