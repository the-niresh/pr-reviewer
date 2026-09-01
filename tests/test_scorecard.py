"""Scorecard generator (Task 31.1): a real eval run, or the verbatim refusal, never hand-edited."""

from __future__ import annotations

from datetime import date

from pr_reviewer.evals.fixture_reviewer import FixtureReviewer
from pr_reviewer.evals.scorecard import generate_scorecard
from pr_reviewer.evals.types import EvalCase, EvalLabel


def _holdout_case() -> EvalCase:
    return EvalCase(
        id="holdout-1",
        split="holdout",
        diff="--- a/widget.py\n+++ b/widget.py\n@@ -1 +1 @@\n-old\n+new\n",
        expected_labels=[
            EvalLabel(
                concern="correctness",
                category="null-check",
                file_path="widget.py",
                line_start=1,
                line_end=1,
            )
        ],
        source_evidence=["widget.py:1"],
        human_auditor="niresh",
        committed_at=date(2026, 1, 1),
    )


def test_scorecard_is_the_refusal_against_the_real_public_dataset() -> None:
    # datasets/public/eval_cases.jsonl has one dev case and zero holdout, so this is a real
    # eval run hitting the real, currently-empty holdout, not a fabricated scenario.
    scorecard = generate_scorecard(FixtureReviewer.perfect())
    assert scorecard.precision_per_finding == "holdout is empty; refusing to report a baseline"
    assert scorecard.reviewed_pr_count == "holdout is empty; refusing to report a baseline"


def test_scorecard_reports_real_numbers_once_a_holdout_exists() -> None:
    scorecard = generate_scorecard(FixtureReviewer.perfect(), cases=[_holdout_case()], repeats=3)
    assert scorecard.precision_per_finding == 1.0
    assert scorecard.recall_per_finding == 1.0
    assert scorecard.false_findings_per_pr == 0.0
    assert scorecard.reviewed_pr_count == 3
