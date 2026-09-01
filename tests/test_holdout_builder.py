"""Candidate sheet and holdout builder. Humans fill verdicts. Code refuses blanks."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _init_git_repo(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "eval@test.example"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Eval Test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    return repo


def _commit_file(repo: Path, relative: str, content: str, message: str) -> None:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "--", relative], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", message], cwd=repo, check=True, capture_output=True)


def test_write_candidate_sheet_leaves_verdict_empty(tmp_path: Path) -> None:
    from pr_reviewer.evals.holdout_sheet import write_candidate_sheet

    repo = _init_git_repo(tmp_path)
    _commit_file(repo, "src/widget.py", "value = 1\n", "fix widget")
    sheet = tmp_path / "sheet.jsonl"
    stats = write_candidate_sheet(repo, sheet, max_cases=10)
    assert stats.candidate_count >= 1
    rows = [json.loads(line) for line in sheet.read_text(encoding="utf-8").splitlines() if line]
    assert rows
    for row in rows:
        assert row["verdict"] == ""
        assert row["human_auditor"] == ""
        assert row["split"] == ""
        assert row["labels"] == []
        assert row["sha"]
        assert row["subject"]
        assert "diff" in row


def test_build_holdout_refuses_an_unjudged_row(tmp_path: Path) -> None:
    from pr_reviewer.evals.holdout_sheet import HoldoutUnjudged, build_holdout

    sheet = tmp_path / "sheet.jsonl"
    sheet.write_text(
        json.dumps(
            {
                "id": "cand-001",
                "sha": "a" * 40,
                "committed_at": "2026-01-02",
                "subject": "fix widget",
                "files": ["src/widget.py"],
                "token_count": 4,
                "source_evidence": ["fix widget"],
                "diff": "@@ -1 +1 @@\n+value = 1\n",
                "verdict": "",
                "human_auditor": "",
                "split": "",
                "labels": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "holdout.jsonl"
    with pytest.raises(HoldoutUnjudged, match="unjudged"):
        build_holdout(sheet, out)
    assert not out.exists()


def test_build_holdout_writes_included_judged_rows(tmp_path: Path) -> None:
    from pr_reviewer.evals.holdout_sheet import build_holdout
    from pr_reviewer.evals.types import EvalCase

    sheet = tmp_path / "sheet.jsonl"
    include = {
        "id": "cand-001",
        "sha": "a" * 40,
        "committed_at": "2026-01-02",
        "subject": "fix widget",
        "files": ["src/widget.py"],
        "token_count": 4,
        "source_evidence": ["fix widget"],
        "diff": "@@ -1 +1 @@\n+value = 1\n",
        "verdict": "include",
        "human_auditor": "niresh",
        "split": "holdout",
        "labels": [
            {
                "concern": "correctness",
                "category": "null-check",
                "file_path": "src/widget.py",
                "line_start": 1,
                "line_end": 1,
            }
        ],
    }
    exclude = {**include, "id": "cand-002", "verdict": "exclude", "sha": "b" * 40}
    sheet.write_text(
        json.dumps(include) + "\n" + json.dumps(exclude) + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "holdout.jsonl"
    written = build_holdout(sheet, out)
    assert written == 1
    case = EvalCase.model_validate_json(out.read_text(encoding="utf-8").splitlines()[0])
    assert case.id == "cand-001"
    assert case.split == "holdout"
    assert case.human_auditor == "niresh"


def test_build_holdout_refuses_include_without_split_or_auditor(tmp_path: Path) -> None:
    from pr_reviewer.evals.holdout_sheet import HoldoutUnjudged, build_holdout

    sheet = tmp_path / "sheet.jsonl"
    row = {
        "id": "cand-001",
        "sha": "a" * 40,
        "committed_at": "2026-01-02",
        "subject": "fix widget",
        "files": ["src/widget.py"],
        "token_count": 4,
        "source_evidence": ["fix widget"],
        "diff": "@@ -1 +1 @@\n+value = 1\n",
        "verdict": "include",
        "human_auditor": "",
        "split": "",
        "labels": [
            {
                "concern": "correctness",
                "category": "null-check",
                "file_path": "src/widget.py",
                "line_start": 1,
                "line_end": 1,
            }
        ],
    }
    sheet.write_text(json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(HoldoutUnjudged):
        build_holdout(sheet, tmp_path / "holdout.jsonl")


def test_cli_build_holdout_refuses_unjudged_rows(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from pr_reviewer.evals.holdout_sheet import main

    sheet = tmp_path / "sheet.jsonl"
    sheet.write_text(
        json.dumps(
            {
                "id": "cand-001",
                "sha": "a" * 40,
                "committed_at": "2026-01-02",
                "subject": "fix widget",
                "files": ["src/widget.py"],
                "token_count": 4,
                "source_evidence": ["fix widget"],
                "diff": "@@ -1 +1 @@\n+value = 1\n",
                "verdict": "",
                "human_auditor": "",
                "split": "",
                "labels": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    code = main(["build-holdout", "--sheet", str(sheet), "--out", str(tmp_path / "holdout.jsonl")])
    captured = capsys.readouterr()
    assert code == 2
    assert "HoldoutUnjudged" in captured.err
    assert "unjudged" in captured.err
