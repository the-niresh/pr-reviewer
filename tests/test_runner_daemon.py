"""Tests for the installed runner daemon (Runtime Task 5).

RunnerDaemon is the thing that turns the runner from a script into an installed product: it
recovers state after a restart, replays work the control plane could not previously accept, and
stops cooperatively instead of being killed. It is a pure orchestrator over two collaborators it
never constructs for itself in tests -- a RunnerClient-shaped fake (see `FakeRunnerClient` below)
and a real LocalStore backed by a temp SQLite file -- so these tests exercise real recovery and
real persistence logic without a network or a control-plane process.

The hardest case here is restart recovery when the control plane cannot be reached at all, which
is a third outcome distinct from "lease is active" and "lease is invalid_or_expired": recovery
must leave an unreachable job's local status untouched, because neither resuming it (it might
already be re-claimed by another runner) nor abandoning it (the control plane never actually said
so) is safe on unreachable-network evidence alone.

`RunnerClient.acknowledge` raises JobProtocolDenied when the control plane rejects a lease.
complete_job persists the result, then re-claims. NoJob marks that stored result terminal.
A network failure still persists a pending acknowledgement and re-raises.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import uuid
from decimal import Decimal
from pathlib import Path

import httpx

from pr_reviewer.contracts.runner import (
    JobAcknowledgement,
    JobBudget,
    JobEnvelope,
    JobProtocolDenied,
    LeaseState,
    NoJob,
)
from pr_reviewer.local_store.sqlite import LocalStore

BASE_SHA = "a" * 40
HEAD_SHA = "b" * 40


def _job_envelope(
    *,
    job_id: uuid.UUID | None = None,
    lease_token: str = "lease-token-value",
) -> JobEnvelope:
    return JobEnvelope(
        job_id=job_id or uuid.uuid4(),
        installation_id=6101,
        repository_id=61101,
        pull_request_number=3,
        base_sha=BASE_SHA,
        head_sha=HEAD_SHA,
        policy_version="v1",
        budget=JobBudget(max_tokens=1000, max_cost_usd=Decimal("1.000000")),
        trace_id=uuid.uuid4(),
        lease_token=lease_token,
    )


def _acknowledgement() -> JobAcknowledgement:
    return JobAcknowledgement(
        terminal_state="succeeded",
        error_class=None,
        input_tokens=5,
        output_tokens=7,
        cost_usd=Decimal("0.005000"),
        latency_ms=900,
        local_result_hash="d" * 64,
    )


class FakeRunnerClient:
    """A RunnerClient-shaped fake. heartbeat_outcome and ack_outcome are pre-programmed per test
    so a daemon test never has to spin up a real HTTP server or a control-plane process.
    """

    def __init__(
        self,
        *,
        heartbeat_outcome: str = "active",
        ack_outcome: str = "succeed",
    ) -> None:
        self.heartbeat_outcome = heartbeat_outcome
        self.ack_outcome = ack_outcome
        self.heartbeat_calls: list[tuple[str, str]] = []
        self.acknowledge_calls: list[tuple[str, str, JobAcknowledgement]] = []
        self.claim_calls = 0
        self._credential = "runner-credential"

    def set_credential(self, credential: str) -> None:
        self._credential = credential

    def claim(self) -> NoJob:
        self.claim_calls += 1
        return NoJob()

    def heartbeat(self, job_id: str, lease_token: str) -> LeaseState:
        self.heartbeat_calls.append((job_id, lease_token))
        if self.heartbeat_outcome == "unreachable":
            raise httpx.ConnectError("connection refused")
        if self.heartbeat_outcome == "invalid_or_expired":
            return LeaseState(status="invalid_or_expired")
        if self.heartbeat_outcome == "cancelled":
            return LeaseState(status="cancelled")
        return LeaseState(status="active")

    def acknowledge(self, job_id: str, lease_token: str, result: JobAcknowledgement) -> None:
        self.acknowledge_calls.append((job_id, lease_token, result))
        if self.ack_outcome == "network_down":
            raise httpx.ConnectError("connection refused")
        if self.ack_outcome == "invalid_or_expired":
            raise JobProtocolDenied(reason="invalid_or_expired")
        return None


def _store(tmp_path: Path) -> LocalStore:
    from pr_reviewer.local_store.sqlite import open_local_store

    return open_local_store(tmp_path / "local_state.sqlite3")


def test_recover_resumes_a_claimed_job_while_its_lease_is_still_active(tmp_path: Path) -> None:
    from pr_reviewer.runner.daemon import RunnerDaemon

    store = _store(tmp_path)
    envelope = _job_envelope()
    store.jobs.record_claimed(envelope)
    client = FakeRunnerClient(heartbeat_outcome="active")
    daemon = RunnerDaemon(runner_client=client, local_store=store)

    daemon.recover()

    assert client.heartbeat_calls == [(str(envelope.job_id), envelope.lease_token)]
    remaining = store.jobs.list_claimed()
    assert [job.job_id for job in remaining] == [str(envelope.job_id)]


def test_recover_abandons_a_claimed_job_once_its_lease_is_invalid_or_expired(
    tmp_path: Path,
) -> None:
    """Task 3's invalid_or_expired path applies here: another runner may already own this job,
    so recovery must not resume it, only stop treating it as this runner's work.
    """
    from pr_reviewer.runner.daemon import RunnerDaemon

    store = _store(tmp_path)
    envelope = _job_envelope()
    store.jobs.record_claimed(envelope)
    client = FakeRunnerClient(heartbeat_outcome="invalid_or_expired")
    daemon = RunnerDaemon(runner_client=client, local_store=store)

    daemon.recover()

    assert store.jobs.list_claimed() == []
    row = store.jobs.get(str(envelope.job_id))
    assert row is not None
    assert row.status == "abandoned"


def test_recover_abandons_a_cancelled_job_and_does_not_reclaim_it_on_a_second_recover(
    tmp_path: Path,
) -> None:
    """heartbeat_job returns cancelled forever. recover() must abandon once so a restart
    does not keep re-heartbeating a job the control plane will never give back.
    """
    from pr_reviewer.runner.daemon import RunnerDaemon

    store = _store(tmp_path)
    envelope = _job_envelope()
    store.jobs.record_claimed(envelope)
    client = FakeRunnerClient(heartbeat_outcome="cancelled")
    daemon = RunnerDaemon(runner_client=client, local_store=store)

    daemon.recover()

    assert store.jobs.list_claimed() == []
    row = store.jobs.get(str(envelope.job_id))
    assert row is not None
    assert row.status == "abandoned"
    assert client.heartbeat_calls == [(str(envelope.job_id), envelope.lease_token)]

    daemon.recover()

    assert store.jobs.list_claimed() == []
    assert client.heartbeat_calls == [(str(envelope.job_id), envelope.lease_token)]


def test_recover_leaves_a_claimed_job_untouched_when_the_control_plane_is_unreachable(
    tmp_path: Path,
) -> None:
    """Unreachable is not the same evidence as invalid_or_expired. Resuming on unreachable
    evidence risks duplicating a review a different runner already owns; abandoning on
    unreachable evidence risks discarding work the control plane never actually rejected. Neither
    is safe, so recovery must leave the row exactly as it was and let a later attempt decide.
    """
    from pr_reviewer.runner.daemon import RunnerDaemon

    store = _store(tmp_path)
    envelope = _job_envelope()
    store.jobs.record_claimed(envelope)
    client = FakeRunnerClient(heartbeat_outcome="unreachable")
    daemon = RunnerDaemon(runner_client=client, local_store=store)

    daemon.recover()  # must not raise

    remaining = store.jobs.list_claimed()
    assert [job.job_id for job in remaining] == [str(envelope.job_id)]
    assert remaining[0].status == "claimed"


def test_completing_a_job_rejected_by_the_control_plane_persists_then_reclaims(
    tmp_path: Path,
) -> None:
    """invalid_or_expired is not retried on the same lease. The result is stored, then claim
    decides: NoJob means the stored result is terminal.
    """
    from pr_reviewer.runner.daemon import RunnerDaemon

    store = _store(tmp_path)
    envelope = _job_envelope()
    store.jobs.record_claimed(envelope)
    client = FakeRunnerClient(ack_outcome="invalid_or_expired")
    daemon = RunnerDaemon(runner_client=client, local_store=store)
    result = _acknowledgement()

    daemon.complete_job(str(envelope.job_id), envelope.lease_token, result)

    assert store.pending_acknowledgements.list_pending() == []
    row = store.jobs.get(str(envelope.job_id))
    assert row is not None
    assert row.status == "completed"


def test_completing_a_job_during_a_network_outage_persists_a_pending_acknowledgement(
    tmp_path: Path,
) -> None:
    """The other half of 'lost network after completion': a real connectivity failure, not a
    lease rejection, must land in the same durable queue rather than being lost.
    """
    from pr_reviewer.runner.daemon import RunnerDaemon

    store = _store(tmp_path)
    envelope = _job_envelope()
    store.jobs.record_claimed(envelope)
    client = FakeRunnerClient(ack_outcome="network_down")
    daemon = RunnerDaemon(runner_client=client, local_store=store)
    result = _acknowledgement()

    try:
        daemon.complete_job(str(envelope.job_id), envelope.lease_token, result)
    except httpx.TransportError:
        pass
    else:
        raise AssertionError("expected the network error to still surface to the caller")

    pending = store.pending_acknowledgements.list_pending()
    assert len(pending) == 1
    assert pending[0].reason == "network_unreachable"


def test_completing_a_job_that_the_control_plane_accepts_does_not_queue_anything(
    tmp_path: Path,
) -> None:
    from pr_reviewer.runner.daemon import RunnerDaemon

    store = _store(tmp_path)
    envelope = _job_envelope()
    store.jobs.record_claimed(envelope)
    client = FakeRunnerClient(ack_outcome="succeed")
    daemon = RunnerDaemon(runner_client=client, local_store=store)

    daemon.complete_job(str(envelope.job_id), envelope.lease_token, _acknowledgement())

    assert store.pending_acknowledgements.list_pending() == []
    row = store.jobs.get(str(envelope.job_id))
    assert row is not None
    assert row.status == "completed"


def test_replaying_pending_acknowledgements_resolves_them_once_the_control_plane_accepts(
    tmp_path: Path,
) -> None:
    from pr_reviewer.runner.daemon import RunnerDaemon

    store = _store(tmp_path)
    envelope = _job_envelope()
    store.jobs.record_claimed(envelope)
    result = _acknowledgement()
    store.pending_acknowledgements.record(
        str(envelope.job_id), envelope.lease_token, result, reason="network_unreachable"
    )
    client = FakeRunnerClient(ack_outcome="succeed")
    daemon = RunnerDaemon(runner_client=client, local_store=store)

    daemon.replay_pending_acknowledgements()

    assert store.pending_acknowledgements.list_pending() == []
    assert client.acknowledge_calls == [(str(envelope.job_id), envelope.lease_token, result)]


def test_replaying_invalid_or_expired_pending_acks_reclaims_instead_of_retrying_the_same_lease(
    tmp_path: Path,
) -> None:
    """Replay of an invalid_or_expired ack must not present the dead lease again. claim_job
    decides: NoJob means mark the stored result terminal.
    """
    from pr_reviewer.runner.daemon import RunnerDaemon

    store = _store(tmp_path)
    envelope = _job_envelope()
    store.jobs.record_claimed(envelope)
    result = _acknowledgement()
    store.pending_acknowledgements.record(
        str(envelope.job_id), envelope.lease_token, result, reason="invalid_or_expired"
    )
    client = FakeRunnerClient(ack_outcome="invalid_or_expired")
    daemon = RunnerDaemon(runner_client=client, local_store=store)

    daemon.replay_pending_acknowledgements()

    assert store.pending_acknowledgements.list_pending() == []
    row = store.jobs.get(str(envelope.job_id))
    assert row is not None
    assert row.status == "completed"
    assert client.acknowledge_calls == []


def test_start_then_stop_is_cooperative_and_returns_well_within_the_deadline(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    client = FakeRunnerClient()
    from pr_reviewer.runner.daemon import RunnerDaemon

    daemon = RunnerDaemon(runner_client=client, local_store=store, poll_interval_seconds=0.02)

    daemon.start()
    time.sleep(0.1)  # let the poll loop actually run a few iterations
    assert client.claim_calls > 0, "expected the background loop to poll at least once"

    started_stop = time.monotonic()
    daemon.stop(deadline_seconds=2.0)
    elapsed = time.monotonic() - started_stop

    assert elapsed < 2.0, "stop() should not need to wait out the full deadline for a short loop"
    thread = getattr(daemon, "_poll_thread", None)
    if thread is not None:
        assert not thread.is_alive(), "the background loop thread must have stopped"


def test_daemon_recovers_from_a_corrupted_local_store_file_by_quarantining_and_starting_fresh(
    tmp_path: Path,
) -> None:
    from pr_reviewer.runner.daemon import open_or_recover_local_store

    path = tmp_path / "local_state.sqlite3"
    path.write_bytes(
        b"not a sqlite database, deliberately corrupted for this test"
    )

    store = open_or_recover_local_store(path)  # must not raise

    assert store.jobs.list_claimed() == []  # fresh store, usable immediately
    quarantined = list(tmp_path.glob("local_state.sqlite3.corrupt-*"))
    assert quarantined, "the corrupted file must be preserved for forensics, not deleted"


def test_secret_access_never_leaks_into_os_environ_including_a_spawned_childs_environment(
    tmp_path: Path,
) -> None:
    from pr_reviewer.runner.daemon import RunnerDaemon
    from pr_reviewer.runner.secrets import FileSecretStore

    marker = "sk-daemon-marker-" + uuid.uuid4().hex
    secret_store = FileSecretStore(tmp_path / "secrets")
    secret_store.set("model_key", marker)
    store = _store(tmp_path)
    client = FakeRunnerClient()

    before = dict(os.environ)
    daemon = RunnerDaemon(
        runner_client=client,
        local_store=store,
        secret_store=secret_store,
        poll_interval_seconds=0.02,
    )
    daemon.start()
    time.sleep(0.05)
    daemon.stop(deadline_seconds=2.0)

    assert dict(os.environ) == before, "the daemon lifecycle must never mutate os.environ"

    child = subprocess.run(
        [sys.executable, "-c", "import os, sys; sys.stdout.write(repr(dict(os.environ)))"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert marker not in child.stdout


def test_recovering_a_lost_lease_never_creates_a_second_local_row_for_the_same_job(
    tmp_path: Path,
) -> None:
    """Cross-check against test_local_store.py's duplicate-row guarantee: a recovery pass that
    re-observes a job the poll loop also just recorded must still land on exactly one row.
    """
    from pr_reviewer.runner.daemon import RunnerDaemon

    store = _store(tmp_path)
    envelope = _job_envelope()
    store.jobs.record_claimed(envelope)
    client = FakeRunnerClient(heartbeat_outcome="active")
    daemon = RunnerDaemon(runner_client=client, local_store=store)

    daemon.recover()
    store.jobs.record_claimed(envelope)
    daemon.recover()

    assert len(store.jobs.list_claimed()) == 1


def test_daemon_never_imports_the_hosted_control_plane_or_database_client() -> None:
    import inspect

    from pr_reviewer.runner import daemon

    source = inspect.getsource(daemon)
    assert "pr_reviewer.control_plane" not in source
    assert "pr_reviewer.db" not in source
    assert "os.environ[" not in source
    assert "os.putenv" not in source
