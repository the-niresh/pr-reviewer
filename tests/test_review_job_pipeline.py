"""Failing tests that wire the runner daemon to the simple workflow engine (Task 16).

The daemon still owns queue-shaped local_jobs (claimed/completed/abandoned). The engine
owns step completion. A cancelled lease mid-pipeline must stop at the next step boundary
and record cancelled, not a dead lease. Imports of new modules stay inside test bodies.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from pr_reviewer.contracts.runner import (
    JobAcknowledgement,
    JobBudget,
    JobEnvelope,
    LeaseState,
    NoJob,
)
from pr_reviewer.local_store.sqlite import LocalStore

HEAD_SHA = "a" * 40
BASE_SHA = "c" * 40
STEPS = (
    "fetch",
    "baseline_review",
    "retrieval",
    "verification",
    "routing",
    "storage",
)


def _job_envelope(*, job_id: uuid.UUID | None = None) -> JobEnvelope:
    return JobEnvelope(
        job_id=job_id or uuid.uuid4(),
        installation_id=1601,
        repository_id=16001,
        pull_request_number=16,
        base_sha=BASE_SHA,
        head_sha=HEAD_SHA,
        policy_version="v1",
        budget=JobBudget(max_tokens=1000, max_cost_usd=Decimal("1.000000")),
        trace_id=uuid.uuid4(),
        lease_token="lease-token-value",
    )


class FakeRunnerClient:
    def __init__(self, envelope: JobEnvelope | None = None) -> None:
        self.envelope = envelope
        self.heartbeat_outcome = "active"
        self.heartbeat_calls: list[tuple[str, str]] = []
        self.acknowledge_calls: list[tuple[str, str, JobAcknowledgement]] = []
        self.claim_calls = 0

    def set_credential(self, credential: str) -> None:
        del credential

    def claim(self) -> JobEnvelope | NoJob:
        self.claim_calls += 1
        if self.envelope is None:
            return NoJob()
        claimed = self.envelope
        self.envelope = None
        return claimed

    def heartbeat(self, job_id: str, lease_token: str) -> LeaseState:
        self.heartbeat_calls.append((job_id, lease_token))
        if self.heartbeat_outcome == "cancelled":
            return LeaseState(status="cancelled")
        return LeaseState(status="active")

    def acknowledge(self, job_id: str, lease_token: str, result: JobAcknowledgement) -> None:
        self.acknowledge_calls.append((job_id, lease_token, result))


def _store(tmp_path: Path) -> LocalStore:
    from pr_reviewer.local_store.sqlite import open_local_store

    return open_local_store(tmp_path / "local_state.sqlite3")


def _engine(
    local_store: LocalStore,
    counts: dict[str, int],
    *,
    heartbeat: Any = None,
    crash_before: str | None = None,
    crashed: dict[str, bool] | None = None,
) -> Any:
    from pr_reviewer.workflow.simple_engine import SimpleEngine
    from pr_reviewer.workflow.store import SqliteWorkflowStore

    crashed = crashed if crashed is not None else {"done": False}

    def make(name: str) -> Any:
        def handler(_inp: Any, _outputs: dict[str, object]) -> object:
            if name == crash_before and not crashed["done"]:
                crashed["done"] = True
                raise RuntimeError(f"crash before {name}")
            counts[name] = counts.get(name, 0) + 1
            if name == "baseline_review":
                counts["model_calls"] = counts.get("model_calls", 0) + 1
            if name == "storage":
                counts["posts"] = counts.get("posts", 0) + 1
                counts["notifies"] = counts.get("notifies", 0) + 1
            return name

        return handler

    handlers = {name: make(name) for name in STEPS}
    return SimpleEngine(
        store=SqliteWorkflowStore(local_store.connection),
        fetch=handlers["fetch"],
        baseline_review=handlers["baseline_review"],
        retrieval=handlers["retrieval"],
        verification=handlers["verification"],
        routing=handlers["routing"],
        storage=handlers["storage"],
        heartbeat=heartbeat,
    )


def test_daemon_process_once_runs_the_simple_engine_and_acks(tmp_path: Path) -> None:
    from pr_reviewer.runner.daemon import RunnerDaemon

    envelope = _job_envelope()
    client = FakeRunnerClient(envelope)
    store = _store(tmp_path)
    counts: dict[str, int] = {}
    engine = _engine(store, counts)
    daemon = RunnerDaemon(runner_client=client, local_store=store, review=engine)

    daemon.process_once()

    assert [counts[name] for name in STEPS] == [1] * 6
    assert len(client.acknowledge_calls) == 1
    ack = client.acknowledge_calls[0][2]
    assert ack.terminal_state == "succeeded"
    remaining = store.jobs.list_claimed()
    assert remaining == []


def test_daemon_recover_resumes_without_a_second_model_call(tmp_path: Path) -> None:
    from pr_reviewer.runner.daemon import RunnerDaemon

    envelope = _job_envelope()
    store = _store(tmp_path)
    store.jobs.record_claimed(envelope)
    counts: dict[str, int] = {}
    crashed = {"done": False}
    engine = _engine(store, counts, crash_before="retrieval", crashed=crashed)
    with pytest.raises(RuntimeError):
        engine.review(envelope)
    assert counts.get("fetch", 0) == 1
    assert counts.get("baseline_review", 0) == 1
    assert counts.get("model_calls", 0) == 1
    assert counts.get("retrieval", 0) == 0

    client = FakeRunnerClient()
    daemon = RunnerDaemon(runner_client=client, local_store=store, review=engine)
    daemon.recover()

    assert counts["retrieval"] == 1
    assert counts["model_calls"] == 1
    assert counts["posts"] == 1
    assert counts["notifies"] == 1
    assert len(client.acknowledge_calls) == 1


def test_closed_pr_mid_pipeline_stops_at_the_next_boundary(tmp_path: Path) -> None:
    from pr_reviewer.runner.daemon import RunnerDaemon

    envelope = _job_envelope()
    client = FakeRunnerClient(envelope)
    store = _store(tmp_path)
    counts: dict[str, int] = {}
    beats = {"n": 0}

    def heartbeat(_inp: Any) -> LeaseState:
        beats["n"] += 1
        if beats["n"] >= 2:
            return LeaseState(status="cancelled")
        return LeaseState(status="active")

    engine = _engine(store, counts, heartbeat=heartbeat)
    daemon = RunnerDaemon(runner_client=client, local_store=store, review=engine)
    daemon.process_once()

    assert counts.get("fetch", 0) == 1
    assert counts.get("baseline_review", 0) == 0
    assert counts.get("model_calls", 0) == 0
    assert len(client.acknowledge_calls) == 1
    ack = client.acknowledge_calls[0][2]
    assert ack.terminal_state == "failed"
    assert ack.error_class == "cancelled"
