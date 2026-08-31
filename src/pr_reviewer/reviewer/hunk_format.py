"""Paired new/old hunk renderer. Line numbers are on new-side lines only."""

from __future__ import annotations

import re
from dataclasses import dataclass

from pr_reviewer.contracts.review_context import FilePatch

_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


@dataclass(frozen=True)
class _Hunk:
    new_start: int
    lines: tuple[str, ...]


def render_hunks(file_patch: FilePatch) -> str:
    new_header = f"NEW {file_patch.path}"
    old_header = f"OLD {file_patch.previous_path or file_patch.path}"
    blocks: list[str] = []
    for hunk in _parse_hunks(file_patch.patch):
        new_lines, old_lines = _split_hunk(hunk)
        blocks.append(new_header)
        blocks.extend(new_lines)
        blocks.append(old_header)
        blocks.extend(old_lines)
    return "\n".join(blocks)


def _parse_hunks(patch: str) -> list[_Hunk]:
    hunks: list[_Hunk] = []
    new_start = 1
    body: list[str] = []
    in_hunk = False
    for line in patch.splitlines():
        header = _HUNK_HEADER.match(line)
        if header is not None:
            if in_hunk:
                hunks.append(_Hunk(new_start=new_start, lines=tuple(body)))
            new_start = int(header.group(3))
            body = []
            in_hunk = True
            continue
        if in_hunk:
            body.append(line)
    if in_hunk:
        hunks.append(_Hunk(new_start=new_start, lines=tuple(body)))
    return hunks


def _split_hunk(hunk: _Hunk) -> tuple[list[str], list[str]]:
    new_lines: list[str] = []
    old_lines: list[str] = []
    new_no = hunk.new_start
    for raw in hunk.lines:
        if raw.startswith("\\") or raw == "":
            continue
        mark, content = raw[0], raw[1:]
        if mark == " ":
            new_lines.append(f"{new_no}| {content}")
            old_lines.append(content)
            new_no += 1
        elif mark == "+":
            new_lines.append(f"{new_no}| {content}")
            new_no += 1
        elif mark == "-":
            old_lines.append(content)
    return new_lines, old_lines
