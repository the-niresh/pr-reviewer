"""Mine eval candidates from git history. A commit message is evidence, not a label."""

from __future__ import annotations

import subprocess
from pathlib import Path

from pr_reviewer.evals.types import EvalCandidate


def _git_output(repo: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
    )
    return result.stdout.decode("utf-8", errors="replace")


def mine_eval_candidates(repo: Path, max_cases: int = 10) -> list[EvalCandidate]:
    if not (repo / ".git").exists():
        return []
    log = _git_output(
        repo,
        ["log", f"--max-count={max_cases}", "--name-only", "--pretty=format:%s"],
    )
    patches = _git_output(
        repo,
        ["log", f"--max-count={max_cases}", "-p", "--pretty=format:"],
    )
    evidence = [line.strip() for line in log.splitlines() if line.strip()]
    if not evidence:
        return []
    return [EvalCandidate(source_evidence=evidence, diff=patches)]
