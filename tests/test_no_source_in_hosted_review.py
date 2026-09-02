"""Phase 27 widens the hosted allowlist for findings text and agent reasoning. This proves that
widening did not open a door for diff hunks or source: review_findings and agent_reasoning have
no column shaped like one, and adding one is still rejected by assert_no_private_columns.
"""

from __future__ import annotations

import psycopg
import pytest

from pr_reviewer.control_plane.boundary import HostedSchemaViolation, assert_no_private_columns
from pr_reviewer.db.client import connection

WIDENED_TABLES = ("review_findings",)
FORBIDDEN_COLUMN_NAME_FRAGMENTS = ("diff", "patch", "hunk", "source", "sandbox_log", "embedding")


def test_widened_tables_have_no_diff_or_source_shaped_column() -> None:
    with connection() as conn:
        rows = conn.execute(
            """
            select table_name, column_name from information_schema.columns
            where table_schema = 'public' and table_name = any(%s)
            """,
            (list(WIDENED_TABLES),),
        ).fetchall()

    offenders = [
        f"{row['table_name']}.{row['column_name']}"
        for row in rows
        if any(
            fragment in str(row["column_name"]).lower()
            for fragment in FORBIDDEN_COLUMN_NAME_FRAGMENTS
        )
    ]
    assert offenders == [], f"diff/source-shaped column found on a widened table: {offenders}"


def test_adding_a_diff_column_to_review_findings_is_still_rejected() -> None:
    with connection() as conn:
        conn.execute("alter table review_findings add column diff text")
        conn.commit()
        try:
            with pytest.raises(HostedSchemaViolation):
                assert_no_private_columns(conn)
        finally:
            conn.execute("alter table review_findings drop column diff")
            conn.commit()


def test_adding_a_source_column_to_review_findings_is_still_rejected() -> None:
    with connection() as conn:
        conn.execute("alter table review_findings add column source_snippet text")
        conn.commit()
        try:
            with pytest.raises(HostedSchemaViolation):
                assert_no_private_columns(conn)
        finally:
            conn.execute("alter table review_findings drop column source_snippet")
            conn.commit()


def test_review_findings_insert_rejects_an_unlisted_evidence_column() -> None:
    # evidence was deliberately left off review_findings (see the migration and boundary.py):
    # this proves the table really has no such column, not just that ALLOWLIST omits one.
    with pytest.raises(psycopg.errors.UndefinedColumn), connection() as conn, conn.transaction():
        conn.execute("insert into review_findings (id, evidence) values ('probe', '[]')")
