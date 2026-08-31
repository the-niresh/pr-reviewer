"""Failing tests for the hunk renderer (master Task 10A).

Paired new and old blocks. Line numbers on new-side lines only. Every rendered
new-side number must map back to a real head-file line so Task 17 can anchor a
comment. Imports of new modules stay inside test bodies.
"""

from __future__ import annotations

import re

NEW_LINE = re.compile(r"^(\d+)\| (.*)$")


def _new_side_pairs(rendered: str) -> list[tuple[int, str]]:
    pairs: list[tuple[int, str]] = []
    section = None
    for line in rendered.splitlines():
        if line.startswith("NEW "):
            section = "new"
            continue
        if line.startswith("OLD "):
            section = "old"
            continue
        if section != "new":
            continue
        match = NEW_LINE.match(line)
        if match is not None:
            pairs.append((int(match.group(1)), match.group(2)))
    return pairs


def test_render_hunks_emits_paired_new_and_old_blocks() -> None:
    from pr_reviewer.contracts.review_context import FilePatch
    from pr_reviewer.reviewer.hunk_format import render_hunks

    rendered = render_hunks(
        FilePatch(
            path="app.py",
            patch="@@ -1,2 +1,3 @@\n def foo():\n     return 1\n+    return 2\n",
        )
    )
    assert "NEW app.py" in rendered
    assert "OLD app.py" in rendered
    assert rendered.index("NEW app.py") < rendered.index("OLD app.py")


def test_line_numbers_appear_on_new_side_lines_only() -> None:
    from pr_reviewer.contracts.review_context import FilePatch
    from pr_reviewer.reviewer.hunk_format import render_hunks

    rendered = render_hunks(
        FilePatch(
            path="app.py",
            patch="@@ -1,2 +1,2 @@\n def foo():\n-    return 1\n+    return 2\n",
        )
    )
    in_old = False
    for line in rendered.splitlines():
        if line.startswith("OLD "):
            in_old = True
            continue
        if line.startswith("NEW "):
            in_old = False
            continue
        if in_old:
            assert NEW_LINE.match(line) is None, line


def test_rendered_new_side_line_numbers_map_back_to_head_file_lines() -> None:
    from pr_reviewer.contracts.review_context import FilePatch
    from pr_reviewer.reviewer.hunk_format import render_hunks

    head_lines = ["def foo():", "    return 1", "    return 2"]
    rendered = render_hunks(
        FilePatch(
            path="app.py",
            patch="@@ -1,2 +1,3 @@\n def foo():\n     return 1\n+    return 2\n",
        )
    )
    pairs = _new_side_pairs(rendered)
    assert pairs
    for number, text in pairs:
        assert 1 <= number <= len(head_lines)
        assert text == head_lines[number - 1]


def test_multiple_hunks_stay_whole_file_pairs() -> None:
    from pr_reviewer.contracts.review_context import FilePatch
    from pr_reviewer.reviewer.hunk_format import render_hunks

    patch = (
        "@@ -1,1 +1,2 @@\n"
        " alpha\n"
        "+beta\n"
        "@@ -10,1 +11,2 @@\n"
        " omega\n"
        "+zeta\n"
    )
    rendered = render_hunks(FilePatch(path="mod.py", patch=patch))
    assert rendered.count("NEW mod.py") == 2
    assert rendered.count("OLD mod.py") == 2
    numbers = [number for number, _text in _new_side_pairs(rendered)]
    assert numbers == [1, 2, 11, 12]


def test_renamed_file_keeps_previous_path_in_the_render() -> None:
    from pr_reviewer.contracts.review_context import FilePatch
    from pr_reviewer.reviewer.hunk_format import render_hunks

    rendered = render_hunks(
        FilePatch(
            path="new.py",
            previous_path="old.py",
            patch="@@ -1,1 +1,1 @@\n-old\n+new\n",
        )
    )
    assert "NEW new.py" in rendered
    assert "old.py" in rendered
