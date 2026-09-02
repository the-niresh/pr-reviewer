from __future__ import annotations

from pathlib import Path

import pytest

from pr_reviewer import refusals


def test_refusal_registry_is_generated_from_source() -> None:
    generated = refusals.generate_registry()

    assert generated == refusals.checked_in_registry()
    assert len([entry for entry in generated if entry.id.startswith("eval-")]) == 6
    assert {
        "reliability-budget-unset-denies",
        "reliability-circuit-unreadable-denies",
        "notification-confidentiality-default-restricted",
        "feedback-candidates-unknown-age-decays",
    }.issubset({entry.id for entry in generated})


def test_refusal_registry_renders_one_discoverable_list() -> None:
    text = refusals.render_registry()

    assert "| Refusal | Source | Reason |" in text
    assert "holdout is empty; refusing to report a baseline" in text
    assert "Unreadable circuit state becomes open, which denies new calls." in text
    assert "Unset confidentiality defaults to restricted." in text


def test_refusal_registry_check_fails_on_drift(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    source = root / "src" / "pr_reviewer"
    for directory in (
        source / "evals",
        source / "reliability",
        source / "contracts",
    ):
        directory.mkdir(parents=True, exist_ok=True)
    (source / "evals" / "run_eval.py").write_text(
        """
class BaselineBlocked(Exception):
    \"\"\"Holdout is empty. Refusing to publish a baseline number.\"\"\"

def run_diff_only_baseline():
    raise BaselineBlocked("changed refusal")

def run_retrieval_comparison():
    raise BaselineBlocked("holdout is empty; refusing to report a retrieval comparison")

def run_context_source_comparison():
    raise BaselineBlocked("holdout is empty; refusing to report a context-source comparison")

def run_specialist_comparison():
    raise BaselineBlocked("holdout is empty; refusing to report a specialist comparison")

def useful_findings_per_dollar():
    raise BaselineBlocked("cost_usd is zero; refusing to report useful findings per dollar")
""",
        encoding="utf-8",
    )
    (source / "reliability" / "budget.py").write_text(
        """
class BudgetDenied(Exception):
    pass

def require_configured():
    raise BudgetDenied("unset")
""",
        encoding="utf-8",
    )
    (source / "reliability" / "circuit.py").write_text(
        'UNKNOWN_CIRCUIT_STATE: str = "open"\n',
        encoding="utf-8",
    )
    (source / "contracts" / "notification.py").write_text(
        """
class NotificationChannel:
    confidentiality: str = "restricted"
""",
        encoding="utf-8",
    )
    (source / "evals" / "feedback_candidates.py").write_text(
        """
def _event_is_fresh(event):
    if event.observed_at is None:
        return False
    return True
""",
        encoding="utf-8",
    )

    try:
        refusals.assert_registry_current(root)
    except refusals.RefusalRegistryDrift as exc:
        assert "changed refusal" in str(exc)
    else:
        raise AssertionError("--check must fail when generated refusals drift")


def test_refusal_registry_cli_check_reports_current(capsys: pytest.CaptureFixture[str]) -> None:
    assert refusals.main(["--check"]) == 0

    captured = capsys.readouterr()
    assert captured.out.strip() == "refusal registry is up to date."
