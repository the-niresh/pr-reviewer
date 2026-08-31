"""Local SQLite state for the installed runner (Runtime Task 5).

This is where source, diffs, review findings, rationale, and human decision notes live -- the
exact data Task 1A retired off the hosted plane's findings, code_chunks, human_decisions, and
pull_requests tables, because the control plane must not be able to hand any of it to an attacker.
`local_store/` is a guarded package (tests/test_package_boundaries.py): it must never import
pr_reviewer.db, pr_reviewer.db.client, or pr_reviewer.control_plane.

open_local_store enforces file mode 0600 and directory mode 0700 on the SQLite file itself (and
its -wal/-shm sidecars, since WAL mode is enabled here) because local_jobs.lease_token is a
capability: anyone who can read this file can heartbeat or acknowledge an in-flight job with
fabricated results, the same reason runner/secrets.py's FileSecretStore locks its files down.

Every local_events row gets a trace_id and a per-store sequence (the table's own autoincrement
rowid, one counter across every job) so Task 5A can later join a hosted agent_events row to the
local events it caused.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from pr_reviewer.contracts.finding import Finding
from pr_reviewer.contracts.runner import JobAcknowledgement, JobBudget, JobEnvelope
from pr_reviewer.github.pull_request import PullRequestFile, PullRequestSnapshot
from pr_reviewer.observability.trace import LocalTrace, LocalTraceEvent

MIGRATIONS_DIRECTORY = Path(__file__).with_name("migrations")

LocalJobStatus = Literal["claimed", "completed", "abandoned"]
PendingAcknowledgementReason = Literal["invalid_or_expired", "network_unreachable"]


class LocalStoreCorrupted(Exception):
    """path exists but is not a readable pr-reviewer local store."""


@dataclass(frozen=True)
class LocalJob:
    job_id: str
    installation_id: int
    repository_id: int
    pull_request_number: int
    base_sha: str
    head_sha: str
    policy_version: str
    budget: JobBudget
    trace_id: str
    lease_token: str
    status: str
    claimed_at: str


@dataclass(frozen=True)
class LocalHumanDecision:
    id: int
    finding_id: str
    decision: str
    decided_by: str
    note: str | None
    created_at: str


@dataclass(frozen=True)
class LocalEvent:
    sequence: int
    job_id: str | None
    trace_id: str
    event_type: str
    payload: dict[str, Any]
    created_at: str


@dataclass(frozen=True)
class PendingAcknowledgement:
    id: int
    job_id: str
    lease_token: str
    result: JobAcknowledgement
    reason: str
    attempts: int
    created_at: str


class LocalJobStore:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def record_claimed(self, job: JobEnvelope) -> None:
        self._connection.execute(
            """
            insert or ignore into local_jobs (
              job_id, installation_id, repository_id, pull_request_number, base_sha, head_sha,
              policy_version, budget_max_tokens, budget_max_cost_usd, trace_id, lease_token,
              status
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'claimed')
            """,
            (
                str(job.job_id),
                job.installation_id,
                job.repository_id,
                job.pull_request_number,
                job.base_sha,
                job.head_sha,
                job.policy_version,
                job.budget.max_tokens,
                str(job.budget.max_cost_usd),
                str(job.trace_id),
                job.lease_token,
            ),
        )
        self._connection.commit()

    def get(self, job_id: str) -> LocalJob | None:
        row = self._connection.execute(
            "select * from local_jobs where job_id = ?", (job_id,)
        ).fetchone()
        return None if row is None else _row_to_local_job(row)

    def list_claimed(self) -> list[LocalJob]:
        rows = self._connection.execute(
            "select * from local_jobs where status = 'claimed' order by claimed_at"
        ).fetchall()
        return [_row_to_local_job(row) for row in rows]

    def mark_abandoned(self, job_id: str) -> None:
        self._connection.execute(
            "update local_jobs set status = 'abandoned' where job_id = ?", (job_id,)
        )
        self._connection.commit()

    def mark_completed(self, job_id: str) -> None:
        self._connection.execute(
            "update local_jobs set status = 'completed' where job_id = ?", (job_id,)
        )
        self._connection.commit()


def _row_to_local_job(row: sqlite3.Row) -> LocalJob:
    return LocalJob(
        job_id=str(row["job_id"]),
        installation_id=int(row["installation_id"]),
        repository_id=int(row["repository_id"]),
        pull_request_number=int(row["pull_request_number"]),
        base_sha=str(row["base_sha"]),
        head_sha=str(row["head_sha"]),
        policy_version=str(row["policy_version"]),
        budget=JobBudget(
            max_tokens=int(row["budget_max_tokens"]),
            max_cost_usd=Decimal(str(row["budget_max_cost_usd"])),
        ),
        trace_id=str(row["trace_id"]),
        lease_token=str(row["lease_token"]),
        status=str(row["status"]),
        claimed_at=str(row["claimed_at"]),
    )


class LocalSnapshotStore:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def record(self, job_id: str, snapshot: PullRequestSnapshot) -> None:
        files_json = json.dumps([file.model_dump(mode="json") for file in snapshot.files])
        self._connection.execute(
            """
            insert or replace into local_snapshots (
              job_id, repo_owner, repo_name, number, base_sha, head_sha, title, body, files_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                snapshot.repo_owner,
                snapshot.repo_name,
                snapshot.number,
                snapshot.base_sha,
                snapshot.head_sha,
                snapshot.title,
                snapshot.body,
                files_json,
            ),
        )
        self._connection.commit()

    def get(self, job_id: str) -> PullRequestSnapshot | None:
        row = self._connection.execute(
            "select * from local_snapshots where job_id = ?", (job_id,)
        ).fetchone()
        if row is None:
            return None
        files = [PullRequestFile.model_validate(item) for item in json.loads(row["files_json"])]
        return PullRequestSnapshot(
            repo_owner=str(row["repo_owner"]),
            repo_name=str(row["repo_name"]),
            number=int(row["number"]),
            base_sha=str(row["base_sha"]),
            head_sha=str(row["head_sha"]),
            title=str(row["title"]),
            body=str(row["body"]),
            files=files,
        )


class LocalFindingStore:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def record(self, finding: Finding) -> None:
        self._connection.execute(
            """
            insert or replace into local_findings (
              id, job_id, concern, severity, category, file_path, line_start, line_end, title,
              rationale, evidence_json, confidence, verified, verification_method, public_safe,
              status
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                finding.id,
                finding.review_job_id,
                finding.concern,
                finding.severity,
                finding.category,
                finding.file_path,
                finding.line_start,
                finding.line_end,
                finding.title,
                finding.rationale,
                json.dumps(finding.evidence),
                finding.confidence,
                int(finding.verified),
                finding.verification_method,
                int(finding.public_safe),
                finding.status,
            ),
        )
        self._connection.commit()

    def list_for_job(self, job_id: str) -> list[Finding]:
        rows = self._connection.execute(
            "select * from local_findings where job_id = ? order by created_at", (job_id,)
        ).fetchall()
        return [_row_to_finding(row) for row in rows]


def _row_to_finding(row: sqlite3.Row) -> Finding:
    return Finding(
        id=str(row["id"]),
        review_job_id=str(row["job_id"]),
        concern=row["concern"],
        severity=row["severity"],
        category=str(row["category"]),
        file_path=str(row["file_path"]),
        line_start=int(row["line_start"]),
        line_end=int(row["line_end"]),
        title=str(row["title"]),
        rationale=str(row["rationale"]),
        evidence=list(json.loads(row["evidence_json"])),
        confidence=float(row["confidence"]),
        verified=bool(row["verified"]),
        verification_method=row["verification_method"],
        public_safe=bool(row["public_safe"]),
        status=row["status"],
    )


class LocalHumanDecisionStore:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def record(self, finding_id: str, decision: str, decided_by: str, note: str | None) -> None:
        self._connection.execute(
            "insert into local_human_decisions (finding_id, decision, decided_by, note) "
            "values (?, ?, ?, ?)",
            (finding_id, decision, decided_by, note),
        )
        self._connection.commit()

    def list_for_finding(self, finding_id: str) -> list[LocalHumanDecision]:
        rows = self._connection.execute(
            "select * from local_human_decisions where finding_id = ? order by created_at",
            (finding_id,),
        ).fetchall()
        return [
            LocalHumanDecision(
                id=int(row["id"]),
                finding_id=str(row["finding_id"]),
                decision=str(row["decision"]),
                decided_by=str(row["decided_by"]),
                note=row["note"],
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]


class LocalEventStore:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def record(
        self, *, job_id: str | None, trace_id: str, event_type: str, payload: dict[str, Any]
    ) -> LocalEvent:
        cursor = self._connection.execute(
            "insert into local_events (job_id, trace_id, event_type, payload_json) "
            "values (?, ?, ?, ?)",
            (job_id, trace_id, event_type, json.dumps(payload)),
        )
        self._connection.commit()
        row = self._connection.execute(
            "select * from local_events where sequence = ?", (cursor.lastrowid,)
        ).fetchone()
        assert row is not None
        return _row_to_event(row)

    def list_all(self) -> list[LocalEvent]:
        rows = self._connection.execute("select * from local_events order by sequence").fetchall()
        return [_row_to_event(row) for row in rows]

    def list_for_trace(self, trace_id: str) -> list[LocalEvent]:
        """The local half of Runtime Task 5A's trace join. trace_id, not job_id, is the filter:
        every local_events row carries trace_id, but job_id is nullable, so trace_id is the one
        column guaranteed to scope every event this store could ever hold for a given trace.
        """
        rows = self._connection.execute(
            "select * from local_events where trace_id = ? order by sequence", (trace_id,)
        ).fetchall()
        return [_row_to_event(row) for row in rows]


def _row_to_event(row: sqlite3.Row) -> LocalEvent:
    return LocalEvent(
        sequence=int(row["sequence"]),
        job_id=row["job_id"],
        trace_id=str(row["trace_id"]),
        event_type=str(row["event_type"]),
        payload=dict(json.loads(row["payload_json"])),
        created_at=str(row["created_at"]),
    )


class PendingAcknowledgementStore:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def record(
        self,
        job_id: str,
        lease_token: str,
        result: JobAcknowledgement,
        reason: PendingAcknowledgementReason,
    ) -> int:
        cursor = self._connection.execute(
            "insert into local_pending_acknowledgements (job_id, lease_token, result_json, "
            "reason) values (?, ?, ?, ?)",
            (job_id, lease_token, json.dumps(result.model_dump(mode="json")), reason),
        )
        self._connection.commit()
        assert cursor.lastrowid is not None
        return int(cursor.lastrowid)

    def list_pending(self) -> list[PendingAcknowledgement]:
        rows = self._connection.execute(
            "select * from local_pending_acknowledgements order by created_at"
        ).fetchall()
        return [_row_to_pending(row) for row in rows]

    def resolve(self, entry_id: int) -> None:
        self._connection.execute(
            "delete from local_pending_acknowledgements where id = ?", (entry_id,)
        )
        self._connection.commit()

    def bump_attempt(self, entry_id: int) -> None:
        self._connection.execute(
            "update local_pending_acknowledgements set attempts = attempts + 1 where id = ?",
            (entry_id,),
        )
        self._connection.commit()


def _row_to_pending(row: sqlite3.Row) -> PendingAcknowledgement:
    return PendingAcknowledgement(
        id=int(row["id"]),
        job_id=str(row["job_id"]),
        lease_token=str(row["lease_token"]),
        result=JobAcknowledgement.model_validate(json.loads(row["result_json"])),
        reason=str(row["reason"]),
        attempts=int(row["attempts"]),
        created_at=str(row["created_at"]),
    )


class LocalStore:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self.jobs = LocalJobStore(connection)
        self.snapshots = LocalSnapshotStore(connection)
        self.findings = LocalFindingStore(connection)
        self.human_decisions = LocalHumanDecisionStore(connection)
        self.events = LocalEventStore(connection)
        self.pending_acknowledgements = PendingAcknowledgementStore(connection)

    @property
    def connection(self) -> sqlite3.Connection:
        return self._connection

    def close(self) -> None:
        self._connection.close()

    def fetch_trace(self, job_id: str) -> LocalTrace | None:
        """None means this store has no local_jobs row for job_id -- distinct from a LocalTrace
        with zero events, which means the job was claimed here but nothing has been recorded for
        it yet. Looking job_id up first, rather than requiring a caller-supplied trace_id, keeps
        job_id the one join key a caller of this module needs to know at all.
        """
        job = self.jobs.get(job_id)
        if job is None:
            return None
        events = self.events.list_for_trace(job.trace_id)
        return LocalTrace(
            trace_id=job.trace_id,
            events=tuple(
                LocalTraceEvent(
                    sequence=event.sequence,
                    kind=event.event_type,
                    payload=event.payload,
                    created_at=event.created_at,
                )
                for event in events
            ),
        )


def open_local_store(path: str | Path) -> LocalStore:
    resolved = Path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(resolved.parent, 0o700)

    connection = sqlite3.connect(str(resolved))
    connection.row_factory = sqlite3.Row
    os.chmod(resolved, 0o600)

    try:
        connection.execute("pragma journal_mode=WAL")
        _run_migrations(connection)
    except sqlite3.DatabaseError as exc:
        connection.close()
        raise LocalStoreCorrupted(f"{resolved} is not a readable local store: {exc}") from exc

    _chmod_if_exists(resolved.with_name(resolved.name + "-wal"))
    _chmod_if_exists(resolved.with_name(resolved.name + "-shm"))

    return LocalStore(connection)


def _chmod_if_exists(path: Path) -> None:
    if path.exists():
        os.chmod(path, 0o600)


def _run_migrations(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        create table if not exists schema_migrations (
          filename text primary key,
          checksum text not null,
          applied_at text not null default (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        )
        """
    )
    connection.commit()

    applied = {
        str(row["filename"]): str(row["checksum"])
        for row in connection.execute("select filename, checksum from schema_migrations")
    }
    for migration_path in sorted(MIGRATIONS_DIRECTORY.glob("*.sql")):
        sql = migration_path.read_text(encoding="utf-8")
        checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
        applied_checksum = applied.get(migration_path.name)
        if applied_checksum is not None:
            if applied_checksum != checksum:
                raise LocalStoreCorrupted(f"migration checksum mismatch: {migration_path.name}")
            continue

        connection.executescript(sql)
        connection.execute(
            "insert into schema_migrations (filename, checksum) values (?, ?)",
            (migration_path.name, checksum),
        )
        connection.commit()
