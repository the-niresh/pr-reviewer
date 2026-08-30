"""Mine eval candidates from git history. A commit message is evidence, not a label."""

from __future__ import annotations

import subprocess
from pathlib import Path

from pr_reviewer.evals.types import EvalCandidate


def mine_eval_candidates(repo: Path, max_cases: int = 10) -> list[EvalCandidate]:
    if not (repo / ".git").exists():
        return []
    log = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "log",
            f"--max-count={max_cases}",
            "--name-only",
            "--pretty=format:%s",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    patches = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "log",
            f"--max-count={max_cases}",
            "-p",
            "--pretty=format:",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    evidence = [line.strip() for line in log.stdout.splitlines() if line.strip()]
    if not evidence:
        return []
    return [EvalCandidate(source_evidence=evidence, diff=patches.stdout)]
