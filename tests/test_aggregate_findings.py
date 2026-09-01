"""Failing tests for deterministic specialist merge (master Task 19).

Merge key is repository, head SHA, file, overlapping lines, and normalised
category. Order never comes from dict or set iteration. Imports of new
modules stay inside test bodies.
"""

from __future__ import annotations

from collections.abc import Iterator

from pr_reviewer.contracts.finding_candidate import FindingCandidate

REPO = "acme/widgets"
HEAD_SHA = "b" * 40


class _NoIterateSet(set[str]):
    def __iter__(self) -> Iterator[str]:
        raise AssertionError("do not iterate sets to decide merge order")


class _NoIterateMap(dict[str, str]):
    def __iter__(self) -> Iterator[str]:
        raise AssertionError("do not iterate dicts to decide merge order")


def _candidate(**overrides: object) -> FindingCandidate:
    fields: dict[str, object] = {
        "concern": "correctness",
        "severity": "high",
        "category": "null-check",
        "file_path": "src/widget.py",
        "line_start": 10,
        "line_end": 12,
        "title": "Missing null check",
        "rationale": "widget.value can be None.",
        "evidence": ["src/widget.py:10"],
        "confidence": 0.8,
    }
    fields.update(overrides)
    return FindingCandidate.model_validate(fields)


def test_normalise_category_collapses_case_and_separators() -> None:
    from pr_reviewer.reviewer.aggregate_findings import normalise_category

    assert normalise_category("Null Check") == "null-check"
    assert normalise_category("null_check") == "null-check"
    assert normalise_category("null-check") == "null-check"


def test_overlapping_same_category_findings_merge_to_one() -> None:
    from pr_reviewer.reviewer.aggregate_findings import aggregate_findings

    left = _candidate(line_start=10, line_end=14, title="Null A")
    right = _candidate(line_start=12, line_end=16, title="Null B")
    merged = aggregate_findings(
        [right, left],
        repository=REPO,
        head_sha=HEAD_SHA,
    )
    assert len(merged) == 1
    assert merged[0].line_start == 10
    assert merged[0].line_end == 16


def test_non_overlapping_same_category_findings_stay_separate() -> None:
    from pr_reviewer.reviewer.aggregate_findings import aggregate_findings

    first = _candidate(line_start=10, line_end=12, title="First")
    second = _candidate(line_start=40, line_end=42, title="Second")
    merged = aggregate_findings([second, first], repository=REPO, head_sha=HEAD_SHA)
    assert [item.title for item in merged] == ["First", "Second"]


def test_same_overlap_different_category_does_not_merge() -> None:
    from pr_reviewer.reviewer.aggregate_findings import aggregate_findings

    nulls = _candidate(category="null-check", title="Null")
    auth = _candidate(category="authz", title="Auth")
    merged = aggregate_findings([auth, nulls], repository=REPO, head_sha=HEAD_SHA)
    assert [item.title for item in merged] == ["Auth", "Null"]


def test_conflicting_severity_keeps_the_higher_one() -> None:
    from pr_reviewer.reviewer.aggregate_findings import aggregate_findings

    low = _candidate(severity="low", title="Low")
    critical = _candidate(severity="critical", title="Critical")
    merged = aggregate_findings([low, critical], repository=REPO, head_sha=HEAD_SHA)
    assert len(merged) == 1
    assert merged[0].severity == "critical"
    assert merged[0].title == "Critical"


def test_merge_order_is_stable_and_does_not_iterate_sets_or_dicts() -> None:
    from pr_reviewer.reviewer.aggregate_findings import aggregate_findings

    a = _candidate(file_path="src/a.py", title="A", line_start=1, line_end=1)
    b = _candidate(file_path="src/b.py", title="B", line_start=1, line_end=1)
    forbidden_paths = _NoIterateSet({"src/a.py", "src/b.py"})
    forbidden_map = _NoIterateMap({"src/a.py": "A", "src/b.py": "B"})
    forward = aggregate_findings(
        [b, a],
        repository=REPO,
        head_sha=HEAD_SHA,
        forbidden_paths=forbidden_paths,
        forbidden_map=forbidden_map,
    )
    reverse = aggregate_findings(
        [a, b],
        repository=REPO,
        head_sha=HEAD_SHA,
        forbidden_paths=forbidden_paths,
        forbidden_map=forbidden_map,
    )
    assert [item.title for item in forward] == ["A", "B"]
    assert [item.title for item in reverse] == ["A", "B"]


def test_security_concern_survives_merge() -> None:
    from pr_reviewer.reviewer.aggregate_findings import aggregate_findings

    security = _candidate(
        concern="security",
        category="sql-injection",
        title="SQL injection in query builder",
        rationale="user input reaches execute()",
    )
    merged = aggregate_findings([security], repository=REPO, head_sha=HEAD_SHA)
    assert merged[0].concern == "security"
    assert "injection" in merged[0].title.lower()
