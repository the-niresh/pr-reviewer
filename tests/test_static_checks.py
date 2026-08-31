"""Failing tests for static finding checks (master Task 14).

File existence, changed-line membership, current head SHA, and evidence text.
Imports of new modules stay inside test bodies.
"""

from __future__ import annotations

from pr_reviewer.contracts.finding_candidate import FindingCandidate
from pr_reviewer.github.pull_request import PullRequestFile, PullRequestSnapshot

HEAD = "a" * 40
OTHER = "b" * 40
PATCH = (
    "@@ -1,2 +1,3 @@\n"
    " context\n"
    "+added line\n"
    " keep\n"
)


def _candidate(**overrides: object) -> FindingCandidate:
    fields: dict[str, object] = {
        "concern": "correctness",
        "severity": "medium",
        "category": "null-check",
        "file_path": "src/widget.py",
        "line_start": 2,
        "line_end": 2,
        "title": "Missing null check",
        "rationale": "widget.value can be None.",
        "evidence": ["src/widget.py:2"],
        "confidence": 0.8,
    }
    fields.update(overrides)
    return FindingCandidate.model_validate(fields)


def _snapshot(**overrides: object) -> PullRequestSnapshot:
    fields: dict[str, object] = {
        "repo_owner": "acme",
        "repo_name": "widgets",
        "number": 12,
        "base_sha": "c" * 40,
        "head_sha": HEAD,
        "title": "Add widget",
        "body": "",
        "files": [
            PullRequestFile(path="src/widget.py", status="modified", patch=PATCH),
        ],
    }
    fields.update(overrides)
    return PullRequestSnapshot.model_validate(fields)


def test_file_existence_fails_when_the_path_is_not_in_the_snapshot() -> None:
    from pr_reviewer.verification.static_checks import check_static

    result = check_static(
        _candidate(file_path="src/missing.py"), _snapshot(), required_head_sha=HEAD
    )
    assert result.status == "failed"
    assert result.method == "static"
    assert result.route_to_human is True


def test_changed_line_membership_fails_when_the_line_is_not_in_the_patch() -> None:
    from pr_reviewer.verification.static_checks import check_static

    result = check_static(
        _candidate(line_start=99, line_end=99), _snapshot(), required_head_sha=HEAD
    )
    assert result.status == "failed"
    assert result.method == "static"


def test_changed_line_membership_passes_for_an_added_line() -> None:
    from pr_reviewer.verification.static_checks import check_static

    result = check_static(_candidate(), _snapshot(), required_head_sha=HEAD)
    assert result.status == "passed"
    assert result.method == "static"
    assert result.route_to_human is False


def test_stale_head_sha_is_inconclusive() -> None:
    from pr_reviewer.verification.static_checks import check_static

    result = check_static(_candidate(), _snapshot(), required_head_sha=OTHER)
    assert result.status == "inconclusive"
    assert result.method == "static"
    assert result.route_to_human is True


def test_blank_evidence_text_fails() -> None:
    from pr_reviewer.verification.static_checks import check_static

    result = check_static(_candidate(evidence=["   "]), _snapshot(), required_head_sha=HEAD)
    assert result.status == "failed"
    assert result.method == "static"
