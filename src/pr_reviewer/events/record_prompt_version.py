"""Hosted insert-only writer for prompt_versions. Updates are rejected by the table trigger."""

from __future__ import annotations

from pr_reviewer.db.client import connection


class PromptVersionConflict(Exception):
    """A row with this name and version already exists."""


def record_prompt_version(name: str, version: str, content: str) -> str:
    with connection() as conn, conn.transaction():
        row = conn.execute(
            """
            insert into prompt_versions (name, version, content)
            values (%s, %s, %s)
            on conflict (name, version) do nothing
            returning id
            """,
            (name, version, content),
        ).fetchone()
    if row is None:
        raise PromptVersionConflict()
    return str(row["id"])
