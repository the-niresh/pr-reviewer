"""Failing tests for concern-specific specialist reviewers (master Task 19).

Specialists stay off by default. One timeout or a missing agent must not drop
the others. The public holdout comparison is refused, not invented.
Imports of new modules stay inside test bodies.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from pr_reviewer.contracts.finding_candidate import FindingCandidate
from pr_reviewer.github.pull_request import PullRequestFile, PullRequestSnapshot

BASE_SHA = "a" * 40
HEAD_SHA = "b" * 40
SMALL_PATCH = "@@ -1,1 +1,1 @@\n-old\n+new\n"
SPECIALIST_CONCERNS = ("security", "correctness", "tests", "docs")


def _snapshot(files: list[PullRequestFile]) -> PullRequestSnapshot:
    return PullRequestSnapshot(
        repo_owner="acme",
        repo_name="widgets",
        number=12,
        base_sha=BASE_SHA,
        head_sha=HEAD_SHA,
        title="Add widget",
        body="please review",
        files=files,
    )


def _file(path: str, patch: str | None = SMALL_PATCH, **kwargs: object) -> PullRequestFile:
    fields: dict[str, object] = {"path": path, "status": "modified", "patch": patch}
    fields.update(kwargs)
    return PullRequestFile.model_validate(fields)


def _packed(files: list[PullRequestFile]) -> Any:
    from pr_reviewer.contracts.review_context import ContextBudget
    from pr_reviewer.reviewer.diff_budget import pack_diff

    return pack_diff(_snapshot(files), ContextBudget(tokens=10_000), lambda _text: 1)


def _candidate(concern: str, **overrides: object) -> FindingCandidate:
    fields: dict[str, object] = {
        "concern": concern,
        "severity": "high",
        "category": f"{concern}-issue",
        "file_path": "app.py",
        "line_start": 1,
        "line_end": 1,
        "title": f"{concern} finding",
        "rationale": f"{concern} rationale",
        "evidence": ["app.py:1"],
        "confidence": 0.8,
    }
    fields.update(overrides)
    return FindingCandidate.model_validate(fields)


def _reviewer(concern: str, *, calls: dict[str, int] | None = None) -> Any:
    def review(_snapshot: Any, _packed: Any, _context: Any) -> list[FindingCandidate]:
        if calls is not None:
            calls[concern] = calls.get(concern, 0) + 1
        return [_candidate(concern)]

    return review


def test_specialist_mode_is_disabled_on_the_default_policy() -> None:
    from pr_reviewer.reviewer.specialists import specialists_enabled
    from pr_reviewer.security.instruction_sources import default_review_policy

    assert specialists_enabled(default_review_policy()) is False


def test_disabled_specialists_are_not_called() -> None:
    from pr_reviewer.reviewer.specialists import run_specialists
    from pr_reviewer.security.instruction_sources import default_review_policy

    calls: dict[str, int] = {}
    reviewers = {concern: _reviewer(concern, calls=calls) for concern in SPECIALIST_CONCERNS}
    result = run_specialists(
        _snapshot([_file("app.py")]),
        _packed([_file("app.py")]),
        [],
        reviewers,
        policy=default_review_policy(),
    )
    assert result.candidates == ()
    assert calls == {}


def test_enabled_specialists_run_all_four_concerns() -> None:
    from pr_reviewer.reviewer.specialists import run_specialists
    from pr_reviewer.security.instruction_sources import ReviewPolicy

    calls: dict[str, int] = {}
    reviewers = {concern: _reviewer(concern, calls=calls) for concern in SPECIALIST_CONCERNS}
    result = run_specialists(
        _snapshot([_file("app.py")]),
        _packed([_file("app.py")]),
        [],
        reviewers,
        policy=ReviewPolicy(specialist_mode=True),
    )
    assert set(calls) == set(SPECIALIST_CONCERNS)
    assert {item.concern for item in result.candidates} == set(SPECIALIST_CONCERNS)


def test_missing_agent_does_not_drop_the_others() -> None:
    from pr_reviewer.reviewer.specialists import run_specialists
    from pr_reviewer.security.instruction_sources import ReviewPolicy

    reviewers = {
        "security": _reviewer("security"),
        "correctness": _reviewer("correctness"),
        "docs": _reviewer("docs"),
    }
    result = run_specialists(
        _snapshot([_file("app.py")]),
        _packed([_file("app.py")]),
        [],
        reviewers,
        policy=ReviewPolicy(specialist_mode=True),
    )
    assert "tests" in result.missing_concerns
    assert {item.concern for item in result.candidates} == {
        "security",
        "correctness",
        "docs",
    }


def test_partial_specialist_timeout_keeps_finished_findings() -> None:
    from pr_reviewer.reviewer.specialists import SpecialistTimeout, run_specialists
    from pr_reviewer.security.instruction_sources import ReviewPolicy

    def boom(_snapshot: Any, _packed: Any, _context: Any) -> list[FindingCandidate]:
        raise SpecialistTimeout("security")

    reviewers = {
        "security": boom,
        "correctness": _reviewer("correctness"),
        "tests": _reviewer("tests"),
        "docs": _reviewer("docs"),
    }
    result = run_specialists(
        _snapshot([_file("app.py")]),
        _packed([_file("app.py")]),
        [],
        reviewers,
        policy=ReviewPolicy(specialist_mode=True),
    )
    assert result.timed_out_concerns == ("security",)
    assert {item.concern for item in result.candidates} == {
        "correctness",
        "tests",
        "docs",
    }


def test_security_specialist_cannot_set_system_owned_fields() -> None:
    from pydantic import ValidationError

    from pr_reviewer.contracts.finding_candidate import FindingDraft

    with pytest.raises(ValidationError):
        FindingDraft.model_validate(
            {
                "concern": "security",
                "severity": "critical",
                "category": "sql-injection",
                "file_path": "app.py",
                "line_start": 1,
                "line_end": 1,
                "title": "SQL injection exploit payload",
                "rationale": "UNION SELECT password",
                "evidence": ["app.py:1"],
                "confidence": 0.9,
                "public_safe": True,
                "status": "posted",
            }
        )


def test_duplicate_specialist_findings_merge() -> None:
    from pr_reviewer.reviewer.specialists import run_specialists
    from pr_reviewer.security.instruction_sources import ReviewPolicy

    dup = _candidate("correctness", title="Dup A")
    other = _candidate("correctness", title="Dup B")

    reviewers = {
        "security": lambda _s, _p, _c: [dup],
        "correctness": lambda _s, _p, _c: [other],
        "tests": lambda _s, _p, _c: [],
        "docs": lambda _s, _p, _c: [],
    }
    result = run_specialists(
        _snapshot([_file("app.py")]),
        _packed([_file("app.py")]),
        [],
        reviewers,
        policy=ReviewPolicy(specialist_mode=True),
    )
    assert len(result.candidates) == 1


def test_specialist_comparison_is_blocked_on_the_public_dataset() -> None:
    from pr_reviewer.evals.fixture_reviewer import FixtureReviewer
    from pr_reviewer.evals.run_eval import (
        BaselineBlocked,
        load_public_eval_cases,
        run_specialist_comparison,
    )

    with pytest.raises(BaselineBlocked, match="holdout"):
        run_specialist_comparison(
            load_public_eval_cases(),
            FixtureReviewer.perfect(),
            FixtureReviewer.perfect(),
        )


def test_specialist_comparison_runs_both_paths_on_a_synthetic_holdout() -> None:
    from pr_reviewer.evals.fixture_reviewer import FixtureReviewer
    from pr_reviewer.evals.run_eval import run_specialist_comparison, useful_findings_per_dollar
    from pr_reviewer.evals.types import EvalCase, EvalLabel

    case = EvalCase(
        id="holdout-1",
        split="holdout",
        diff="@@ -1 +1 @@\n+value = widget.value\n",
        expected_labels=[
            EvalLabel(
                concern="correctness",
                category="null-check",
                file_path="src/widget.py",
                line_start=10,
                line_end=12,
            )
        ],
        source_evidence=["fix null check"],
        human_auditor="niresh",
        committed_at=date(2024, 6, 1),
    )
    one_agent, specialists = run_specialist_comparison(
        [case],
        FixtureReviewer.perfect(),
        FixtureReviewer.perfect(),
    )
    assert one_agent.metrics.precision_per_finding == 1.0
    assert specialists.metrics.precision_per_finding == 1.0
    assert one_agent.metrics.false_findings_per_pr == 0.0
    assert specialists.metrics.latency_ms >= 0
    assert specialists.metrics.cost_usd >= 0
    assert useful_findings_per_dollar(specialists) >= 0.0
