"""Failing tests for code chunking (master Task 12).

Python uses ast.parse (stdlib, never executes the file). A chunk is a function or
class with its real line range. Every other language uses overlapping line windows.
Each chunk records which strategy produced it. Imports of new modules stay inside
test bodies.
"""

from __future__ import annotations

from pathlib import Path

PYTHON_SOURCE = """\
def greet(name: str) -> str:
    return f"hello {name}"


class Greeter:
    def shout(self, name: str) -> str:
        return greet(name).upper()
"""

UNRELATED_PREFIX = "CONSTANT = 1\n\n"


def test_python_chunks_are_functions_and_classes_with_real_line_ranges() -> None:
    from pr_reviewer.retrieval.chunk_code import ChunkingStrategy, chunk_source

    chunks = chunk_source("src/greet.py", PYTHON_SOURCE)
    by_symbol = {chunk.symbol_name: chunk for chunk in chunks}
    assert set(by_symbol) == {"greet", "Greeter", "Greeter.shout"}
    assert by_symbol["greet"].start_line == 1
    assert by_symbol["greet"].end_line == 2
    assert by_symbol["Greeter"].start_line == 5
    assert by_symbol["Greeter"].end_line == 7
    assert by_symbol["Greeter.shout"].start_line == 6
    assert by_symbol["Greeter.shout"].end_line == 7
    assert all(chunk.strategy == ChunkingStrategy.AST_PYTHON for chunk in chunks)
    assert all(chunk.language == "python" for chunk in chunks)
    assert all(chunk.file_path == "src/greet.py" for chunk in chunks)


def test_unrelated_edit_elsewhere_does_not_change_python_chunk_identity() -> None:
    from pr_reviewer.retrieval.chunk_code import chunk_source

    original = chunk_source("src/greet.py", PYTHON_SOURCE)
    shifted = chunk_source("src/greet.py", UNRELATED_PREFIX + PYTHON_SOURCE)
    original_foo = next(chunk for chunk in original if chunk.symbol_name == "greet")
    shifted_foo = next(chunk for chunk in shifted if chunk.symbol_name == "greet")
    assert original_foo.identity == shifted_foo.identity
    assert original_foo.content_hash == shifted_foo.content_hash
    assert shifted_foo.start_line == original_foo.start_line + 2
    assert shifted_foo.end_line == original_foo.end_line + 2


def test_function_rename_changes_chunk_identity() -> None:
    from pr_reviewer.retrieval.chunk_code import chunk_source

    before = chunk_source("src/greet.py", "def foo():\n    return 1\n")
    after = chunk_source("src/greet.py", "def bar():\n    return 1\n")
    assert before[0].identity != after[0].identity
    assert before[0].symbol_name == "foo"
    assert after[0].symbol_name == "bar"


def test_non_python_uses_overlapping_line_windows_and_records_the_strategy() -> None:
    from pr_reviewer.retrieval.chunk_code import (
        WINDOW_OVERLAP_LINES,
        WINDOW_SIZE_LINES,
        ChunkingStrategy,
        chunk_source,
    )

    source = "\n".join(f"line {index}" for index in range(1, 81))
    chunks = chunk_source("src/widget.js", source)
    assert len(chunks) >= 2
    assert all(chunk.strategy == ChunkingStrategy.LINE_WINDOW for chunk in chunks)
    assert all(chunk.language == "javascript" for chunk in chunks)
    first, second = chunks[0], chunks[1]
    assert first.start_line == 1
    assert first.end_line == WINDOW_SIZE_LINES
    assert second.start_line == 1 + WINDOW_SIZE_LINES - WINDOW_OVERLAP_LINES
    assert second.start_line <= first.end_line
    overlap = {line for line in range(second.start_line, first.end_line + 1)}
    assert overlap


def test_line_ranges_are_one_based_and_inclusive() -> None:
    from pr_reviewer.retrieval.chunk_code import chunk_source

    source = "one\ntwo\nthree\n"
    chunks = chunk_source("notes.md", source)
    assert len(chunks) == 1
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 3
    assert chunks[0].end_line >= chunks[0].start_line


def test_content_hash_is_sha256_of_chunk_content() -> None:
    import hashlib

    from pr_reviewer.retrieval.chunk_code import chunk_source

    chunks = chunk_source("src/greet.py", "def foo():\n    return 1\n")
    assert len(chunks) == 1
    expected = hashlib.sha256(chunks[0].content.encode("utf-8")).hexdigest()
    assert chunks[0].content_hash == expected
    assert len(chunks[0].content_hash) == 64


def test_binary_generated_ignored_and_symlink_files_are_not_chunked(tmp_path: Path) -> None:
    from pr_reviewer.retrieval.chunk_code import chunk_tree

    root = tmp_path / "repo"
    root.mkdir()
    (root / "ok.py").write_text("def keep():\n    return 1\n", encoding="utf-8")
    (root / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00binary")
    dist = root / "dist"
    dist.mkdir()
    (dist / "app.js").write_text("console.log('generated');\n", encoding="utf-8")
    ignored_dir = root / "tmp"
    ignored_dir.mkdir()
    (ignored_dir / "cache.dat").write_text("cache\n", encoding="utf-8")
    secret = tmp_path / "secret.py"
    secret.write_text("def leak():\n    return 0\n", encoding="utf-8")
    (root / "link.py").symlink_to(secret)
    git_dir = root / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")

    chunks = chunk_tree(
        root,
        generated_paths={"dist/app.js"},
        ignored_paths={"tmp/cache.dat"},
    )
    paths = {chunk.file_path for chunk in chunks}
    assert paths == {"ok.py"}
    assert all(chunk.symbol_name == "keep" for chunk in chunks)
