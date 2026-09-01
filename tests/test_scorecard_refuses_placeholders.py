"""Proves no number reaches the scorecard without a holdout behind it (Task 31.1)."""

from __future__ import annotations

from pr_reviewer.evals.fixture_reviewer import FixtureReviewer
from pr_reviewer.evals.run_eval import (
    BaselineBlocked,
    load_public_eval_cases,
    run_diff_only_baseline,
)
from pr_reviewer.evals.scorecard import generate_scorecard

_NUMERIC_FIELDS = (
    "precision_per_finding",
    "precision_per_case",
    "recall_per_finding",
    "recall_per_case",
    "false_findings_per_pr",
    "cost_usd",
    "reviewed_pr_count",
)


def test_every_field_is_the_verbatim_refusal_when_the_holdout_is_empty() -> None:
    try:
        run_diff_only_baseline(load_public_eval_cases(), FixtureReviewer.perfect())
    except BaselineBlocked as exc:
        expected_refusal = str(exc)
    else:
        raise AssertionError("the real public dataset must have zero holdout cases right now")

    scorecard = generate_scorecard(FixtureReviewer.perfect())
    for field in _NUMERIC_FIELDS:
        value = getattr(scorecard, field)
        assert isinstance(value, str), f"{field} is {value!r}, not the refusal string"
        assert value == expected_refusal, f"{field} does not match the real BaselineBlocked message"
