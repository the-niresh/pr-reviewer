from __future__ import annotations

import re
from pathlib import Path

from pr_reviewer.db.client import connection


def test_hosted_schema_and_writers_have_no_agent_reasoning() -> None:
    with connection() as conn:
        row = conn.execute(
            "select to_regclass('public.agent_reasoning') as table_name"
        ).fetchone()
    assert row is not None
    assert row["table_name"] is None

    root = Path(__file__).resolve().parents[1] / "src" / "pr_reviewer"
    writers = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if re.search(r"\binsert\s+into\s+agent_reasoning\b", text, re.IGNORECASE):
            writers.append(str(path.relative_to(root)))
    assert writers == []
