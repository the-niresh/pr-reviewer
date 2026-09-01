"""Per-agent reasoning is persisted locally for live reviews."""

from __future__ import annotations

from pathlib import Path

import pytest

from pr_reviewer.local_store.review_log import ReviewLogStore, default_review_log_path
from pr_reviewer.reviewer.specialists import SPECIALIST_CONCERNS


def test_append_and_list_reasoning_records(tmp_path: Path) -> None:
    store = ReviewLogStore(tmp_path / "review_log.json")
    first = store.append_reasoning("review-1", "security", "Checking auth boundaries")
    second = store.append_reasoning("review-1", "correctness", "Tracing control flow")

    records = store.list_reasoning("review-1")
    assert first.sequence == 1
    assert second.sequence == 2
    assert [record.concern for record in records] == ["security", "correctness"]


def test_reasoning_log_survives_reload(tmp_path: Path) -> None:
    path = tmp_path / "review_log.json"
    first = ReviewLogStore(path)
    first.append_reasoning("review-42", "docs", "Checking README drift")

    second = ReviewLogStore(path)
    records = second.list_reasoning("review-42")
    assert len(records) == 1
    assert records[0].reasoning == "Checking README drift"


def test_append_reasoning_rejects_empty_text(tmp_path: Path) -> None:
    store = ReviewLogStore(tmp_path / "review_log.json")
    with pytest.raises(ValueError):
        store.append_reasoning("review-1", "tests", "   ")


def test_default_review_log_path_uses_config_dir() -> None:
    assert default_review_log_path(Path("/tmp/example")).name == "review_log.json"


def test_reasoning_records_keep_specialist_order(tmp_path: Path) -> None:
    store = ReviewLogStore(tmp_path / "review_log.json")
    for concern in SPECIALIST_CONCERNS:
        store.append_reasoning("review-1", concern, f"{concern} reasoning")

    assert [record.concern for record in store.list_reasoning("review-1")] == list(
        SPECIALIST_CONCERNS
    )
