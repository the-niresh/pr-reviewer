"""Write a reviewable candidate sheet and build a holdout only from judged rows.

The writer never fills verdict, split, auditor, or labels. The builder refuses
any row whose verdict is empty. It does not guess a split.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from pr_reviewer.evals.mine_candidates import estimate_diff_tokens, mine_eval_candidates
from pr_reviewer.evals.types import EvalCase, EvalLabel, EvalSplit


class HoldoutUnjudged(Exception):
    """A sheet row has no verdict, or an include row is missing required fields."""


@dataclass(frozen=True)
class SheetStats:
    candidate_count: int
    skipped_count: int


def write_candidate_sheet(
    repo: Path, dest: Path, max_cases: int = 40, *, id_prefix: str = "cand"
) -> SheetStats:
    mined = mine_eval_candidates(repo, max_cases=max_cases)
    dest.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for index, candidate in enumerate(mined.candidates, start=1):
        committed = ""
        if candidate.committed_at is not None:
            committed = candidate.committed_at.isoformat()
        row = {
            "id": f"{id_prefix}-{index:03d}",
            "sha": candidate.sha,
            "committed_at": committed,
            "subject": candidate.source_evidence[0] if candidate.source_evidence else "",
            "files": list(candidate.files),
            "token_count": estimate_diff_tokens(candidate.diff),
            "source_evidence": list(candidate.source_evidence),
            "diff": candidate.diff,
            "verdict": "",
            "human_auditor": "",
            "split": "",
            "labels": [],
        }
        lines.append(json.dumps(row, ensure_ascii=False))
    dest.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return SheetStats(
        candidate_count=len(mined.candidates),
        skipped_count=len(mined.skipped),
    )


def _parse_committed_at(value: str) -> date:
    return date.fromisoformat(value)


def build_holdout(sheet: Path, dest: Path) -> int:
    rows = [
        json.loads(line)
        for line in sheet.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    cases: list[EvalCase] = []
    for row in rows:
        row_id = str(row.get("id") or "")
        verdict = str(row.get("verdict") or "").strip()
        if verdict == "":
            raise HoldoutUnjudged(f"row {row_id or '<missing id>'} is unjudged")
        if verdict == "exclude":
            continue
        if verdict != "include":
            raise HoldoutUnjudged(f"row {row_id} has unknown verdict {verdict!r}")
        auditor = str(row.get("human_auditor") or "").strip()
        split_raw = str(row.get("split") or "").strip()
        labels_raw = row.get("labels") or []
        committed_raw = str(row.get("committed_at") or "").strip()
        diff = str(row.get("diff") or "")
        evidence = row.get("source_evidence") or []
        if not auditor or split_raw not in {"dev", "holdout"} or not labels_raw:
            raise HoldoutUnjudged(
                f"row {row_id} is include but missing auditor, split, or labels"
            )
        if not committed_raw or not diff or not evidence:
            raise HoldoutUnjudged(f"row {row_id} is include but missing case fields")
        split: EvalSplit = "holdout" if split_raw == "holdout" else "dev"
        labels = [EvalLabel.model_validate(item) for item in labels_raw]
        cases.append(
            EvalCase(
                id=row_id,
                split=split,
                diff=diff,
                expected_labels=labels,
                source_evidence=list(evidence),
                human_auditor=auditor,
                committed_at=_parse_committed_at(committed_raw),
            )
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        "".join(case.model_dump_json() + "\n" for case in cases),
        encoding="utf-8",
    )
    return len(cases)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pr-reviewer-holdout")
    sub = parser.add_subparsers(dest="command", required=True)
    write = sub.add_parser("write-sheet", help="mine a repo into an unjudged JSONL sheet")
    write.add_argument("--repo", type=Path, required=True)
    write.add_argument("--out", type=Path, required=True)
    write.add_argument("--max-cases", type=int, default=40)
    write.add_argument("--id-prefix", default="cand")
    build = sub.add_parser(
        "build-holdout", help="write judged include rows to an EvalCase JSONL"
    )
    build.add_argument("--sheet", type=Path, required=True)
    build.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "write-sheet":
            stats = write_candidate_sheet(
                args.repo,
                args.out,
                max_cases=args.max_cases,
                id_prefix=args.id_prefix,
            )
            print(
                f"candidates={stats.candidate_count} skipped={stats.skipped_count} out={args.out}"
            )
            return 0
        written = build_holdout(args.sheet, args.out)
        print(f"holdout_cases={written} out={args.out}")
        return 0
    except HoldoutUnjudged as exc:
        print(f"HoldoutUnjudged: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
