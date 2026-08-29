#!/usr/bin/env python3
"""Regenerate the hosted table in docs/DATA_BOUNDARIES.md from control_plane/boundary.py.

The allowlist in boundary.py is the enforced half of the data boundary; this script renders it as
a markdown table between two HTML comment markers in the doc, so the human-readable half cannot
drift from what assert_no_private_columns actually checks.

Usage:
  python3 scripts/generate_data_boundaries_doc.py         # rewrite the doc in place
  python3 scripts/generate_data_boundaries_doc.py --check # exit 1 if the doc is out of date
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pr_reviewer.control_plane.boundary import ALLOWLIST, HOSTED_EXEMPTIONS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DOC_PATH = ROOT / "docs" / "DATA_BOUNDARIES.md"
BEGIN_MARKER = "<!-- BEGIN GENERATED HOSTED ALLOWLIST -->"
END_MARKER = "<!-- END GENERATED HOSTED ALLOWLIST -->"


def render_table() -> str:
    lines = [
        "| Table | Column | Reason |",
        "|---|---|---|",
    ]
    for table, column in sorted(ALLOWLIST):
        reason = ALLOWLIST[(table, column)]
        lines.append(f"| `{table}` | `{column}` | {reason} |")
    lines.append("")
    if HOSTED_EXEMPTIONS:
        tail = (
            " or belongs to a table in `HOSTED_EXEMPTIONS` "
            f"(`{', '.join(sorted(HOSTED_EXEMPTIONS))}`, see below)."
        )
    else:
        tail = ". `HOSTED_EXEMPTIONS` is empty: every hosted table's columns are covered above."
    lines.append(
        "Every other hosted column is either `uuid`, `timestamptz`, `integer`, `bigint`, "
        "`boolean`, or `numeric` (auto-permitted; none of those types can hold source, a diff, "
        f"or a rationale){tail}"
    )
    return "\n".join(lines)


def main() -> int:
    check_only = "--check" in sys.argv[1:]
    text = DOC_PATH.read_text(encoding="utf-8")
    if BEGIN_MARKER not in text or END_MARKER not in text:
        print(f"{DOC_PATH}: missing {BEGIN_MARKER} / {END_MARKER} markers", file=sys.stderr)
        return 1

    before, rest = text.split(BEGIN_MARKER, 1)
    _, after = rest.split(END_MARKER, 1)
    generated = f"{BEGIN_MARKER}\n{render_table()}\n{END_MARKER}"
    new_text = f"{before}{generated}{after}"

    if check_only:
        if new_text != text:
            print(f"{DOC_PATH} is out of date, run without --check to regenerate", file=sys.stderr)
            return 1
        print(f"{DOC_PATH} is up to date.")
        return 0

    DOC_PATH.write_text(new_text, encoding="utf-8")
    print(f"Regenerated hosted allowlist table in {DOC_PATH}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
