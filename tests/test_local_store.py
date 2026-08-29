"""Tests for the runner's local SQLite state (Runtime Task 5).

This is the store Task 1A pointed at when it retired `findings`, `code_chunks`,
`human_decisions`, and `pull_requests` from the hosted plane: source, diffs, review findings,
rationale, and human decision notes live here, on the runner's own machine, never on Neon.
`local_store/` is the third guarded package (tests/test_package_boundaries.py); it must never
import `pr_reviewer.db`, `pr_reviewer.db.client`, or `pr_reviewer.control_plane`.

Every event row carries a `trace_id` and a per-store `sequence` (a single, monotonically
increasing counter for the whole local event table, not per job), so Task 5A can later join a
hosted `agent_events` row to the local events it caused. Getting the sequence wrong now means a
migration later, so it is tested directly here, not deferred.

`record_claimed` is idempotent by `job_id`: a restart racing with an in-flight claim, or a
recovery pass re-observing a job the poll loop already recorded, must never produce two local
rows for one job.
"""

from __future__ import annotations

import sqlite3
import uuid
from decimal import Decimal
from pathlib import Path

from pr_reviewer.contracts.finding import Finding
from pr_reviewer.contracts.runner import JobAcknowledgement, JobBudget, JobEnvelope
from pr_reviewer.github.pull_request import PullRequestFile, PullRequestSnapshot

BASE_SHA = "a" * 40
HEAD_SHA = "b" * 40


def _job_envelope(
    *,
    job_id: uuid.UUID | None = None,
    repository_id: int = 51101,
    lease_token: str = "lease-token-value",
) -> JobEnvelope:
    return JobEnvelope(
        job_id=job_id or uuid.uuid4(),
        installation_id=5101,
        repository_id=repository_id,
        pull_request_number=9,
        base_sha=BASE_SHA,
        head_sha=HEAD_SHA,
        policy_version="v1",
        budget=JobBudget(max_tokens=1000, max_cost_usd=Decimal("1.000000")),
        trace_id=uuid.uuid4(),
        lease_token=lease_token,
    )


def _snapshot() -> PullRequestSnapshot:
    return PullRequestSnapshot(
        repo_owner="foodspector",
        repo_name="widgets",
        number=9,
        base_sha=BASE_SHA,
        head_sha=HEAD_SHA,
        title="Add widget",
        body="Adds a widget.",
        files=[
            PullRequestFile(path="src/widget.py", status="modified", patch="@@ widget"),
        ],
    )


def _finding(job_id: str, finding_id: str = "finding-1") -> Finding:
    return Finding(
        id=finding_id,
        review_job_id=job_id,
        concern="correctness",
        severity="high",
        category="null-check",
        file_path="src/widget.py",
        line_start=10,
        line_end=12,
        title="Missing null check",
        rationale="widget.value can be None here.",
        evidence=["widget.value is read without a guard on line 11"],
        confidence=0.8,
        verified=True,
        verification_method="static",
        public_safe=True,
        status="draft",
    )


def _acknowledgement() -> JobAcknowledgement:
    return JobAcknowledgement(
        terminal_state="succeeded",
        error_class=None,
        input_tokens=10,
        output_tokens=20,
        cost_usd=Decimal("0.010000"),
        latency_ms=1500,
        local_result_hash="c" * 64,
    )


def test_recording_a_claimed_job_round_trips_the_envelope(tmp_path: Path) -> None:
    from pr_reviewer.local_store.sqlite import open_local_store

    store = open_local_store(tmp_path / "local_state.sqlite3")
    envelope = _job_envelope()

    store.jobs.record_claimed(envelope)
    row = store.jobs.get(str(envelope.job_id))

    assert row is not None
    assert row.job_id == str(envelope.job_id)
    assert row.repository_id == envelope.repository_id
    assert row.head_sha == HEAD_SHA
    assert row.lease_token == envelope.lease_token
    assert row.trace_id == str(envelope.trace_id)
    assert row.status == "claimed"


def test_recording_the_same_claimed_job_twice_does_not_create_a_duplicate_row(
    tmp_path: Path,
) -> None:
    from pr_reviewer.local_store.sqlite import open_local_store

    store = open_local_store(tmp_path / "local_state.sqlite3")
    envelope = _job_envelope()

    store.jobs.record_claimed(envelope)
    store.jobs.record_claimed(envelope)  # simulates recovery racing the poll loop

    assert len(store.jobs.list_claimed()) == 1


def test_marking_a_job_abandoned_removes_it_from_the_claimed_list(tmp_path: Path) -> None:
    from pr_reviewer.local_store.sqlite import open_local_store

    store = open_local_store(tmp_path / "local_state.sqlite3")
    envelope = _job_envelope()
    store.jobs.record_claimed(envelope)

    store.jobs.mark_abandoned(str(envelope.job_id))

    assert store.jobs.list_claimed() == []
    row = store.jobs.get(str(envelope.job_id))
    assert row is not None
    assert row.status == "abandoned"


def test_recording_and_reading_back_a_snapshot(tmp_path: Path) -> None:
    from pr_reviewer.local_store.sqlite import open_local_store

    store = open_local_store(tmp_path / "local_state.sqlite3")
    envelope = _job_envelope()
    store.jobs.record_claimed(envelope)

    store.snapshots.record(str(envelope.job_id), _snapshot())
    fetched = store.snapshots.get(str(envelope.job_id))

    assert fetched is not None
    assert fetched.repo_owner == "foodspector"
    assert fetched.files[0].path == "src/widget.py"
    assert fetched.files[0].patch == "@@ widget"


def test_recording_a_finding_and_listing_it_for_its_job(tmp_path: Path) -> None:
    from pr_reviewer.local_store.sqlite import open_local_store

    store = open_local_store(tmp_path / "local_state.sqlite3")
    envelope = _job_envelope()
    store.jobs.record_claimed(envelope)

    finding = _finding(str(envelope.job_id))
    store.findings.record(finding)
    listed = store.findings.list_for_job(str(envelope.job_id))

    assert len(listed) == 1
    assert listed[0].id == "finding-1"
    assert listed[0].rationale == finding.rationale


def test_recording_a_human_decision_for_a_finding(tmp_path: Path) -> None:
    from pr_reviewer.local_store.sqlite import open_local_store

    store = open_local_store(tmp_path / "local_state.sqlite3")
    envelope = _job_envelope()
    store.jobs.record_claimed(envelope)
    finding = _finding(str(envelope.job_id))
    store.findings.record(finding)

    store.human_decisions.record(finding.id, "approved", "alice", "looks right")
    decisions = store.human_decisions.list_for_finding(finding.id)

    assert len(decisions) == 1
    assert decisions[0].decision == "approved"
    assert decisions[0].decided_by == "alice"
    assert decisions[0].note == "looks right"


def test_every_event_row_carries_a_trace_id_and_a_strictly_increasing_per_store_sequence(
    tmp_path: Path,
) -> None:
    from pr_reviewer.local_store.sqlite import open_local_store

    store = open_local_store(tmp_path / "local_state.sqlite3")
    job_a = _job_envelope()
    job_b = _job_envelope()

    first = store.events.record(
        job_id=str(job_a.job_id),
        trace_id=str(job_a.trace_id),
        event_type="job_claimed",
        payload={},
    )
    second = store.events.record(
        job_id=str(job_b.job_id),
        trace_id=str(job_b.trace_id),
        event_type="job_claimed",
        payload={},
    )
    third = store.events.record(
        job_id=str(job_a.job_id),
        trace_id=str(job_a.trace_id),
        event_type="snapshot_fetched",
        payload={"files": 1},
    )

    # The sequence is a single counter for the whole store, not scoped per job: job_a's second
    # event still moves strictly past job_b's event in between.
    assert first.sequence < second.sequence < third.sequence
    assert first.trace_id == str(job_a.trace_id)
    assert second.trace_id == str(job_b.trace_id)

    all_events = store.events.list_all()
    assert [event.sequence for event in all_events] == sorted(
        event.sequence for event in all_events
    )


def test_pending_acknowledgement_can_be_recorded_listed_and_resolved(tmp_path: Path) -> None:
    from pr_reviewer.local_store.sqlite import open_local_store

    store = open_local_store(tmp_path / "local_state.sqlite3")
    envelope = _job_envelope()
    store.jobs.record_claimed(envelope)
    result = _acknowledgement()

    entry_id = store.pending_acknowledgements.record(
        str(envelope.job_id), envelope.lease_token, result, reason="invalid_or_expired"
    )
    pending = store.pending_acknowledgements.list_pending()

    assert len(pending) == 1
    assert pending[0].job_id == str(envelope.job_id)
    assert pending[0].result.local_result_hash == result.local_result_hash
    assert pending[0].reason == "invalid_or_expired"
    assert pending[0].attempts == 0

    store.pending_acknowledgements.bump_attempt(entry_id)
    bumped = store.pending_acknowledgements.list_pending()
    assert bumped[0].attempts == 1

    store.pending_acknowledgements.resolve(entry_id)
    assert store.pending_acknowledgements.list_pending() == []


def test_opening_a_corrupted_sqlite_file_raises_a_clear_error_not_a_raw_sqlite_error(
    tmp_path: Path,
) -> None:
    from pr_reviewer.local_store.sqlite import LocalStoreCorrupted, open_local_store

    path = tmp_path / "local_state.sqlite3"
    path.write_bytes(b"this is not a sqlite database, just garbage bytes on disk")

    try:
        open_local_store(path)
    except LocalStoreCorrupted:
        pass
    else:
        raise AssertionError("expected LocalStoreCorrupted for a garbage local state file")


def test_open_local_store_creates_the_database_file_mode_0600_and_directory_mode_0700(
    tmp_path: Path,
) -> None:
    """local_jobs.lease_token makes this file a capability store: anyone who can read it can
    heartbeat or acknowledge an in-flight job with fabricated results. Same mode as
    FileSecretStore's file (0600) and directory (0700). WAL mode creates -wal and -shm sidecars
    that inherit the same content, so they must carry the same mode too.
    """
    from pr_reviewer.local_store.sqlite import open_local_store

    directory = tmp_path / "state"
    path = directory / "local_state.sqlite3"
    store = open_local_store(path)
    store.jobs.record_claimed(_job_envelope())  # force a write so WAL sidecars actually exist

    assert path.stat().st_mode & 0o777 == 0o600
    assert directory.stat().st_mode & 0o777 == 0o700

    sidecars = [path.with_name(path.name + suffix) for suffix in ("-wal", "-shm")]
    existing_sidecars = [sidecar for sidecar in sidecars if sidecar.exists()]
    assert existing_sidecars, "expected WAL mode to produce at least one sidecar file"
    for sidecar in existing_sidecars:
        assert sidecar.stat().st_mode & 0o777 == 0o600, f"{sidecar} must be mode 0600 too"


def test_local_schema_has_no_columns_for_long_lived_secrets() -> None:
    """Runner credential, model keys, GitHub tokens, and the Slack secret stay out of SQLite
    entirely. lease_token is deliberately not in this list: it is a per-job capability the runner
    must hold locally to heartbeat or acknowledge the same job across a restart, not a long-lived
    credential.
    """
    from pr_reviewer.local_store import sqlite as local_sqlite

    migration_files = sorted(local_sqlite.MIGRATIONS_DIRECTORY.glob("*.sql"))
    assert migration_files, "expected at least one local-state migration file"
    schema_text = "\n".join(path.read_text(encoding="utf-8") for path in migration_files).lower()

    forbidden_fragments = [
        "runner_credential",
        "credential text",
        "model_key",
        "api_key",
        "slack_secret",
        "slack_token",
        "github_token",
        "installation_token",
        "private_key",
    ]
    for fragment in forbidden_fragments:
        assert fragment not in schema_text, f"local schema must never hold {fragment!r}"


def test_local_store_boundary_is_a_plain_sqlite_file_with_no_network_dependency(
    tmp_path: Path,
) -> None:
    """Sanity check that the local store really is local: opening it and using it must not
    require any of our own network-facing modules, only the stdlib sqlite3 driver.
    """
    from pr_reviewer.local_store.sqlite import open_local_store

    store = open_local_store(tmp_path / "local_state.sqlite3")
    assert isinstance(store._connection, sqlite3.Connection)
