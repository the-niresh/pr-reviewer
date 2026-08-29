"""The installed runner daemon (Runtime Task 5).

RunnerDaemon.start() recovers claimed jobs left over from a previous run, replays acknowledgements
the control plane could not previously accept, and starts a background poll loop. stop() is
cooperative: it signals the loop and waits up to deadline_seconds for it to notice, rather than
killing anything.

Recovery has three outcomes, not two, because "lease is active" and "lease is invalid_or_expired"
are not the only evidence a heartbeat call can produce:

- active: still ours, leave it claimed.
- invalid_or_expired: Task 3's path -- another runner may already own this job, so this run stops
  treating it as its own without resuming it.
- unreachable (a network failure talking to the control plane, not a lease response at all):
  leave the row exactly as it is. Resuming on unreachable evidence risks duplicating a review
  another runner may already own; abandoning on unreachable evidence risks discarding real
  in-progress work the control plane never actually rejected. Neither is safe, so recovery defers
  the decision to a later attempt instead of guessing.

complete_job wires up the TODO in runner/client.py's acknowledge(): a lease rejection or a real
network failure after a review has finished must not drop the only copy of the result. Both land
in local_store.pending_acknowledgements before the original exception is re-raised, so the caller
still learns about the failure but the work is never lost. replay_pending_acknowledgements is the
best-effort sweep that resends them later; a lease that is genuinely dead forever keeps failing,
but the record stays queued rather than being dropped.
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import httpx

from pr_reviewer.contracts.runner import (
    JobAcknowledgement,
    JobEnvelope,
    JobProtocolDenied,
    LeaseState,
    NoJob,
    RunnerAuthDenied,
)
from pr_reviewer.local_store.sqlite import LocalStore, LocalStoreCorrupted, open_local_store
from pr_reviewer.runner.secrets import SecretStore

logger = logging.getLogger(__name__)

_RETRYABLE_ACKNOWLEDGE_ERRORS = (JobProtocolDenied, httpx.TransportError)


class RunnerClientProtocol(Protocol):
    """Matches runner/client.py's RunnerClient without importing it, so a test can supply a fake
    with no HTTP layer at all.
    """

    def claim(self) -> JobEnvelope | NoJob | RunnerAuthDenied: ...
    def heartbeat(self, job_id: str, lease_token: str) -> LeaseState: ...
    def acknowledge(self, job_id: str, lease_token: str, result: JobAcknowledgement) -> None: ...


class RunnerDaemon:
    def __init__(
        self,
        *,
        runner_client: RunnerClientProtocol,
        local_store: LocalStore,
        secret_store: SecretStore | None = None,
        poll_interval_seconds: float = 1.0,
    ) -> None:
        self._runner_client = runner_client
        self._local_store = local_store
        self._secret_store = secret_store
        self._poll_interval_seconds = poll_interval_seconds
        self._stop_event = threading.Event()
        self._poll_thread: threading.Thread | None = None

    def start(self) -> None:
        self.recover()
        self.replay_pending_acknowledgements()
        self._stop_event.clear()
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()

    def stop(self, deadline_seconds: float) -> None:
        self._stop_event.set()
        if self._poll_thread is not None:
            self._poll_thread.join(timeout=deadline_seconds)

    def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                claimed = self._runner_client.claim()
            except httpx.TransportError:
                claimed = None
            if isinstance(claimed, JobEnvelope):
                self._local_store.jobs.record_claimed(claimed)
            self._stop_event.wait(self._poll_interval_seconds)

    def recover(self) -> None:
        for job in self._local_store.jobs.list_claimed():
            try:
                lease = self._runner_client.heartbeat(job.job_id, job.lease_token)
            except httpx.TransportError:
                logger.warning(
                    "control plane unreachable recovering job %s; deferring", job.job_id
                )
                continue
            if lease.status == "invalid_or_expired":
                self._local_store.jobs.mark_abandoned(job.job_id)

    def complete_job(self, job_id: str, lease_token: str, result: JobAcknowledgement) -> None:
        try:
            self._runner_client.acknowledge(job_id, lease_token, result)
        except JobProtocolDenied:
            self._local_store.pending_acknowledgements.record(
                job_id, lease_token, result, reason="invalid_or_expired"
            )
            raise
        except httpx.TransportError:
            self._local_store.pending_acknowledgements.record(
                job_id, lease_token, result, reason="network_unreachable"
            )
            raise
        else:
            self._local_store.jobs.mark_completed(job_id)

    def replay_pending_acknowledgements(self) -> None:
        for entry in self._local_store.pending_acknowledgements.list_pending():
            try:
                self._runner_client.acknowledge(entry.job_id, entry.lease_token, entry.result)
            except _RETRYABLE_ACKNOWLEDGE_ERRORS:
                self._local_store.pending_acknowledgements.bump_attempt(entry.id)
                continue
            self._local_store.pending_acknowledgements.resolve(entry.id)
            self._local_store.jobs.mark_completed(entry.job_id)


def open_or_recover_local_store(path: str | Path) -> LocalStore:
    """Corruption (a truncated file, a power-loss mid-write, disk damage) must not crash the
    daemon. The corrupt file is quarantined by rename, never deleted, so it survives for
    forensics, and a fresh usable store takes its place immediately.
    """
    try:
        return open_local_store(path)
    except LocalStoreCorrupted:
        resolved = Path(path)
        quarantine = resolved.with_name(
            f"{resolved.name}.corrupt-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}"
        )
        resolved.rename(quarantine)
        logger.warning(
            "local state file %s was corrupted; quarantined to %s, starting fresh",
            resolved,
            quarantine,
        )
        return open_local_store(path)
