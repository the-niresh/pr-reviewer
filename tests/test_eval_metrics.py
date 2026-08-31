"""Failing tests for eval metrics, FixtureReviewer, and package guards (master Task 9).

run_eval takes an injected ReviewerCallable and imports nothing from models/.
FixtureReviewer replays perfect, silent, noisy, and flaky-across-repeats.
Rule-adherence is scored on three arms separately.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "pr_reviewer"


def _label() -> Any:
    from pr_reviewer.evals.types import EvalLabel

    return EvalLabel(
        concern="correctness",
        category="null-check",
        file_path="src/widget.py",
        line_start=10,
        line_end=12,
    )


def _case(*, case_id: str = "case-1") -> Any:
    from pr_reviewer.evals.types import EvalCase

    return EvalCase(
        id=case_id,
        split="dev",
        diff="@@ -1 +1 @@\n+value = widget.value",
        expected_labels=[_label()],
        source_evidence=["fix null check"],
        human_auditor="niresh",
        committed_at=date(2024, 1, 1),
    )


def _candidate(**overrides: Any) -> Any:
    from pr_reviewer.contracts.finding_candidate import FindingCandidate

    fields: dict[str, Any] = {
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
    return FindingCandidate(**fields)


def test_metrics_cover_precision_recall_and_cost() -> None:
    from pr_reviewer.evals.match_findings import match_findings
    from pr_reviewer.evals.metrics import compute_metrics

    matched = match_findings([_label()], [_candidate()])
    extra = match_findings([_label()], [_candidate(file_path="src/other.py")])
    metrics = compute_metrics([matched, extra], reviewed_pr_count=2)
    assert metrics.precision_per_finding == 0.5
    assert metrics.precision_per_case == 0.5
    assert metrics.recall_per_finding == 0.5
    assert metrics.recall_per_case == 0.5
    assert metrics.false_findings_per_pr == 0.5
    assert metrics.selectivity == 1.0
    assert metrics.verified_finding_rate == 0.0
    assert metrics.latency_ms == 0
    assert metrics.cost_usd == 0.0
    assert metrics.needs_human_rate == 0.5
    assert metrics.reviewed_pr_count == 2


def test_rule_adherence_is_scored_on_three_arms() -> None:
    from pr_reviewer.evals.match_findings import match_findings
    from pr_reviewer.evals.metrics import compute_metrics

    result = match_findings([_label()], [_candidate()])
    metrics = compute_metrics([result], reviewed_pr_count=1)
    arms = set(metrics.rule_adherence)
    assert arms == {"retrieval_only", "executable_check_only", "both"}


def test_fixture_reviewer_perfect_silent_noisy_and_flaky() -> None:
    from pr_reviewer.evals.fixture_reviewer import FixtureReviewer
    from pr_reviewer.evals.run_eval import run_eval
    from pr_reviewer.evals.types import EvalConfig

    config = EvalConfig(cases=[_case()], repeats=3)
    perfect = run_eval(config, FixtureReviewer.perfect())
    assert perfect.metrics.precision_per_finding == 1.0
    assert perfect.metrics.precision_per_case == 1.0
    assert perfect.metrics.recall_per_finding == 1.0
    assert perfect.metrics.recall_per_case == 1.0

    silent = run_eval(config, FixtureReviewer.silent())
    assert silent.metrics.recall_per_finding == 0.0
    assert silent.metrics.recall_per_case == 0.0

    noisy = run_eval(config, FixtureReviewer.noisy())
    assert noisy.metrics.false_findings_per_pr > 0

    flaky = FixtureReviewer.flaky(seed=1)
    scores = [run_eval(config, flaky).metrics.precision_per_finding for _ in range(3)]
    assert len(set(scores)) > 1


def test_run_eval_and_evals_package_import_nothing_from_models() -> None:
    from test_package_boundaries import (
        EXPECTED_EXISTING_PACKAGES,
        GUARDED_PACKAGES,
        HOSTED_SIDE_PACKAGES,
        RUNNER_SIDE_PACKAGES,
        _imports_matching_prefix,
        collect_imports,
    )

    assert "evals" in GUARDED_PACKAGES
    assert "models" in GUARDED_PACKAGES
    assert "evals" in EXPECTED_EXISTING_PACKAGES
    assert "models" in EXPECTED_EXISTING_PACKAGES
    assert "models" in RUNNER_SIDE_PACKAGES
    assert "models" not in HOSTED_SIDE_PACKAGES
    assert "evals" not in HOSTED_SIDE_PACKAGES

    evals_imports = collect_imports(SRC_ROOT / "evals")
    assert not _imports_matching_prefix(evals_imports, "pr_reviewer.models")
    assert not _imports_matching_prefix(evals_imports, "pr_reviewer.db")
    assert not _imports_matching_prefix(evals_imports, "pr_reviewer.control_plane")

    models_imports = collect_imports(SRC_ROOT / "models")
    assert not _imports_matching_prefix(models_imports, "pr_reviewer.runner")
    assert not _imports_matching_prefix(models_imports, "pr_reviewer.local_store")

    source = (SRC_ROOT / "evals" / "run_eval.py").read_text(encoding="utf-8")
    assert "httpx" not in source
    assert "openai" not in source
    assert "anthropic" not in source
