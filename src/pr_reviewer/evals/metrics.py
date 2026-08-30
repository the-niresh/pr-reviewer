"""Eval metrics. Both denominators are named. needs_human is a miss, not a pass."""

from __future__ import annotations

from collections.abc import Sequence

from pr_reviewer.evals.match_findings import MatchResult
from pr_reviewer.evals.types import EvalMetrics

_RULE_ARMS = ("retrieval_only", "executable_check_only", "both")


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _case_is_precise(result: MatchResult) -> bool:
    return bool(result.matched) and not result.unmatched_actual and not result.needs_human_match


def _case_is_recalled(result: MatchResult) -> bool:
    return bool(result.matched) and not result.unmatched_expected and not result.needs_human_match


def compute_metrics(
    results: Sequence[MatchResult],
    *,
    reviewed_pr_count: int,
    latency_ms: int = 0,
    cost_usd: float = 0.0,
) -> EvalMetrics:
    true_positives = sum(len(result.matched) for result in results)
    predicted = sum(len(result.matched) + len(result.unmatched_actual) for result in results)
    expected = sum(len(result.matched) + len(result.unmatched_expected) for result in results)
    false_findings = sum(len(result.unmatched_actual) for result in results)
    cases_with_a_finding = sum(
        1 for result in results if result.matched or result.unmatched_actual
    )
    precise_cases = sum(1 for result in results if _case_is_precise(result))
    recalled_cases = sum(1 for result in results if _case_is_recalled(result))
    needs_human_cases = sum(1 for result in results if result.needs_human_match)
    case_count = len(results)
    return EvalMetrics(
        precision_per_finding=_ratio(true_positives, predicted),
        precision_per_case=_ratio(precise_cases, case_count),
        recall_per_finding=_ratio(true_positives, expected),
        recall_per_case=_ratio(recalled_cases, case_count),
        false_findings_per_pr=_ratio(false_findings, reviewed_pr_count),
        selectivity=_ratio(cases_with_a_finding, case_count),
        verified_finding_rate=0.0,
        latency_ms=latency_ms,
        cost_usd=cost_usd,
        needs_human_rate=_ratio(needs_human_cases, case_count),
        reviewed_pr_count=reviewed_pr_count,
        rule_adherence=dict.fromkeys(_RULE_ARMS, 0.0),
    )
