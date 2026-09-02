"""Persist per-agent reasoning for live reviews on the runner machine."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AgentReasoningRecord:
    concern: str
    reasoning: str
    sequence: int


class ReviewLogStore:
    """JSON-backed append-only log of per-agent reasoning for one review run."""

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def append_reasoning(
        self, review_id: str, concern: str, reasoning: str
    ) -> AgentReasoningRecord:
        cleaned = reasoning.strip()
        if not concern.strip():
            raise ValueError("concern must not be empty")
        if not cleaned:
            raise ValueError("reasoning must not be empty")
        payload = self._read_payload()
        reviews = payload.setdefault("reviews", {})
        review = reviews.setdefault(review_id, {"entries": []})
        entries = review.setdefault("entries", [])
        if not isinstance(entries, list):
            raise ValueError("review log entries must be a JSON array")
        record = AgentReasoningRecord(
            concern=concern.strip(),
            reasoning=cleaned,
            sequence=len(entries) + 1,
        )
        entries.append(
            {
                "concern": record.concern,
                "reasoning": record.reasoning,
                "sequence": record.sequence,
            }
        )
        self._write_payload(payload)
        return record

    def list_reasoning(self, review_id: str) -> tuple[AgentReasoningRecord, ...]:
        payload = self._read_payload()
        reviews = payload.get("reviews", {})
        if not isinstance(reviews, dict):
            raise ValueError("review log must be a JSON object")
        review = reviews.get(review_id, {})
        if not isinstance(review, dict):
            raise ValueError("review entry must be a JSON object")
        entries = review.get("entries", [])
        if not isinstance(entries, list):
            raise ValueError("review log entries must be a JSON array")
        records: list[AgentReasoningRecord] = []
        for raw in entries:
            if not isinstance(raw, dict):
                raise ValueError("review log entry must be a JSON object")
            records.append(
                AgentReasoningRecord(
                    concern=str(raw["concern"]),
                    reasoning=str(raw["reasoning"]),
                    sequence=int(raw["sequence"]),
                )
            )
        return tuple(records)

    def append_review_summary(self, payload: dict[str, object]) -> None:
        stored = dict(payload)
        stored["created_at"] = datetime.now(UTC).isoformat()
        root = self._read_payload()
        summaries = root.setdefault("review_summaries", [])
        if not isinstance(summaries, list):
            raise ValueError("review summaries must be a JSON array")
        review_job_id = stored.get("review_job_id")
        summaries[:] = [
            item
            for item in summaries
            if not isinstance(item, dict) or item.get("review_job_id") != review_job_id
        ]
        summaries.append(stored)
        self._write_payload(root)

    def list_review_summaries(self) -> tuple[dict[str, Any], ...]:
        root = self._read_payload()
        summaries = root.get("review_summaries", [])
        if not isinstance(summaries, list):
            raise ValueError("review summaries must be a JSON array")
        result = []
        for item in summaries:
            if not isinstance(item, dict):
                raise ValueError("review summary must be a JSON object")
            result.append(dict(item))
        return tuple(result)

    def _read_payload(self) -> dict[str, Any]:
        if not self._path.is_file():
            return {"reviews": {}}
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("review log must be a JSON object")
        return raw

    def _write_payload(self, payload: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def default_review_log_path(config_dir: Path | None = None) -> Path:
    root = config_dir or (Path.home() / ".config" / "pr-reviewer")
    return root / "review_log.json"
