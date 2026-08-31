"""Append-only human feedback with hashes. Never updates prompts from one decision."""

from __future__ import annotations

import hashlib
from pathlib import Path

from pr_reviewer.contracts.finding import Finding
from pr_reviewer.contracts.runner import JobBudget, JobEnvelope

BASE_SHA = "a" * 40
HEAD_SHA = "b" * 40


def _envelope() -> JobEnvelope:
    from decimal import Decimal
    from uuid import uuid4

    return JobEnvelope(
        job_id=uuid4(),
        installation_id=5101,
        repository_id=51101,
        pull_request_number=9,
        base_sha=BASE_SHA,
        head_sha=HEAD_SHA,
        policy_version="v1",
        budget=JobBudget(max_tokens=1000, max_cost_usd=Decimal("1.000000")),
        trace_id=uuid4(),
        lease_token="lease-token-value",
    )


def _finding(job_id: str) -> Finding:
    return Finding(
        id="finding-1",
        review_job_id=job_id,
        concern="security",
        severity="high",
        category="sql-injection",
        file_path="src/auth.ts",
        line_start=42,
        line_end=42,
        title="SQL injection in auth.ts line 42",
        rationale="User input reaches SQL text.",
        evidence=["src/auth.ts:42"],
        confidence=0.9,
        verified=True,
        verification_method="static",
        public_safe=False,
        status="queued_for_human",
    )


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_human_feedback_is_append_only_with_actor_action_note_and_hashes(tmp_path: Path) -> None:
    from pr_reviewer.local_store.sqlite import open_local_store
    from pr_reviewer.notifications.feedback import record_human_feedback

    store = open_local_store(tmp_path / "local_state.sqlite3")
    envelope = _envelope()
    store.jobs.record_claimed(envelope)
    finding = _finding(str(envelope.job_id))
    store.findings.record(finding)

    original = _hash(finding.model_dump_json())
    edited = _hash(finding.model_dump_json() + ":edited")
    record_human_feedback(
        store,
        finding_id=finding.id,
        actor="alice",
        action="edited",
        note="tighten the title",
        original_hash=original,
        edited_hash=edited,
    )
    record_human_feedback(
        store,
        finding_id=finding.id,
        actor="bob",
        action="approved",
        note="ok",
        original_hash=edited,
        edited_hash=edited,
    )
    rows = store.human_decisions.list_for_finding(finding.id)
    assert len(rows) == 2
    assert rows[0].decided_by == "alice"
    assert rows[0].decision == "edited"
    assert rows[0].note == "tighten the title"
    assert rows[0].original_hash == original
    assert rows[0].edited_hash == edited
    assert rows[1].decided_by == "bob"
    assert rows[1].decision == "approved"
    assert rows[0].id != rows[1].id


def test_human_feedback_does_not_update_prompts(tmp_path: Path) -> None:
    from pr_reviewer.local_store.sqlite import open_local_store
    from pr_reviewer.notifications.feedback import record_human_feedback

    store = open_local_store(tmp_path / "local_state.sqlite3")
    envelope = _envelope()
    store.jobs.record_claimed(envelope)
    finding = _finding(str(envelope.job_id))
    store.findings.record(finding)

    prompts = {"review": "v1-template"}
    digest = _hash(finding.model_dump_json())
    record_human_feedback(
        store,
        finding_id=finding.id,
        actor="alice",
        action="approved",
        note="ship it",
        original_hash=digest,
        edited_hash=digest,
        prompts=prompts,
    )
    assert prompts == {"review": "v1-template"}
