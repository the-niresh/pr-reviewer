"""Failing tests for the Task 11 eval harness entry (master Task 11).

The public dataset has one dev case and zero holdout. The harness may run
FixtureReviewer. A holdout baseline is refused rather than invented.
Imports of new modules stay inside test bodies.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def test_public_dataset_has_one_dev_case_and_zero_holdout() -> None:
    from pr_reviewer.evals.run_eval import load_public_eval_cases

    cases = load_public_eval_cases()
    assert [case.id for case in cases] == ["public-1"]
    assert [case.split for case in cases] == ["dev"]
    assert not any(case.split == "holdout" for case in cases)


def test_harness_runs_fixture_reviewer_on_the_dev_case() -> None:
    from pr_reviewer.evals.fixture_reviewer import FixtureReviewer
    from pr_reviewer.evals.run_eval import load_public_eval_cases, run_eval
    from pr_reviewer.evals.types import EvalConfig

    cases = load_public_eval_cases()
    run = run_eval(EvalConfig(cases=cases, repeats=3), FixtureReviewer.perfect())
    assert run.metrics.precision_per_finding == 1.0
    assert run.metrics.recall_per_finding == 1.0
    assert run.metrics.reviewed_pr_count == 3


def test_diff_only_baseline_is_blocked_when_holdout_is_empty() -> None:
    from pr_reviewer.evals.fixture_reviewer import FixtureReviewer
    from pr_reviewer.evals.run_eval import (
        BaselineBlocked,
        load_public_eval_cases,
        run_diff_only_baseline,
    )

    with pytest.raises(BaselineBlocked, match="holdout"):
        run_diff_only_baseline(load_public_eval_cases(), FixtureReviewer.perfect())


def test_eval_runner_still_imports_nothing_from_models() -> None:
    from test_package_boundaries import _imports_matching_prefix, collect_imports

    evals_imports = collect_imports(REPO / "src" / "pr_reviewer" / "evals")
    assert not _imports_matching_prefix(evals_imports, "pr_reviewer.models")
    source = (REPO / "src" / "pr_reviewer" / "evals" / "run_eval.py").read_text(
        encoding="utf-8"
    )
    assert "httpx" not in source
    assert "openai" not in source
    assert "anthropic" not in source
