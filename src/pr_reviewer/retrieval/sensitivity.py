"""Deterministic per-file sensitivity: fix density, callers, structural flags."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from pr_reviewer.retrieval.code_graph import CodeGraph

_FIX_SUBJECT = re.compile(r"\b(fix|revert)\b", re.IGNORECASE)
_MARKER_NEEDLES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("auth", ("auth", "oauth", "session")),
    ("tokens", ("token", "jwt")),
    ("crypto", ("crypto", "secret")),
    ("migrations", ("migration", "migrations")),
    ("deletion", ("delete", "destroy", "drop")),
    ("money", ("money", "stripe", "billing", "payment")),
)


@dataclass(frozen=True)
class SensitivityScore:
    path: str
    fix_density: float
    fix_count: int
    commit_count: int
    caller_count: int
    structural_flags: tuple[str, ...]
    evidence: tuple[str, ...]

    def prompt_facts(self) -> str:
        return f"{self.path} has {self.fix_count} prior fixes and {self.caller_count} callers"


def score_sensitivity(repo_path: Path, graph: CodeGraph) -> dict[str, SensitivityScore]:
    paths = _tracked_paths(repo_path)
    for node in graph.nodes.values():
        if node.source_file:
            paths.add(node.source_file)
    callers_by_file = _extracted_callers_by_file(graph)
    imported_by_file = _extracted_imports_by_file(graph)
    scores: dict[str, SensitivityScore] = {}
    for path in sorted(paths):
        fix_count, commit_count = _fix_history(repo_path, path)
        density = (fix_count / commit_count) if commit_count else 0.0
        caller_count = len(callers_by_file.get(path, set()))
        flags = _structural_flags(path, imported_by_file.get(path, ()))
        evidence = [
            f"{caller_count} EXTRACTED callers",
            f"{fix_count} fix-or-revert commits of {commit_count} --follow --no-merges",
        ]
        if flags:
            evidence.append("structural flags: " + ",".join(flags))
        scores[path] = SensitivityScore(
            path=path,
            fix_density=density,
            fix_count=fix_count,
            commit_count=commit_count,
            caller_count=caller_count,
            structural_flags=flags,
            evidence=tuple(evidence),
        )
    return scores


def _extracted_callers_by_file(graph: CodeGraph) -> dict[str, set[str]]:
    file_of = {node.id: node.source_file for node in graph.nodes.values()}
    callers: dict[str, set[str]] = {}
    for edge in graph.edges:
        if edge.confidence != "EXTRACTED" or edge.relation != "calls":
            continue
        target_file = file_of.get(edge.target)
        if not target_file:
            continue
        callers.setdefault(target_file, set()).add(edge.source)
    return callers


def _extracted_imports_by_file(graph: CodeGraph) -> dict[str, tuple[str, ...]]:
    file_of = {node.id: node.source_file for node in graph.nodes.values()}
    label_of = {node.id: node.label for node in graph.nodes.values()}
    imported: dict[str, list[str]] = {}
    for edge in graph.edges:
        if edge.confidence != "EXTRACTED" or edge.relation not in {"imports", "imports_from"}:
            continue
        source_file = file_of.get(edge.source)
        if not source_file:
            continue
        imported.setdefault(source_file, []).append(label_of.get(edge.target, edge.target))
    return {path: tuple(labels) for path, labels in imported.items()}


def _structural_flags(path: str, imported_labels: tuple[str, ...]) -> tuple[str, ...]:
    haystack = f"{path} {' '.join(imported_labels)}".lower()
    flags: list[str] = []
    for name, needles in _MARKER_NEEDLES:
        if any(needle in haystack for needle in needles):
            flags.append(name)
    return tuple(flags)


def _tracked_paths(repo_path: Path) -> set[str]:
    git_dir = repo_path / ".git"
    if not git_dir.exists():
        return {
            str(item.relative_to(repo_path))
            for item in repo_path.rglob("*")
            if item.is_file() and "graphify-out" not in item.parts
        }
    result = subprocess.run(
        ["git", "-C", str(repo_path), "ls-files"],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    if result.returncode != 0:
        return set()
    return {line for line in result.stdout.splitlines() if line}


def _fix_history(repo_path: Path, path: str) -> tuple[int, int]:
    git_dir = repo_path / ".git"
    if not git_dir.exists():
        return 0, 0
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repo_path),
            "log",
            "--follow",
            "--no-merges",
            "--format=%s",
            "--",
            path,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    if result.returncode != 0:
        return 0, 0
    subjects = [line for line in result.stdout.splitlines() if line]
    fix_count = sum(1 for subject in subjects if _FIX_SUBJECT.search(subject))
    return fix_count, len(subjects)
