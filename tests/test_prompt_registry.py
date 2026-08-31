"""Failing tests for the immutable prompt registry (master Task 10).

In-process registry rejects an update to an existing name and version. The hosted
prompt_versions table gets the same rule from a migration trigger. Imports of new
modules stay inside test bodies.
"""

from __future__ import annotations

import pytest
from psycopg.errors import RaiseException, UniqueViolation

from pr_reviewer.db.client import connection


def test_registry_rejects_an_update_to_an_existing_name_and_version() -> None:
    from pr_reviewer.prompts.registry import PromptRegistry, PromptVersionImmutable

    registry = PromptRegistry()
    registry.register("reviewer", "1", "review the diff")
    with pytest.raises(PromptVersionImmutable):
        registry.register("reviewer", "1", "review the diff, updated")
    with pytest.raises(PromptVersionImmutable):
        registry.register("reviewer", "1", "review the diff")
    registry.register("reviewer", "2", "review the diff, v2")
    assert registry.get("reviewer", "1").content == "review the diff"
    assert registry.get("reviewer", "2").content == "review the diff, v2"


def test_registry_unknown_prompt_raises() -> None:
    from pr_reviewer.prompts.registry import PromptNotFound, PromptRegistry

    registry = PromptRegistry()
    with pytest.raises(PromptNotFound):
        registry.get("reviewer", "1")


def test_hosted_prompt_versions_reject_an_update_to_existing_name_and_version() -> None:
    from pr_reviewer.events.record_prompt_version import (
        PromptVersionConflict,
        record_prompt_version,
    )

    first = record_prompt_version("reviewer", "1", "review the diff")
    with pytest.raises(PromptVersionConflict):
        record_prompt_version("reviewer", "1", "review the diff, updated")
    with connection() as conn:
        row = conn.execute(
            "select content from prompt_versions where id = %s", (first,)
        ).fetchone()
    assert row is not None
    assert row["content"] == "review the diff"
    with connection() as conn, pytest.raises(RaiseException):
        conn.execute(
            "update prompt_versions set content = %s where id = %s",
            ("mutated", first),
        )


def test_hosted_prompt_versions_unique_name_and_version() -> None:
    with connection() as conn, conn.transaction():
        conn.execute(
            "insert into prompt_versions (name, version, content) values (%s, %s, %s)",
            ("reviewer", "9", "first"),
        )
    with pytest.raises(UniqueViolation), connection() as conn, conn.transaction():
        conn.execute(
            "insert into prompt_versions (name, version, content) values (%s, %s, %s)",
            ("reviewer", "9", "second"),
        )


def test_prompts_package_must_not_import_hosted_or_runner_stores() -> None:
    from pathlib import Path

    from test_package_boundaries import collect_imports

    package_dir = Path(__file__).resolve().parent.parent / "src" / "pr_reviewer" / "prompts"
    assert package_dir.is_dir()
    imports = collect_imports(package_dir)
    forbidden = (
        "pr_reviewer.db",
        "pr_reviewer.control_plane",
        "pr_reviewer.runner",
        "pr_reviewer.local_store",
    )
    hits = {
        module
        for module in imports
        for prefix in forbidden
        if module == prefix or module.startswith(prefix + ".")
    }
    assert not hits, f"prompts/* must not import hosted or runner stores, found: {sorted(hits)}"
