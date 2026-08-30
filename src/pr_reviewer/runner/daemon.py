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

complete_job persists a finished result before it is lost. invalid_or_expired is five distinct
control-plane conditions collapsed into one reason, so retrying the same ack has no correct
give-up rule. Instead the runner re-claims: a JobEnvelope for that job means the stored result
can land under a fresh lease; NoJob means stop and mark the stored result terminal. The stored
result is reused. The model and GitHub are not called again.
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
from pr_reviewer.runner.revocation import RevocationGate
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
    def set_credential(self, credential: str) -> None: ...


class ReviewExecutor(Protocol):
    def review(self, job: JobEnvelope) -> JobAcknowledgement: ...


class RunnerDaemon:
    def __init__(
        self,
        *,
        runner_client: RunnerClientProtocol,
        local_store: LocalStore,
        secret_store: SecretStore | None = None,
        review: ReviewExecutor | None = None,
        revocation: RevocationGate | None = None,
        poll_interval_seconds: float = 1.0,
    ) -> None:
        self._runner_client = runner_client
        self._local_store = local_store
        self._secret_store = secret_store
        self._review = review
        self._revocation = revocation if revocation is not None else RevocationGate()
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
            self.process_once()
            if not self._revocation.allow_new_work():
                break
            self._stop_event.wait(self._poll_interval_seconds)

    def process_once(self) -> None:
        if not self._revocation.allow_new_work():
            return
        self._refresh_credential()
        try:
            claimed = self._runner_client.claim()
        except httpx.TransportError:
            return
        if isinstance(claimed, RunnerAuthDenied):
            if claimed.reason == "revoked_runner":
                self._revocation.note_runner_revoked()
            return
        if isinstance(claimed, NoJob):
            return
        self._run_claimed_job(claimed)

    def _refresh_credential(self) -> None:
        if self._secret_store is None:
            return
        credential = self._secret_store.get("runner_credential")
        if credential is None:
            return
        self._runner_client.set_credential(credential)

    def _run_claimed_job(self, claimed: JobEnvelope) -> None:
        self._local_store.jobs.record_claimed(claimed)
        if self._review is None:
            return
        result = self._review.review(claimed)
        self.complete_job(str(claimed.job_id), claimed.lease_token, result)

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
            self._land_pending_result(job_id, result)
            return
        except httpx.TransportError:
            self._local_store.pending_acknowledgements.record(
                job_id, lease_token, result, reason="network_unreachable"
            )
            raise
        else:
            self._local_store.jobs.mark_completed(job_id)

    def replay_pending_acknowledgements(self) -> None:
        for entry in self._local_store.pending_acknowledgements.list_pending():
            if entry.reason == "invalid_or_expired":
                self._land_pending_result(entry.job_id, entry.result)
                continue
            try:
                self._runner_client.acknowledge(entry.job_id, entry.lease_token, entry.result)
            except _RETRYABLE_ACKNOWLEDGE_ERRORS:
                self._local_store.pending_acknowledgements.bump_attempt(entry.id)
                continue
            self._local_store.pending_acknowledgements.resolve(entry.id)
            self._local_store.jobs.mark_completed(entry.job_id)

    def _land_pending_result(self, job_id: str, result: JobAcknowledgement) -> None:
        self._refresh_credential()
        try:
            claimed = self._runner_client.claim()
        except httpx.TransportError:
            return
        if isinstance(claimed, RunnerAuthDenied):
            if claimed.reason == "revoked_runner":
                self._revocation.note_runner_revoked()
            self._mark_pending_terminal(job_id)
            return
        if isinstance(claimed, JobEnvelope) and str(claimed.job_id) == job_id:
            try:
                self._runner_client.acknowledge(str(claimed.job_id), claimed.lease_token, result)
            except _RETRYABLE_ACKNOWLEDGE_ERRORS:
                return
            self._mark_pending_terminal(job_id)
            return
        if isinstance(claimed, JobEnvelope):
            self._local_store.jobs.record_claimed(claimed)
        self._mark_pending_terminal(job_id)

    def _mark_pending_terminal(self, job_id: str) -> None:
        self._local_store.jobs.mark_completed(job_id)
        for entry in self._local_store.pending_acknowledgements.list_pending():
            if entry.job_id == job_id:
                self._local_store.pending_acknowledgements.resolve(entry.id)


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
