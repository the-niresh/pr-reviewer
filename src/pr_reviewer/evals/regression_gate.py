"""Compare eval reports, score calibration, and flag drift. No model calls."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from pr_reviewer.evals.types import EvalRun


class EvalThresholds(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    min_precision_per_finding: float = Field(ge=0, le=1)
    max_false_findings_per_pr: float = Field(ge=0)
    min_high_value_recall: float = Field(ge=0, le=1)
    max_cost_usd: float = Field(ge=0)
    max_latency_ms: int = Field(ge=0)


@dataclass(frozen=True)
class GateResult:
    passed: bool
    blocked_metrics: tuple[str, ...]


@dataclass(frozen=True)
class CalibrationBucket:
    lower: float
    upper: float
    count: int
    accuracy: float
    mean_confidence: float


@dataclass(frozen=True)
class DriftSnapshot:
    rejection_rate: float
    dispute_rate: float
    no_finding_rate: float
    cost_usd: float
    latency_ms: int
    retrieval_miss_rate: float


def compare_eval_reports(
    candidate: EvalRun,
    baseline: EvalRun,
    thresholds: EvalThresholds,
) -> GateResult:
    blocked: list[str] = []
    cand = candidate.metrics
    base = baseline.metrics
    if (
        cand.precision_per_finding < base.precision_per_finding
        or cand.precision_per_finding < thresholds.min_precision_per_finding
    ):
        blocked.append("precision_per_finding")
    if (
        cand.false_findings_per_pr > base.false_findings_per_pr
        or cand.false_findings_per_pr > thresholds.max_false_findings_per_pr
    ):
        blocked.append("false_findings_per_pr")
    if (
        cand.recall_per_finding < base.recall_per_finding
        or cand.recall_per_finding < thresholds.min_high_value_recall
    ):
        blocked.append("high_value_recall")
    if cand.cost_usd > base.cost_usd or cand.cost_usd > thresholds.max_cost_usd:
        blocked.append("cost_usd")
    if cand.latency_ms > base.latency_ms or cand.latency_ms > thresholds.max_latency_ms:
        blocked.append("latency_ms")
    return GateResult(passed=not blocked, blocked_metrics=tuple(blocked))


def brier_score(predictions: Sequence[tuple[float, bool]]) -> float:
    if not predictions:
        return 0.0
    total = sum((confidence - float(outcome)) ** 2 for confidence, outcome in predictions)
    return total / len(predictions)


def calibration_buckets(
    predictions: Sequence[tuple[float, bool]],
    *,
    edges: tuple[float, ...] = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0),
) -> tuple[CalibrationBucket, ...]:
    buckets: list[CalibrationBucket] = []
    for index, lower in enumerate(edges[:-1]):
        upper = edges[index + 1]
        if index == len(edges) - 2:
            members = [item for item in predictions if lower <= item[0] <= upper]
        else:
            members = [item for item in predictions if lower <= item[0] < upper]
        if not members:
            continue
        hits = sum(1 for _confidence, outcome in members if outcome)
        mean_confidence = sum(confidence for confidence, _outcome in members) / len(members)
        buckets.append(
            CalibrationBucket(
                lower=lower,
                upper=upper,
                count=len(members),
                accuracy=hits / len(members),
                mean_confidence=mean_confidence,
            )
        )
    return tuple(buckets)


def detect_drift(current: DriftSnapshot, baseline: DriftSnapshot) -> tuple[str, ...]:
    alerts: list[str] = []
    if current.rejection_rate > baseline.rejection_rate:
        alerts.append("rejection_rate")
    if current.dispute_rate > baseline.dispute_rate:
        alerts.append("dispute_rate")
    if current.no_finding_rate > baseline.no_finding_rate:
        alerts.append("no_finding_rate")
    if current.cost_usd > baseline.cost_usd:
        alerts.append("cost_usd")
    if current.latency_ms > baseline.latency_ms:
        alerts.append("latency_ms")
    if current.retrieval_miss_rate > baseline.retrieval_miss_rate:
        alerts.append("retrieval_miss_rate")
    return tuple(alerts)
