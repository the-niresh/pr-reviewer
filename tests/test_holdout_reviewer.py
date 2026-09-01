"""Interactive holdout reviewer. Scripted stdin only. Never invents a verdict."""

from __future__ import annotations

import json
from datetime import date
from io import StringIO
from pathlib import Path

import pytest

LABEL = {
    "concern": "correctness",
    "category": "null-check",
    "file_path": "src/widget.py",
    "line_start": 1,
    "line_end": 1,
}


def _row(row_id: str, *, committed_at: str = "2026-01-02", verdict: str = "") -> dict[str, object]:
    return {
        "id": row_id,
        "sha": "a" * 40,
        "committed_at": committed_at,
        "subject": "fix widget",
        "files": ["src/widget.py"],
        "token_count": 4,
        "source_evidence": ["fix widget"],
        "diff": "@@ -1 +1 @@\n+value = 1\n",
        "verdict": verdict,
        "human_auditor": "",
        "split": "",
        "labels": [],
    }


def _write_sheet(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def _load(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _row_labels(row: dict[str, object]) -> list[dict[str, object]]:
    raw = row["labels"]
    assert isinstance(raw, list)
    labels: list[dict[str, object]] = []
    for item in raw:
        assert isinstance(item, dict)
        labels.append(item)
    return labels


def test_exclude_needs_no_auditor_split_or_labels(tmp_path: Path) -> None:
    from pr_reviewer.evals.holdout_sheet import review_sheet

    sheet = tmp_path / "sheet.jsonl"
    _write_sheet(sheet, [_row("cand-001"), _row("cand-002")])
    stdin = StringIO("e\nq\n")
    stdout = StringIO()
    code = review_sheet(
        sheet, auditor="niresh", stdin=stdin, stdout=stdout
    )
    assert code == 0
    rows = _load(sheet)
    assert rows[0]["verdict"] == "exclude"
    assert rows[0]["human_auditor"] == ""
    assert rows[0]["split"] == ""
    assert rows[0]["labels"] == []
    assert rows[1]["verdict"] == ""
    assert "row 1 of 2, 0 include, 0 exclude" in stdout.getvalue()


def test_resume_after_quit_judges_nothing_twice(tmp_path: Path) -> None:
    from pr_reviewer.evals.holdout_sheet import review_sheet

    sheet = tmp_path / "sheet.jsonl"
    _write_sheet(sheet, [_row("cand-001"), _row("cand-002")])
    first = StringIO("e\nq\n")
    review_sheet(sheet, auditor="niresh", stdin=first, stdout=StringIO())
    second_out = StringIO()
    review_sheet(sheet, auditor="niresh", stdin=StringIO("q\n"), stdout=second_out)
    rows = _load(sheet)
    assert rows[0]["verdict"] == "exclude"
    assert rows[1]["verdict"] == ""
    text = second_out.getvalue()
    assert "cand-001" not in text
    assert "cand-002" in text
    assert "row 2 of 2, 0 include, 1 exclude" in text


def test_include_with_empty_labels_reprompts(tmp_path: Path) -> None:
    from pr_reviewer.evals.holdout_sheet import review_sheet

    sheet = tmp_path / "sheet.jsonl"
    _write_sheet(sheet, [_row("cand-001")])
    stdin = StringIO("i\n\n" + json.dumps([LABEL]) + "\ndev\nq\n")
    stdout = StringIO()
    review_sheet(sheet, auditor="niresh", stdin=stdin, stdout=stdout)
    rows = _load(sheet)
    assert rows[0]["verdict"] == "include"
    assert rows[0]["human_auditor"] == "niresh"
    assert rows[0]["split"] == "dev"
    assert rows[0]["labels"] == [LABEL]
    assert "labels" in stdout.getvalue().lower()


def test_split_after_never_asks(tmp_path: Path) -> None:
    from pr_reviewer.evals.holdout_sheet import review_sheet

    sheet = tmp_path / "sheet.jsonl"
    _write_sheet(sheet, [_row("cand-001", committed_at="2026-07-02")])
    stdin = StringIO("i\n" + json.dumps([LABEL]) + "\nq\n")
    stdout = StringIO()
    review_sheet(
        sheet,
        auditor="niresh",
        split_after=date(2026, 6, 1),
        stdin=stdin,
        stdout=stdout,
    )
    rows = _load(sheet)
    assert rows[0]["verdict"] == "include"
    assert rows[0]["split"] == "holdout"
    assert "split (dev|holdout)" not in stdout.getvalue()


def test_interrupted_write_leaves_the_sheet_valid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pr_reviewer.evals import holdout_sheet

    sheet = tmp_path / "sheet.jsonl"
    original = [_row("cand-001"), _row("cand-002")]
    _write_sheet(sheet, original)

    def boom(_self: Path, _target: Path) -> None:
        raise OSError("interrupted")

    monkeypatch.setattr(Path, "replace", boom)
    with pytest.raises(OSError, match="interrupted"):
        holdout_sheet.review_sheet(
            sheet, auditor="niresh", stdin=StringIO("e\n"), stdout=StringIO()
        )
    rows = _load(sheet)
    assert rows[0]["verdict"] == ""
    assert rows[1]["verdict"] == ""


def test_review_cli_requires_auditor(tmp_path: Path) -> None:
    from pr_reviewer.evals.holdout_sheet import main

    sheet = tmp_path / "sheet.jsonl"
    _write_sheet(sheet, [_row("cand-001")])
    with pytest.raises(SystemExit):
        main(["review", "--sheet", str(sheet)])


def test_include_prompts_label_fields_instead_of_requiring_json(tmp_path: Path) -> None:
    from pr_reviewer.evals.holdout_sheet import review_sheet

    sheet = tmp_path / "sheet.jsonl"
    _write_sheet(
        sheet,
        [_row("cand-001") | {"files": ["src/widget.py", "src/other.py"]}],
    )
    stdin = StringIO("i\n2\nnull-check\n1\n14-20\nn\ndev\nq\n")
    stdout = StringIO()
    review_sheet(sheet, auditor="niresh", stdin=stdin, stdout=stdout)
    rows = _load(sheet)
    assert rows[0]["verdict"] == "include"
    assert rows[0]["labels"] == [
        {
            "concern": "correctness",
            "category": "null-check",
            "file_path": "src/widget.py",
            "line_start": 14,
            "line_end": 20,
        }
    ]
    text = stdout.getvalue()
    assert "1. security" in text
    assert "2. correctness" in text
    assert "1. src/widget.py" in text
    assert "add another" in text.lower()


def test_include_accepts_a_single_line_number(tmp_path: Path) -> None:
    from pr_reviewer.evals.holdout_sheet import review_sheet

    sheet = tmp_path / "sheet.jsonl"
    _write_sheet(sheet, [_row("cand-001")])
    stdin = StringIO("i\n2\nnull-check\n1\n14\nn\ndev\nq\n")
    review_sheet(sheet, auditor="niresh", stdin=stdin, stdout=StringIO())
    rows = _load(sheet)
    labels = _row_labels(rows[0])
    assert labels[0]["line_start"] == 14
    assert labels[0]["line_end"] == 14


def test_invalid_label_fields_reprompt_instead_of_discarding_the_row(tmp_path: Path) -> None:
    from pr_reviewer.evals.holdout_sheet import review_sheet

    sheet = tmp_path / "sheet.jsonl"
    _write_sheet(sheet, [_row("cand-001")])
    stdin = StringIO("i\n9\n\n2\n\nnull-check\n9\n1\nabc\n20-14\n14-20\nn\ndev\nq\n")
    stdout = StringIO()
    review_sheet(sheet, auditor="niresh", stdin=stdin, stdout=stdout)
    rows = _load(sheet)
    assert rows[0]["verdict"] == "include"
    labels = _row_labels(rows[0])
    assert labels[0]["concern"] == "correctness"
    assert labels[0]["file_path"] == "src/widget.py"
    assert labels[0]["line_start"] == 14
    assert labels[0]["line_end"] == 20


def test_json_array_fallback_still_accepted(tmp_path: Path) -> None:
    from pr_reviewer.evals.holdout_sheet import review_sheet

    sheet = tmp_path / "sheet.jsonl"
    _write_sheet(sheet, [_row("cand-001")])
    stdin = StringIO("i\n" + json.dumps([LABEL]) + "\ndev\nq\n")
    review_sheet(sheet, auditor="niresh", stdin=stdin, stdout=StringIO())
    rows = _load(sheet)
    assert rows[0]["verdict"] == "include"
    assert rows[0]["labels"] == [LABEL]


def test_add_another_label_then_stop(tmp_path: Path) -> None:
    from pr_reviewer.evals.holdout_sheet import review_sheet

    sheet = tmp_path / "sheet.jsonl"
    _write_sheet(
        sheet,
        [_row("cand-001") | {"files": ["src/widget.py", "src/other.py"]}],
    )
    stdin = StringIO(
        "i\n2\nnull-check\n1\n14\ny\n1\nauth\n2\n3\nn\ndev\nq\n"
    )
    review_sheet(sheet, auditor="niresh", stdin=stdin, stdout=StringIO())
    rows = _load(sheet)
    labels = _row_labels(rows[0])
    assert len(labels) == 2
    assert labels[0]["concern"] == "correctness"
    assert labels[1]["concern"] == "security"
    assert labels[1]["file_path"] == "src/other.py"
    assert labels[1]["line_start"] == 3
