"""Failing tests for CI, release containers, and supply-chain config (master Task 23)."""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

SECRET_BUILD_MARKERS = (
    "DATABASE_URL",
    "NEON",
    "WEBHOOK_SECRET",
    "GITHUB_APP_PRIVATE_KEY",
    "GITHUB_PRIVATE_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "PRIVATE_KEY",
)

MIGRATION_SETS = (
    REPO / "src/pr_reviewer/db/migrations",
    REPO / "src/pr_reviewer/local_store/migrations",
    REPO / "src/pr_reviewer/local_store/postgres_migrations",
)

# Applied names that must keep existing. A rename deletes an applied file.
REQUIRED_APPLIED_MIGRATIONS = {
    "src/pr_reviewer/db/migrations": (
        "0001_initial.sql",
        "0002_foreign_key_indexes.sql",
        "0003_review_job_leases.sql",
        "0004_event_and_cost_ledger.sql",
        "202608272008_control_plane_identity.sql",
        "202608281326_retire_local_only_tables.sql",
        "202608281629_runner_protocol.sql",
        "202608281951_oauth_state.sql",
        "202608290208_runner_job_leases.sql",
        "202608291930_rescope_hosted_events.sql",
        "202608302200_pr_lifecycle.sql",
        "202608302330_connector_runs.sql",
        "202608311600_prompt_registry_constraints.sql",
        "202609010100_notification_channels.sql",
        "202609010300_create_pull_request_review.sql",
        "202609010400_reliability_and_budget.sql",
        "202609011830_drop_review_jobs_draft.sql",
    ),
    "src/pr_reviewer/local_store/migrations": (
        "202608291645_local_state.sql",
        "202609010100_human_feedback_hashes.sql",
        "202609010200_workflow_runs.sql",
        "202609010400_job_budget_reservations.sql",
    ),
    "src/pr_reviewer/local_store/postgres_migrations": (
        "0000_extensions.sql",
        "202608311400_retrieval_generations.sql",
        "202608312000_finding_candidates_and_verification.sql",
        "202608312200_repo_profile_and_graph.sql",
    ),
}

MIGRATION_NAME = re.compile(r"^(0000_|000\d_|\d{12}_).+\.sql$")
FROM_LINE = re.compile(r"^\s*FROM\s+(\S+)", re.IGNORECASE)
IMAGE_LINE = re.compile(r"^\s+image:\s+(\S+)", re.IGNORECASE)
USER_LINE = re.compile(r"^\s*USER\s+(\S+)", re.IGNORECASE | re.MULTILINE)
ARG_LINE = re.compile(r"^\s*ARG\s+(\S+)", re.IGNORECASE | re.MULTILINE)


def _read(relative: str) -> str:
    path = REPO / relative
    assert path.is_file(), f"missing {relative}"
    return path.read_text(encoding="utf-8")


def _from_refs(text: str) -> list[str]:
    return [match.group(1) for match in FROM_LINE.finditer(text)]


def _image_refs(text: str) -> list[str]:
    return [match.group(1) for match in IMAGE_LINE.finditer(text)]


def _is_pinned(ref: str) -> bool:
    return "@sha256:" in ref and ":latest" not in ref


def test_root_dockerfile_is_non_root_and_digest_pinned() -> None:
    text = _read("Dockerfile")
    users = USER_LINE.findall(text)
    assert users, "release images must drop privileges"
    assert all(user.split(":")[0] not in {"root", "0"} for user in users)
    refs = _from_refs(text)
    assert refs, "Dockerfile needs a FROM line"
    assert all(_is_pinned(ref) for ref in refs), refs
    for arg in ARG_LINE.findall(text):
        name = arg.split("=")[0]
        assert not any(marker in name.upper() for marker in SECRET_BUILD_MARKERS), name


def test_compose_release_and_ci_are_non_root_healthy_and_pinned() -> None:
    for relative in ("docker-compose.ci.yml", "compose.release.yml"):
        text = _read(relative)
        assert "user:" in text
        assert "healthcheck:" in text
        assert all(_is_pinned(ref) for ref in _image_refs(text)), relative
        assert not any(marker in text for marker in SECRET_BUILD_MARKERS), relative


def test_ci_workflow_runs_the_required_gates() -> None:
    text = _read(".github/workflows/ci.yml")
    for needle in (
        "ruff",
        "mypy",
        "pytest",
        "migration-from-empty",
        "migration-upgrade",
        "bun run build",
        "playwright",
        "scripts/check_supply_chain.py lock",
        "scripts/check_supply_chain.py secrets",
        "scripts/check_supply_chain.py containers",
        "scripts/check_supply_chain.py generated",
    ):
        assert needle in text, needle


def test_release_workflow_writes_checksums_and_sbom() -> None:
    text = _read(".github/workflows/release.yml")
    assert "SHA256SUMS" in text
    assert "sbom" in text.lower()
    assert "cosign" in text or "syft" in text or "anchore" in text


def test_migration_filenames_are_unique_prefixed_and_not_renamed() -> None:
    for directory in MIGRATION_SETS:
        names = sorted(path.name for path in directory.glob("*.sql"))
        assert names == sorted(names)
        assert len(names) == len(set(names))
        for name in names:
            assert MIGRATION_NAME.match(name), name
        relative = str(directory.relative_to(REPO))
        required = REQUIRED_APPLIED_MIGRATIONS[relative]
        missing = set(required) - set(names)
        assert missing == set(), f"applied migration renamed in {relative}: {sorted(missing)}"
