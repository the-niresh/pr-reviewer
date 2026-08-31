"""Static checks on a finding candidate before any sandbox runs."""

from __future__ import annotations

import re

from pr_reviewer.contracts.finding_candidate import FindingCandidate
from pr_reviewer.github.pull_request import PullRequestSnapshot
from pr_reviewer.verification.docker_sandbox import VerificationResult

_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def check_static(
    candidate: FindingCandidate,
    snapshot: PullRequestSnapshot,
    *,
    required_head_sha: str,
) -> VerificationResult:
    if not all(item.strip() for item in candidate.evidence):
        return VerificationResult(
            status="failed",
            method="static",
            route_to_human=True,
            detail="evidence text is blank",
        )
    if snapshot.head_sha != required_head_sha:
        return VerificationResult(
            status="inconclusive",
            method="static",
            route_to_human=True,
            detail="head sha is stale",
        )
    files = {item.path: item for item in snapshot.files}
    if candidate.file_path not in files:
        return VerificationResult(
            status="failed",
            method="static",
            route_to_human=True,
            detail=f"file {candidate.file_path} is not in the snapshot",
        )
    patch = files[candidate.file_path].patch
    changed = _new_side_lines(patch or "")
    finding_lines = set(range(candidate.line_start, candidate.line_end + 1))
    if not finding_lines & changed:
        return VerificationResult(
            status="failed",
            method="static",
            route_to_human=True,
            detail="finding lines are not in the changed hunks",
        )
    return VerificationResult(
        status="passed",
        method="static",
        route_to_human=False,
        detail="static checks passed",
    )


def _new_side_lines(patch: str) -> set[int]:
    lines: set[int] = set()
    new_no: int | None = None
    for raw in patch.splitlines():
        header = _HUNK_HEADER.match(raw)
        if header is not None:
            new_no = int(header.group(3))
            continue
        if new_no is None or raw.startswith("\\") or raw == "":
            continue
        mark = raw[0]
        if mark in {" ", "+"}:
            lines.add(new_no)
            new_no += 1
    return lines
