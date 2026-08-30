"""Run an injected reviewer over cases. No model HTTP client lives here."""

from __future__ import annotations

from pr_reviewer.evals.match_findings import MatchResult, match_findings
from pr_reviewer.evals.metrics import compute_metrics
from pr_reviewer.evals.types import EvalConfig, EvalRun, ReviewerCallable


def run_eval(config: EvalConfig, reviewer: ReviewerCallable) -> EvalRun:
    results: list[MatchResult] = []
    for _ in range(config.repeats):
        for case in config.cases:
            actual = list(reviewer(case))
            results.append(match_findings(case.expected_labels, actual))
    metrics = compute_metrics(results, reviewed_pr_count=len(results))
    return EvalRun(metrics=metrics)
