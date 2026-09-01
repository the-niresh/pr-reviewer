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
from typing import TextIO

from pr_reviewer.evals.mine_candidates import estimate_diff_tokens, mine_eval_candidates
from pr_reviewer.evals.types import EvalCase, EvalLabel, EvalSplit, assign_time_split


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


DIFF_PAGE_LINES = 40


def _load_sheet_rows(sheet: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in sheet.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _atomic_write_rows(sheet: Path, rows: list[dict[str, object]]) -> None:
    tmp = sheet.with_name(sheet.name + ".tmp")
    tmp.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    tmp.replace(sheet)


def _verdict_counts(rows: list[dict[str, object]]) -> tuple[int, int]:
    include = sum(1 for row in rows if str(row.get("verdict") or "").strip() == "include")
    exclude = sum(1 for row in rows if str(row.get("verdict") or "").strip() == "exclude")
    return include, exclude


def _read_line(stdin: TextIO) -> str | None:
    line = stdin.readline()
    if line == "":
        return None
    return line.rstrip("\n")


def _show_diff(diff: str, *, stdin: TextIO, stdout: TextIO) -> None:
    lines = diff.splitlines() or [""]
    page = DIFF_PAGE_LINES
    tty = bool(getattr(stdin, "isatty", lambda: False)())
    if not tty or len(lines) <= page:
        stdout.write(diff if diff.endswith("\n") or diff == "" else diff + "\n")
        return
    start = 0
    while start < len(lines):
        chunk = lines[start : start + page]
        stdout.write("\n".join(chunk) + "\n")
        start += page
        if start < len(lines):
            stdout.write("-- more --\n")
            stdout.flush()
            if _read_line(stdin) is None:
                return


def _prompt_labels(stdin: TextIO, stdout: TextIO) -> list[dict[str, object]] | None:
    while True:
        stdout.write("labels json (array of EvalLabel, empty rejected):\n")
        stdout.flush()
        raw = _read_line(stdin)
        if raw is None:
            return None
        if raw.strip() == "":
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, list) or not parsed:
            continue
        try:
            labels = [EvalLabel.model_validate(item) for item in parsed]
        except Exception:
            continue
        return [label.model_dump() for label in labels]


def _prompt_split(stdin: TextIO, stdout: TextIO) -> EvalSplit | None:
    while True:
        stdout.write("split (dev|holdout):\n")
        stdout.flush()
        raw = _read_line(stdin)
        if raw is None:
            return None
        value = raw.strip()
        if value in {"dev", "holdout"}:
            return value  # type: ignore[return-value]
        # Empty and unknown values are rejected. No default.


def _split_from_committed_at(committed_at: date, holdout_after: date) -> EvalSplit:
    stub = EvalCase(
        id="derive-split",
        split="dev",
        diff="placeholder",
        expected_labels=[
            EvalLabel(
                concern="correctness",
                category="derive",
                file_path="derive.py",
                line_start=1,
                line_end=1,
            )
        ],
        source_evidence=["derive"],
        human_auditor="derive",
        committed_at=committed_at,
    )
    return assign_time_split([stub], holdout_after=holdout_after)[0].split


def review_sheet(
    sheet: Path,
    *,
    auditor: str,
    split_after: date | None = None,
    stdin: TextIO = sys.stdin,
    stdout: TextIO = sys.stdout,
) -> int:
    if not auditor.strip():
        raise ValueError("auditor is required")
    rows = _load_sheet_rows(sheet)
    index = 0
    while index < len(rows):
        row = rows[index]
        if str(row.get("verdict") or "").strip():
            index += 1
            continue
        include_count, exclude_count = _verdict_counts(rows)
        stdout.write(
            f"row {index + 1} of {len(rows)}, {include_count} include, {exclude_count} exclude\n"
        )
        stdout.write(f"id: {row.get('id')}\n")
        stdout.write(f"sha: {row.get('sha')}\n")
        stdout.write(f"committed_at: {row.get('committed_at')}\n")
        stdout.write(f"subject: {row.get('subject')}\n")
        files = row.get("files") or []
        stdout.write(f"files: {files}\n")
        stdout.write("diff:\n")
        _show_diff(str(row.get("diff") or ""), stdin=stdin, stdout=stdout)
        stdout.write("e/exclude  i/include  s/skip  q/quit\n")
        stdout.flush()
        command = _read_line(stdin)
        if command is None:
            return 0
        token = command.strip().lower()
        if token in {"q", "quit"}:
            return 0
        if token in {"s", "skip"}:
            index += 1
            continue
        if token in {"e", "exclude"}:
            row["verdict"] = "exclude"
            _atomic_write_rows(sheet, rows)
            index += 1
            continue
        if token in {"i", "include"}:
            labels = _prompt_labels(stdin, stdout)
            if labels is None:
                return 0
            if split_after is not None:
                committed_raw = str(row.get("committed_at") or "").strip()
                if not committed_raw:
                    stdout.write("committed_at missing; cannot derive split\n")
                    continue
                chosen_split = _split_from_committed_at(
                    date.fromisoformat(committed_raw), split_after
                )
            else:
                prompted_split = _prompt_split(stdin, stdout)
                if prompted_split is None:
                    return 0
                chosen_split = prompted_split
            row["verdict"] = "include"
            row["human_auditor"] = auditor.strip()
            row["split"] = chosen_split
            row["labels"] = labels
            _atomic_write_rows(sheet, rows)
            index += 1
            continue
        # Unknown or empty command: re-prompt this row. No default verdict.
    return 0


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
    review = sub.add_parser("review", help="judge unjudged sheet rows from a terminal")
    review.add_argument("--sheet", type=Path, required=True)
    review.add_argument("--auditor", required=True)
    review.add_argument("--split-after", type=date.fromisoformat, default=None)
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
        if args.command == "review":
            return review_sheet(
                args.sheet, auditor=args.auditor, split_after=args.split_after
            )
        written = build_holdout(args.sheet, args.out)
        print(f"holdout_cases={written} out={args.out}")
        return 0
    except HoldoutUnjudged as exc:
        print(f"HoldoutUnjudged: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
