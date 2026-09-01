"""Failing tests for eval regression gates, calibration, and drift (master Task 20).

Gates are tested with synthetic report objects. The public holdout is empty, so
a real baseline number is refused, not invented. Imports of new modules stay
inside test bodies.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

from pr_reviewer.evals.types import EvalMetrics, EvalRun

SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "pr_reviewer"


def _metrics(**overrides: object) -> EvalMetrics:
    fields: dict[str, object] = {
        "precision_per_finding": 0.8,
        "precision_per_case": 0.8,
        "recall_per_finding": 0.7,
        "recall_per_case": 0.7,
        "false_findings_per_pr": 0.2,
        "selectivity": 0.5,
        "verified_finding_rate": 0.0,
        "latency_ms": 100,
        "cost_usd": 0.10,
        "needs_human_rate": 0.1,
        "reviewed_pr_count": 10,
        "rule_adherence": {
            "retrieval_only": 0.0,
            "executable_check_only": 0.0,
            "both": 0.0,
        },
    }
    fields.update(overrides)
    return EvalMetrics.model_validate(fields)


def _run(**overrides: object) -> EvalRun:
    return EvalRun(metrics=_metrics(**overrides))


def _thresholds() -> Any:
    from pr_reviewer.evals.regression_gate import EvalThresholds

    return EvalThresholds(
        min_precision_per_finding=0.7,
        max_false_findings_per_pr=0.4,
        min_high_value_recall=0.5,
        max_cost_usd=0.50,
        max_latency_ms=500,
    )


def test_compare_eval_reports_passes_when_candidate_meets_baseline_and_thresholds() -> None:
    from pr_reviewer.evals.regression_gate import compare_eval_reports

    baseline = _run()
    candidate = _run()
    result = compare_eval_reports(candidate, baseline, _thresholds())
    assert result.passed is True
    assert result.blocked_metrics == ()


def test_precision_regression_is_blocked() -> None:
    from pr_reviewer.evals.regression_gate import compare_eval_reports

    result = compare_eval_reports(_run(precision_per_finding=0.6), _run(), _thresholds())
    assert result.passed is False
    assert "precision_per_finding" in result.blocked_metrics


def test_false_findings_regression_is_blocked() -> None:
    from pr_reviewer.evals.regression_gate import compare_eval_reports

    result = compare_eval_reports(_run(false_findings_per_pr=0.5), _run(), _thresholds())
    assert result.passed is False
    assert "false_findings_per_pr" in result.blocked_metrics


def test_high_value_recall_regression_is_blocked() -> None:
    from pr_reviewer.evals.regression_gate import compare_eval_reports

    result = compare_eval_reports(_run(recall_per_finding=0.4), _run(), _thresholds())
    assert result.passed is False
    assert "high_value_recall" in result.blocked_metrics


def test_cost_regression_is_blocked() -> None:
    from pr_reviewer.evals.regression_gate import compare_eval_reports

    result = compare_eval_reports(_run(cost_usd=0.60), _run(), _thresholds())
    assert result.passed is False
    assert "cost_usd" in result.blocked_metrics


def test_latency_regression_is_blocked() -> None:
    from pr_reviewer.evals.regression_gate import compare_eval_reports

    result = compare_eval_reports(_run(latency_ms=800), _run(), _thresholds())
    assert result.passed is False
    assert "latency_ms" in result.blocked_metrics


def test_public_holdout_baseline_is_still_blocked() -> None:
    from pr_reviewer.evals.fixture_reviewer import FixtureReviewer
    from pr_reviewer.evals.run_eval import (
        BaselineBlocked,
        load_public_eval_cases,
        run_diff_only_baseline,
    )

    with pytest.raises(BaselineBlocked, match="holdout"):
        run_diff_only_baseline(load_public_eval_cases(), FixtureReviewer.perfect())


def test_brier_score_and_calibration_buckets_are_reported() -> None:
    from pr_reviewer.evals.regression_gate import brier_score, calibration_buckets

    predictions = ((0.9, True), (0.1, False), (0.8, False), (0.2, True))
    score = brier_score(predictions)
    assert 0.0 <= score <= 1.0
    buckets = calibration_buckets(predictions)
    assert buckets
    assert all(0.0 <= bucket.accuracy <= 1.0 for bucket in buckets)


def test_routing_source_does_not_read_confidence() -> None:
    source = (SRC_ROOT / "notifications" / "gate.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "confidence":
            raise AssertionError("route_finding must not read confidence")
        if isinstance(node, ast.Name) and node.id == "confidence":
            raise AssertionError("route_finding must not mention confidence")


def test_drift_alerts_cover_named_rates() -> None:
    from pr_reviewer.evals.regression_gate import DriftSnapshot, detect_drift

    baseline = DriftSnapshot(
        rejection_rate=0.10,
        dispute_rate=0.05,
        no_finding_rate=0.20,
        cost_usd=0.10,
        latency_ms=100,
        retrieval_miss_rate=0.10,
    )
    current = DriftSnapshot(
        rejection_rate=0.40,
        dispute_rate=0.30,
        no_finding_rate=0.60,
        cost_usd=0.80,
        latency_ms=900,
        retrieval_miss_rate=0.50,
    )
    alerts = detect_drift(current, baseline)
    assert set(alerts) >= {
        "rejection_rate",
        "dispute_rate",
        "no_finding_rate",
        "cost_usd",
        "latency_ms",
        "retrieval_miss_rate",
    }


def test_useful_findings_per_dollar_is_blocked_without_cost() -> None:
    from pr_reviewer.evals.run_eval import BaselineBlocked, useful_findings_per_dollar

    with pytest.raises(BaselineBlocked, match="cost"):
        useful_findings_per_dollar(_run(cost_usd=0.0))


def test_useful_findings_per_dollar_uses_useful_finding_count() -> None:
    from pr_reviewer.evals.run_eval import useful_findings_per_dollar

    assert useful_findings_per_dollar(_run(cost_usd=0.5, useful_finding_count=4)) == 8.0


def test_write_eval_report_is_machine_readable_json(tmp_path: Path) -> None:
    from pr_reviewer.evals.run_eval import write_eval_report

    path = tmp_path / "report.json"
    write_eval_report(_run(), path)
    text = path.read_text(encoding="utf-8")
    assert '"precision_per_finding"' in text
    assert '"false_findings_per_pr"' in text
    assert '"cost_usd"' in text
