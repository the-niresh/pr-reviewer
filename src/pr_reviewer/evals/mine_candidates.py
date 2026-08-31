"""Mine eval candidates from git history. A commit message is evidence, not a label."""

from __future__ import annotations

import subprocess
from pathlib import Path

from pr_reviewer.context_budget import context_budget_for_model
from pr_reviewer.evals.types import EvalCandidate, MineResult, SkippedMineCommit


def estimate_diff_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def _git_output(repo: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
    )
    return result.stdout.decode("utf-8", errors="replace")


def mine_eval_candidates(
    repo: Path,
    max_cases: int = 10,
    *,
    model: str = "gpt-4o-mini",
) -> MineResult:
    if not (repo / ".git").exists():
        return MineResult(candidates=[], skipped=())
    shas = [
        line.strip()
        for line in _git_output(
            repo, ["log", f"--max-count={max_cases}", "--format=%H"]
        ).splitlines()
        if line.strip()
    ]
    budget = context_budget_for_model(model)
    candidates: list[EvalCandidate] = []
    skipped: list[SkippedMineCommit] = []
    for sha in shas:
        subject = _git_output(repo, ["show", "-s", "--format=%s", sha]).strip() or sha
        patch = _git_output(repo, ["show", "--format=", "-p", sha])
        token_count = estimate_diff_tokens(patch)
        if token_count > budget.tokens:
            skipped.append(
                SkippedMineCommit(
                    sha=sha,
                    subject=subject,
                    reason="diff_exceeds_packed_budget",
                    token_count=token_count,
                    token_budget=budget.tokens,
                )
            )
            continue
        candidates.append(EvalCandidate(source_evidence=[subject], diff=patch))
    return MineResult(candidates=candidates, skipped=tuple(skipped))
