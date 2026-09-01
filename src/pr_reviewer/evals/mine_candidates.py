"""Mine eval candidates from git history. A commit message is evidence, not a label."""

from __future__ import annotations

import subprocess
from datetime import date
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


def _even_sample(items: list[str], n: int) -> list[str]:
    if n <= 0 or not items:
        return []
    if len(items) <= n:
        return items
    return [items[(index * len(items)) // n] for index in range(n)]


def _log_shas(
    repo: Path,
    *,
    since: date | None,
    until: date | None,
    max_count: int | None,
    reverse: bool,
) -> list[str]:
    args = ["log", "--format=%H"]
    if since is not None:
        args.append(f"--since={since.isoformat()}")
    if until is not None:
        args.append(f"--until={until.isoformat()}")
    if reverse:
        args.append("--reverse")
    if max_count is not None:
        args.append(f"--max-count={max_count}")
    return [
        line.strip()
        for line in _git_output(repo, args).splitlines()
        if line.strip()
    ]


def mine_eval_candidates(
    repo: Path,
    max_cases: int = 10,
    *,
    model: str = "gpt-4o-mini",
    since: date | None = None,
    until: date | None = None,
    per_window: int | None = None,
) -> MineResult:
    if not (repo / ".git").exists():
        return MineResult(candidates=[], skipped=())
    if per_window is not None:
        shas = _even_sample(
            _log_shas(repo, since=since, until=until, max_count=None, reverse=True),
            per_window,
        )
    else:
        shas = _log_shas(
            repo, since=since, until=until, max_count=max_cases, reverse=False
        )
    budget = context_budget_for_model(model)
    candidates: list[EvalCandidate] = []
    skipped: list[SkippedMineCommit] = []
    for sha in shas:
        meta = _git_output(repo, ["show", "-s", "--format=%s%n%cs", sha]).splitlines()
        subject = (meta[0].strip() if meta else "") or sha
        committed_at: date | None = None
        if len(meta) > 1 and meta[1].strip():
            committed_at = date.fromisoformat(meta[1].strip())
        files = tuple(
            line.strip()
            for line in _git_output(
                repo, ["diff-tree", "--no-commit-id", "--name-only", "-r", sha]
            ).splitlines()
            if line.strip()
        )
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
        candidates.append(
            EvalCandidate(
                source_evidence=[subject],
                diff=patch,
                committed_at=committed_at,
                sha=sha,
                files=files,
            )
        )
    return MineResult(candidates=candidates, skipped=tuple(skipped))
