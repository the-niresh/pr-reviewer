"""Tests that the hosted schema cannot physically store private review data (Runtime Task 1A).

Migration 0001 was written when this was a single hosted service. It created findings, code_chunks,
human_decisions and pull_requests on the hosted plane, which the approved data boundary
(docs/phases/phase-2-security-design-gate.md, section 4, "assume breach") now forbids: a
compromised control plane must never be able to hand an attacker source, diffs, findings,
rationale, sandbox logs, or embeddings. Convention is not a boundary, so these tests prove the
schema itself cannot hold that data, on a real schema read, and make it impossible to add it back
by accident.

agent_events and model_calls are not touched here. They have live writers and no local store to
move to until Task 5, so Task 1B re-scopes them later. HOSTED_EXEMPTIONS names them explicitly so
that exemption cannot silently grow.
"""

from __future__ import annotations

import re
from pathlib import Path

import psycopg
import pytest

from pr_reviewer.db.client import connection

RETIRED_TABLES = ("findings", "code_chunks", "human_decisions", "pull_requests")
SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "pr_reviewer"


def test_retired_tables_do_not_exist_in_the_hosted_schema() -> None:
    with connection() as conn:
        rows = conn.execute(
            """
            select table_name from information_schema.tables
            where table_schema = 'public' and table_name = any(%s)
            """,
            (list(RETIRED_TABLES),),
        ).fetchall()

    still_present = sorted(str(row["table_name"]) for row in rows)
    assert not still_present, (
        f"these tables must be dropped by the retirement migration, still present: {still_present}"
    )


def test_retired_tables_have_zero_references_in_application_code() -> None:
    # Static proof, not prose. Dropping a table a writer still targets must be impossible to do
    # accidentally, so this scans every module under src/pr_reviewer for a whole-word mention of
    # each retired table name, rather than trusting a comment that says "nothing uses this".
    offenders: dict[str, list[str]] = {name: [] for name in RETIRED_TABLES}
    for path in sorted(SRC_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for name in RETIRED_TABLES:
            if re.search(rf"\b{name}\b", text):
                offenders[name].append(str(path.relative_to(SRC_ROOT.parent.parent)))

    referenced = {name: files for name, files in offenders.items() if files}
    assert not referenced, f"retired tables still referenced in application code: {referenced}"


def test_inserting_into_a_retired_table_is_rejected_by_the_database() -> None:
    # This has to stop being possible because the table is gone, not because nothing calls it today.
    with pytest.raises(psycopg.errors.UndefinedTable), connection() as conn, conn.transaction():
        conn.execute("insert into findings (id) values ('boundary-probe')")


def test_hosted_exemptions_is_exactly_agent_events_and_model_calls() -> None:
    from pr_reviewer.control_plane.boundary import HOSTED_EXEMPTIONS

    assert frozenset({"agent_events", "model_calls"}) == HOSTED_EXEMPTIONS, (
        "HOSTED_EXEMPTIONS must contain exactly agent_events and model_calls until Task 1B empties "
        "it. Adding a new exemption here must fail this test, the same way "
        "EXPECTED_EXISTING_PACKAGES works in test_package_boundaries.py."
    )


def test_assert_no_private_columns_passes_against_the_current_hosted_schema() -> None:
    from pr_reviewer.control_plane.boundary import assert_no_private_columns

    with connection() as conn:
        assert_no_private_columns(conn)


def test_assert_no_private_columns_raises_on_an_unlisted_text_column() -> None:
    from pr_reviewer.control_plane.boundary import HostedSchemaViolation, assert_no_private_columns

    with connection() as conn:
        conn.execute("alter table review_jobs add column boundary_probe_text text")
        conn.commit()
        try:
            with pytest.raises(HostedSchemaViolation):
                assert_no_private_columns(conn)
        finally:
            conn.execute("alter table review_jobs drop column boundary_probe_text")
            conn.commit()


def test_assert_no_private_columns_raises_on_an_unlisted_jsonb_column() -> None:
    from pr_reviewer.control_plane.boundary import HostedSchemaViolation, assert_no_private_columns

    with connection() as conn:
        conn.execute("alter table review_jobs add column boundary_probe_json jsonb")
        conn.commit()
        try:
            with pytest.raises(HostedSchemaViolation):
                assert_no_private_columns(conn)
        finally:
            conn.execute("alter table review_jobs drop column boundary_probe_json")
            conn.commit()


def test_array_type_columns_are_not_auto_permitted() -> None:
    # information_schema reports an array column's data_type as "ARRAY", not as its element type.
    # A type-scoped check that is not careful about this would let an unlisted text[] column
    # through as though it were some harmless scalar.
    from pr_reviewer.control_plane.boundary import HostedSchemaViolation, assert_no_private_columns

    with connection() as conn:
        conn.execute("alter table review_jobs add column boundary_probe_array integer[]")
        conn.commit()
        try:
            with pytest.raises(HostedSchemaViolation):
                assert_no_private_columns(conn)
        finally:
            conn.execute("alter table review_jobs drop column boundary_probe_array")
            conn.commit()


def test_user_defined_type_columns_are_not_auto_permitted() -> None:
    # information_schema reports pgvector's vector as data_type "USER-DEFINED". An embedding column
    # is exactly the shape this check exists to catch, so USER-DEFINED must never be auto-permitted.
    from pr_reviewer.control_plane.boundary import HostedSchemaViolation, assert_no_private_columns

    with connection() as conn:
        conn.execute("alter table review_jobs add column boundary_probe_vector vector(3)")
        conn.commit()
        try:
            with pytest.raises(HostedSchemaViolation):
                assert_no_private_columns(conn)
        finally:
            conn.execute("alter table review_jobs drop column boundary_probe_vector")
            conn.commit()
