"""Run an injected reviewer over cases. No model HTTP client lives here."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from pr_reviewer.evals.match_findings import MatchResult, match_findings
from pr_reviewer.evals.metrics import compute_metrics
from pr_reviewer.evals.types import EvalCase, EvalConfig, EvalRun, ReviewerCallable

_PUBLIC_CASES = (
    Path(__file__).resolve().parents[3] / "datasets" / "public" / "eval_cases.jsonl"
)


class BaselineBlocked(Exception):
    """Holdout is empty. Refusing to publish a baseline number."""


def load_public_eval_cases(path: Path | None = None) -> list[EvalCase]:
    target = path or _PUBLIC_CASES
    cases: list[EvalCase] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        if line.strip():
            cases.append(EvalCase.model_validate_json(line))
    return cases


def run_eval(config: EvalConfig, reviewer: ReviewerCallable) -> EvalRun:
    results: list[MatchResult] = []
    for _ in range(config.repeats):
        for case in config.cases:
            actual = list(reviewer(case))
            results.append(match_findings(case.expected_labels, actual))
    metrics = compute_metrics(results, reviewed_pr_count=len(results))
    return EvalRun(metrics=metrics)


def run_diff_only_baseline(
    cases: Sequence[EvalCase],
    reviewer: ReviewerCallable,
    repeats: int = 3,
) -> EvalRun:
    holdout = [case for case in cases if case.split == "holdout"]
    if not holdout:
        raise BaselineBlocked("holdout is empty; refusing to report a baseline")
    return run_eval(EvalConfig(cases=list(holdout), repeats=repeats), reviewer)


def run_retrieval_comparison(
    cases: Sequence[EvalCase],
    without_retrieval: ReviewerCallable,
    with_retrieval: ReviewerCallable,
    repeats: int = 3,
) -> tuple[EvalRun, EvalRun]:
    holdout = [case for case in cases if case.split == "holdout"]
    if not holdout:
        raise BaselineBlocked(
            "holdout is empty; refusing to report a retrieval comparison"
        )
    config = EvalConfig(cases=list(holdout), repeats=repeats)
    return run_eval(config, without_retrieval), run_eval(config, with_retrieval)


def run_context_source_comparison(
    cases: Sequence[EvalCase],
    profile_only: ReviewerCallable,
    graph_only: ReviewerCallable,
    profile_plus_graph: ReviewerCallable,
    repeats: int = 3,
) -> tuple[EvalRun, EvalRun, EvalRun]:
    holdout = [case for case in cases if case.split == "holdout"]
    if not holdout:
        raise BaselineBlocked(
            "holdout is empty; refusing to report a context-source comparison"
        )
    config = EvalConfig(cases=list(holdout), repeats=repeats)
    return (
        run_eval(config, profile_only),
        run_eval(config, graph_only),
        run_eval(config, profile_plus_graph),
    )


def run_specialist_comparison(
    cases: Sequence[EvalCase],
    one_agent: ReviewerCallable,
    specialists: ReviewerCallable,
    repeats: int = 3,
) -> tuple[EvalRun, EvalRun]:
    holdout = [case for case in cases if case.split == "holdout"]
    if not holdout:
        raise BaselineBlocked(
            "holdout is empty; refusing to report a specialist comparison"
        )
    config = EvalConfig(cases=list(holdout), repeats=repeats)
    return run_eval(config, one_agent), run_eval(config, specialists)


def useful_findings_per_dollar(run: EvalRun) -> float:
    if run.metrics.cost_usd <= 0:
        return 0.0
    useful = run.metrics.precision_per_finding * run.metrics.reviewed_pr_count
    return useful / run.metrics.cost_usd
