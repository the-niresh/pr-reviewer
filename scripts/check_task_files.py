#!/usr/bin/env python3
"""Check that every file a plan task declares actually exists on disk.

Task reports say "done". This says whether the declared deliverables are there. Runtime Task 1 was
reported complete and verified against its behaviour, while docs/DATA_BOUNDARIES.md had never been
written, because nobody diffed the file list.

Usage:
  scripts/check_task_files.py                 # every task in every plan
  scripts/check_task_files.py "Task 1"        # one task, by heading prefix
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLANS = sorted((ROOT / "docs" / "superpowers" / "plans").glob("*.md"))
TASK_HEAD = re.compile(r"^### (Task [0-9]+[A-Z]?) - (⬜|✅|❌) (.+)$", re.M)
FILE_LINE = re.compile(r"^- (Create|Modify|Test): (.+)$", re.M)
# "hosted migration `<timestamp>_name.sql`" is a pattern, not a literal path
MIGRATION = re.compile(r"(?:hosted|local(?: SQLite| pgvector)?) migration `<timestamp>_(.+?)\.sql`")


def declared_paths(body: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for kind, raw in FILE_LINE.findall(body):
        raw = raw.strip()
        migration = MIGRATION.search(raw)
        if migration:
            out.append((kind, f"@migration:{migration.group(1)}"))
            continue
        path = raw.strip("`").strip()
        if path.startswith("`") or "`" in path:
            path = path.replace("`", "")
        out.append((kind, path))
    return out


def resolve(path: str) -> tuple[bool, str]:
    # A path written with a <timestamp> placeholder is a pattern. Resolve it by globbing rather
    # than depending on the surrounding prose, so "migration `<timestamp>_x.sql`" and a real path
    # like "src/.../migrations/<timestamp>_x.sql" both work.
    if "<timestamp>" in path:
        pattern = path.replace("<timestamp>", "*")
        hits = list(ROOT.glob(pattern))
        return bool(hits), (hits[0].relative_to(ROOT).as_posix() if hits else pattern)
    if path.startswith("@migration:"):
        stem = path.split(":", 1)[1]
        for d in (ROOT / "src/pr_reviewer/db/migrations",
                  ROOT / "src/pr_reviewer/local_store/migrations",
                  ROOT / "src/pr_reviewer/local_store/postgres_migrations"):
            if d.is_dir() and any(stem in p.name for p in d.iterdir()):
                hit = next(p.name for p in d.iterdir() if stem in p.name)
                return True, f"migration {hit}"
        return False, f"migration *_{stem}.sql"
    if "*" in path:
        return bool(list(ROOT.glob(path))), path
    return (ROOT / path).exists(), path


def main() -> int:
    wanted = sys.argv[1] if len(sys.argv) > 1 else None
    failures = 0
    for plan in PLANS:
        text = plan.read_text(encoding="utf-8")
        heads = list(TASK_HEAD.finditer(text))
        for i, m in enumerate(heads):
            name, mark, title = m.group(1), m.group(2), m.group(3)
            if wanted and not name.startswith(wanted):
                continue
            end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
            paths = declared_paths(text[m.end():end])
            if not paths:
                continue
            missing = [(k, label) for k, p in paths
                       for ok, label in [resolve(p)] if not ok]
            if not missing:
                continue
            # A task has started only if one of its CREATE targets exists. Modify targets often
            # pre-date the task (Task 7 modifies contracts/github.py, written back in Task 6), so
            # counting those marks every future task as started.
            started = any(resolve(p)[0] for kind, p in paths if kind == "Create")
            if not started and mark == "⬜":
                continue
            failures += len(missing)
            print(f"\n{plan.name} :: {name} [{mark}] {title}")
            for kind, label in missing:
                print(f"  MISSING ({kind}): {label}")
    if failures:
        print(f"\n{failures} declared deliverable(s) missing from started tasks.")
        return 1
    print("All started tasks have their declared files on disk.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
