"""Eval data stays on the runner. Hosted eval tables are a phantom and stay absent."""

from __future__ import annotations

from pathlib import Path

from test_package_boundaries import _imports_matching_prefix, collect_imports

REPO = Path(__file__).resolve().parent.parent
HOSTED_MIGRATIONS = REPO / "src" / "pr_reviewer" / "db" / "migrations"
EVALS_MD = REPO / "docs" / "EVALS.md"
BANNED_TABLE_NEEDLES = (
    "create table eval_",
    "create table eval_cases",
    "create table eval_results",
    "create table eval_reports",
    "eval_foundation",
)


def test_hosted_migrations_have_no_eval_foundation_or_eval_tables() -> None:
    names = [path.name for path in HOSTED_MIGRATIONS.glob("*.sql")]
    assert not any("eval_foundation" in name for name in names)
    for path in HOSTED_MIGRATIONS.glob("*.sql"):
        text = path.read_text(encoding="utf-8").lower()
        for needle in BANNED_TABLE_NEEDLES:
            assert needle not in text, f"{path.name} contains {needle}"


def test_evals_package_does_not_import_hosted_db() -> None:
    evals_imports = collect_imports(REPO / "src" / "pr_reviewer" / "evals")
    assert not _imports_matching_prefix(evals_imports, "pr_reviewer.db")
    assert not _imports_matching_prefix(evals_imports, "pr_reviewer.control_plane")


def test_evals_md_records_why_eval_stays_local() -> None:
    text = EVALS_MD.read_text(encoding="utf-8")
    assert "The hosted plane does not get an `eval_foundation` migration." in text
    assert "tests/test_eval_stays_local.py" in text
