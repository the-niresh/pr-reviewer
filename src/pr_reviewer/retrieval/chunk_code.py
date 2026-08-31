"""Split a source file into retrieval chunks.

Python uses ast.parse, which builds a tree and never executes the file. A Python
chunk is a function or class with its real line range. Identity is the file path
plus the qualified name, so an unrelated edit elsewhere does not change it.
Every other language uses overlapping line windows and records that strategy.
"""

from __future__ import annotations

import ast
import hashlib
import os
from collections.abc import Set
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

WINDOW_SIZE_LINES = 40
WINDOW_OVERLAP_LINES = 10
_SKIP_DIRECTORIES = frozenset({".git", "__pycache__"})
_LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".md": "markdown",
    ".json": "json",
    ".rs": "rust",
    ".go": "go",
}


class ChunkingStrategy(StrEnum):
    AST_PYTHON = "ast_python"
    LINE_WINDOW = "line_window"


@dataclass(frozen=True)
class CodeChunk:
    file_path: str
    language: str
    start_line: int
    end_line: int
    content: str
    content_hash: str
    identity: str
    strategy: ChunkingStrategy
    symbol_name: str | None = None


def chunk_source(file_path: str, source: str) -> tuple[CodeChunk, ...]:
    if Path(file_path).suffix == ".py":
        try:
            return _chunk_python(file_path, source)
        except SyntaxError:
            return _chunk_windows(file_path, source)
    return _chunk_windows(file_path, source)


def chunk_tree(
    root: Path,
    *,
    generated_paths: Set[str] | None = None,
    ignored_paths: Set[str] | None = None,
) -> tuple[CodeChunk, ...]:
    generated = generated_paths if generated_paths is not None else frozenset()
    ignored = ignored_paths if ignored_paths is not None else frozenset()
    chunks: list[CodeChunk] = []
    root_resolved = root.resolve()
    for dirpath, dirnames, filenames in os.walk(root_resolved, followlinks=False):
        dirnames[:] = [name for name in dirnames if name not in _SKIP_DIRECTORIES]
        for filename in filenames:
            path = Path(dirpath) / filename
            if path.is_symlink() or not path.is_file():
                continue
            relative = path.relative_to(root_resolved).as_posix()
            if relative in generated or relative in ignored:
                continue
            data = path.read_bytes()
            if b"\x00" in data:
                continue
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                continue
            chunks.extend(chunk_source(relative, text))
    return tuple(chunks)


def _chunk_python(file_path: str, source: str) -> tuple[CodeChunk, ...]:
    tree = ast.parse(source, filename=file_path)
    lines = source.splitlines()
    chunks: list[CodeChunk] = []
    _walk_python(tree, file_path, lines, prefix="", chunks=chunks)
    return tuple(chunks)


def _walk_python(
    node: ast.AST,
    file_path: str,
    lines: list[str],
    *,
    prefix: str,
    chunks: list[CodeChunk],
) -> None:
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            qualified = f"{prefix}.{child.name}" if prefix else child.name
            start, end = _node_line_range(child)
            content = _slice_lines(lines, start, end)
            chunks.append(
                _make_chunk(
                    file_path=file_path,
                    start_line=start,
                    end_line=end,
                    content=content,
                    strategy=ChunkingStrategy.AST_PYTHON,
                    identity=f"{file_path}::{qualified}",
                    symbol_name=qualified,
                )
            )
            _walk_python(child, file_path, lines, prefix=qualified, chunks=chunks)
        else:
            _walk_python(child, file_path, lines, prefix=prefix, chunks=chunks)


def _node_line_range(
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
) -> tuple[int, int]:
    start = node.lineno
    for decorator in node.decorator_list:
        if decorator.lineno < start:
            start = decorator.lineno
    end = node.end_lineno if node.end_lineno is not None else node.lineno
    return start, end


def _chunk_windows(file_path: str, source: str) -> tuple[CodeChunk, ...]:
    lines = source.splitlines()
    if not lines:
        return ()
    chunks: list[CodeChunk] = []
    start = 1
    total = len(lines)
    while start <= total:
        end = min(start + WINDOW_SIZE_LINES - 1, total)
        content = _slice_lines(lines, start, end)
        chunks.append(
            _make_chunk(
                file_path=file_path,
                start_line=start,
                end_line=end,
                content=content,
                strategy=ChunkingStrategy.LINE_WINDOW,
                identity=f"{file_path}:window:{start}:{end}",
                symbol_name=None,
            )
        )
        if end >= total:
            break
        start += WINDOW_SIZE_LINES - WINDOW_OVERLAP_LINES
    return tuple(chunks)


def _make_chunk(
    *,
    file_path: str,
    start_line: int,
    end_line: int,
    content: str,
    strategy: ChunkingStrategy,
    identity: str,
    symbol_name: str | None,
) -> CodeChunk:
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return CodeChunk(
        file_path=file_path,
        language=_language_for(file_path),
        start_line=start_line,
        end_line=end_line,
        content=content,
        content_hash=digest,
        identity=identity,
        strategy=strategy,
        symbol_name=symbol_name,
    )


def _language_for(file_path: str) -> str:
    suffix = Path(file_path).suffix.lower()
    if suffix in _LANGUAGE_BY_SUFFIX:
        return _LANGUAGE_BY_SUFFIX[suffix]
    if suffix:
        return suffix.removeprefix(".")
    return "text"


def _slice_lines(lines: list[str], start_line: int, end_line: int) -> str:
    return "\n".join(lines[start_line - 1 : end_line])
