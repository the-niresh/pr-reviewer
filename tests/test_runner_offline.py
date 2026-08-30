"""Tests for runner offline behaviour, acknowledgement re-claim, and revocation (Runtime Task 9).

The hard decision: when acknowledge_job returns invalid_or_expired, the runner cannot tell
"lease expired, job still pending" from "another runner already finished it". Those five
conditions collapse on purpose (control_plane/runner_jobs.py). A scheduled retry of the same
ack has no correct give-up rule.

So the runner persists the finished result, then calls claim_job again. A JobEnvelope for the
same job means the stored result can land under a fresh lease. NoJob means stop and mark that
stored result terminal. Re-acknowledging must reuse the stored result: it must not call the
model again and must not post to GitHub again.

Imports of new Task 9 names stay inside test bodies so a missing module fails the test instead
of interrupting collection.
"""

from __future__ import annotations

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
    RunnerAuthDenied,
)
from pr_reviewer.local_store.sqlite import LocalStore, open_local_store
from pr_reviewer.runner.daemon import RunnerDaemon
from pr_reviewer.runner.secrets import FileSecretStore

BASE_SHA = "a" * 40
HEAD_SHA = "b" * 40


def _job_envelope(
    *,
    job_id: uuid.UUID | None = None,
    lease_token: str = "lease-token-value",
    installation_id: int = 9101,
) -> JobEnvelope:
    return JobEnvelope(
        job_id=job_id or uuid.uuid4(),
        installation_id=installation_id,
        repository_id=91101,
        pull_request_number=4,
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
        local_result_hash="e" * 64,
    )


class CountingModelClient:
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, job: JobEnvelope) -> str:
        del job
        self.calls += 1
        return "review-body"


class CountingGitHubClient:
    def __init__(self) -> None:
        self.posts = 0

    def post_review(self, job: JobEnvelope, body: str) -> None:
        del job, body
        self.posts += 1


class CountingReviewExecutor:
    def __init__(
        self,
        model: CountingModelClient,
        github: CountingGitHubClient,
        result: JobAcknowledgement | None = None,
    ) -> None:
        self.model = model
        self.github = github
        self.result = result if result is not None else _acknowledgement()
        self.fail_model_with: Exception | None = None

    def review(self, job: JobEnvelope) -> JobAcknowledgement:
        if self.fail_model_with is not None:
            self.model.calls += 1
            raise self.fail_model_with
        body = self.model.complete(job)
        self.github.post_review(job, body)
        return self.result


class ScriptedRunnerClient:
    """A RunnerClient-shaped fake with a queue of claim and ack outcomes."""

    def __init__(self) -> None:
        self.claim_queue: list[object] = []
        self.ack_queue: list[str] = []
        self.claim_calls = 0
        self.credentials_used: list[str] = []
        self.acknowledge_calls: list[tuple[str, str, JobAcknowledgement]] = []
        self._credential = "runner-credential"

    def set_credential(self, credential: str) -> None:
        self._credential = credential

    def claim(self) -> JobEnvelope | NoJob | RunnerAuthDenied:
        self.claim_calls += 1
        self.credentials_used.append(self._credential)
        if not self.claim_queue:
            return NoJob()
        item = self.claim_queue.pop(0)
        if item == "unreachable":
            raise httpx.ConnectError("connection refused")
        if isinstance(item, (JobEnvelope, NoJob, RunnerAuthDenied)):
            return item
        raise AssertionError(f"unexpected claim script item {item!r}")

    def heartbeat(self, job_id: str, lease_token: str) -> LeaseState:
        del job_id, lease_token
        return LeaseState(status="active")

    def acknowledge(self, job_id: str, lease_token: str, result: JobAcknowledgement) -> None:
        self.acknowledge_calls.append((job_id, lease_token, result))
        outcome = self.ack_queue.pop(0) if self.ack_queue else "succeed"
        if outcome == "network_down":
            raise httpx.ConnectError("connection refused")
        if outcome == "invalid_or_expired":
            raise JobProtocolDenied(reason="invalid_or_expired")


def _store(tmp_path: Path) -> LocalStore:
    return open_local_store(tmp_path / "local_state.sqlite3")


def _daemon(
    tmp_path: Path,
    client: ScriptedRunnerClient,
    review: CountingReviewExecutor | None = None,
    *,
    secret_store: FileSecretStore | None = None,
) -> RunnerDaemon:
    return RunnerDaemon(
        runner_client=client,
        local_store=_store(tmp_path),
        secret_store=secret_store,
        review=review,
        poll_interval_seconds=0.01,
    )


def test_offline_before_claim_does_not_record_a_job_or_call_the_model(tmp_path: Path) -> None:
    model = CountingModelClient()
    github = CountingGitHubClient()
    review = CountingReviewExecutor(model, github)
    client = ScriptedRunnerClient()
    client.claim_queue.append("unreachable")
    daemon = _daemon(tmp_path, client, review)

    daemon.process_once()

    assert daemon._local_store.jobs.list_claimed() == []
    assert model.calls == 0
    assert github.posts == 0
    assert client.acknowledge_calls == []


def test_offline_during_a_model_call_keeps_the_claimed_job_and_does_not_post_or_ack(
    tmp_path: Path,
) -> None:
    model = CountingModelClient()
    github = CountingGitHubClient()
    review = CountingReviewExecutor(model, github)
    review.fail_model_with = httpx.ConnectError("model unreachable")
    envelope = _job_envelope()
    client = ScriptedRunnerClient()
    client.claim_queue.append(envelope)
    daemon = _daemon(tmp_path, client, review)

    try:
        daemon.process_once()
    except httpx.TransportError:
        pass
    else:
        raise AssertionError("expected the model outage to surface")

    remaining = daemon._local_store.jobs.list_claimed()
    assert [job.job_id for job in remaining] == [str(envelope.job_id)]
    assert model.calls == 1
    assert github.posts == 0
    assert client.acknowledge_calls == []


def test_offline_after_local_completion_persists_the_result(tmp_path: Path) -> None:
    model = CountingModelClient()
    github = CountingGitHubClient()
    result = _acknowledgement()
    review = CountingReviewExecutor(model, github, result=result)
    envelope = _job_envelope()
    client = ScriptedRunnerClient()
    client.claim_queue.append(envelope)
    client.ack_queue.append("network_down")
    daemon = _daemon(tmp_path, client, review)

    try:
        daemon.process_once()
    except httpx.TransportError:
        pass
    else:
        raise AssertionError("expected the control-plane outage on ack to surface")

    pending = daemon._local_store.pending_acknowledgements.list_pending()
    assert len(pending) == 1
    assert pending[0].result.local_result_hash == result.local_result_hash
    assert pending[0].reason == "network_unreachable"
    assert model.calls == 1
    assert github.posts == 1


def test_invalid_or_expired_ack_reclaims_and_reuses_the_stored_result_without_rerunning(
    tmp_path: Path,
) -> None:
    model = CountingModelClient()
    github = CountingGitHubClient()
    result = _acknowledgement()
    review = CountingReviewExecutor(model, github, result=result)
    job_id = uuid.uuid4()
    first = _job_envelope(job_id=job_id, lease_token="lease-old")
    second = _job_envelope(job_id=job_id, lease_token="lease-fresh")
    client = ScriptedRunnerClient()
    client.claim_queue.extend([first, second])
    client.ack_queue.append("invalid_or_expired")
    daemon = _daemon(tmp_path, client, review)

    daemon.process_once()

    assert model.calls == 1
    assert github.posts == 1
    assert [(call_job, token) for call_job, token, _result in client.acknowledge_calls] == [
        (str(first.job_id), "lease-old"),
        (str(second.job_id), "lease-fresh"),
    ]
    assert client.acknowledge_calls[1][2].local_result_hash == result.local_result_hash
    assert daemon._local_store.pending_acknowledgements.list_pending() == []
    row = daemon._local_store.jobs.get(str(job_id))
    assert row is not None
    assert row.status == "completed"


def test_reclaim_returning_no_job_marks_the_stored_result_terminal(tmp_path: Path) -> None:
    model = CountingModelClient()
    github = CountingGitHubClient()
    result = _acknowledgement()
    review = CountingReviewExecutor(model, github, result=result)
    envelope = _job_envelope()
    client = ScriptedRunnerClient()
    client.claim_queue.append(envelope)
    client.ack_queue.append("invalid_or_expired")
    client.claim_queue.append(NoJob())
    daemon = _daemon(tmp_path, client, review)

    daemon.process_once()

    assert model.calls == 1
    assert github.posts == 1
    pending = daemon._local_store.pending_acknowledgements.list_pending()
    assert pending == []
    row = daemon._local_store.jobs.get(str(envelope.job_id))
    assert row is not None
    assert row.status == "completed"


def test_invalid_or_expired_pending_ack_is_not_retried_on_the_same_lease(
    tmp_path: Path,
) -> None:
    from pr_reviewer.runner.daemon import RunnerDaemon

    store = _store(tmp_path)
    job_id = uuid.uuid4()
    result = _acknowledgement()
    store.pending_acknowledgements.record(
        str(job_id), "lease-old", result, reason="invalid_or_expired"
    )
    store.jobs.record_claimed(_job_envelope(job_id=job_id, lease_token="lease-old"))
    fresh = _job_envelope(job_id=job_id, lease_token="lease-fresh")
    client = ScriptedRunnerClient()
    client.claim_queue.append(fresh)
    daemon = RunnerDaemon(runner_client=client, local_store=store)

    daemon.replay_pending_acknowledgements()

    assert client.acknowledge_calls == [(str(job_id), "lease-fresh", result)]
    assert all(token != "lease-old" for _job, token, _result in client.acknowledge_calls)


def test_revoked_while_running_does_not_claim_a_second_job(tmp_path: Path) -> None:
    model = CountingModelClient()
    github = CountingGitHubClient()
    review = CountingReviewExecutor(model, github)
    first = _job_envelope()
    second = _job_envelope()
    client = ScriptedRunnerClient()
    client.claim_queue.extend([first, RunnerAuthDenied(reason="revoked_runner"), second])
    daemon = _daemon(tmp_path, client, review)

    daemon.process_once()
    daemon.process_once()

    claimed_ids = {job.job_id for job in daemon._local_store.jobs.list_claimed()}
    completed = daemon._local_store.jobs.get(str(first.job_id))
    assert str(second.job_id) not in claimed_ids
    assert daemon._local_store.jobs.get(str(second.job_id)) is None
    assert completed is not None
    assert completed.status == "completed"
    assert model.calls == 1
    assert github.posts == 1


def test_installation_revocation_stops_new_work_immediately(tmp_path: Path) -> None:
    from pr_reviewer.runner.revocation import RevocationGate

    model = CountingModelClient()
    github = CountingGitHubClient()
    review = CountingReviewExecutor(model, github)
    first = _job_envelope(installation_id=9101)
    second = _job_envelope(installation_id=9101)
    client = ScriptedRunnerClient()
    client.claim_queue.extend([first, second])
    gate = RevocationGate()
    daemon = _daemon(tmp_path, client, review)
    daemon._revocation = gate

    daemon.process_once()
    gate.note_installation_revoked(9101)
    daemon.process_once()

    assert daemon._local_store.jobs.get(str(second.job_id)) is None
    assert model.calls == 1


def test_rotated_credential_is_used_on_the_next_call(tmp_path: Path) -> None:
    secrets = FileSecretStore(tmp_path / "secrets")
    secrets.set("runner_credential", "credential-old")
    client = ScriptedRunnerClient()
    client.set_credential("credential-old")
    client.claim_queue.append("unreachable")
    daemon = _daemon(tmp_path, client, secret_store=secrets)

    daemon.process_once()
    secrets.set("runner_credential", "credential-rotated")
    client.claim_queue.append(NoJob())
    daemon.process_once()

    assert client.credentials_used[-1] == "credential-rotated"


def test_control_plane_outage_during_claim_does_not_crash_and_retries_later(
    tmp_path: Path,
) -> None:
    model = CountingModelClient()
    github = CountingGitHubClient()
    review = CountingReviewExecutor(model, github)
    envelope = _job_envelope()
    client = ScriptedRunnerClient()
    client.claim_queue.extend(["unreachable", envelope])
    daemon = _daemon(tmp_path, client, review)

    daemon.process_once()
    daemon.process_once()

    row = daemon._local_store.jobs.get(str(envelope.job_id))
    assert row is not None
    assert model.calls == 1
    assert github.posts == 1
