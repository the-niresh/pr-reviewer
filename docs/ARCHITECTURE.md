# Architecture

| Mark | Means |
|---|---|
| ⬜ | Not done yet |
| ✅ | Done, or in scope and agreed |
| ❌ | Deliberately not doing this |
| ❓ | Open decision |
| ⚠️ | Known trap |

This is a map of the shipped system. Every claim names a file or a test.
This document has no quality, latency, or cost-per-PR numbers.

## 1 - ✅ Two planes, one trust boundary

The hosted control plane receives GitHub webhooks, owns App secrets, stores
shared job metadata in Neon, and hands jobs to runners over outbound HTTPS.
The installed runner keeps model keys local, fetches PR data with short-lived
installation tokens, runs review, and posts only after a human gate.

Hosted schema cannot hold private review data. `assert_no_private_columns`
(`control_plane/boundary.py`) reads the live schema. `HOSTED_EXEMPTIONS` is
empty (`boundary.py:35`, `tests/test_hosted_boundary_enforcement.py`). The
human-readable half is `docs/DATA_BOUNDARIES.md`. Dashboard modules do not
import runner or hosted handles (`tests/test_dashboard_auth.py`). Runner CLI
does not import `pr_reviewer.db` (`tests/test_doctor.py`).

## 2 - ✅ Event spine

A signed webhook is verified before JSON parsing (`github/verify_signature.py:19`,
`tests/test_webhook.py`). Deliveries are keyed by GitHub's delivery id.
A duplicate does not insert a second job (`tests/test_fault_injection.py`).
`handle_pull_request_event` (`github/lifecycle.py:33`) decides enqueue,
cancel, or ignore.

Hosted lifecycle events are flat identifiers, enums, and aggregates
(`events/record_event.py:41`). Nested objects are rejected in application
code and by a CHECK constraint. Local events live in SQLite. One review is
rejoined by job id through `reconstruct_trace` (`observability/trace.py:171`,
`tests/test_trace_join.py`). Mismatched hosted and local trace ids raise.
Secret-like keys are stripped (`tests/test_trace_cli.py`).

## 3 - ✅ Postgres job queue

Jobs are rows in `review_jobs`. `enqueue_review_job`
(`jobs/enqueue_review_job.py:16`) inserts pending. `claim_review_job`
(`jobs/claim_review_job.py:46`) takes the next pending or expired-lease row
with `FOR UPDATE SKIP LOCKED`. There is no Redis in this stack. ADR-002's
reversal trigger is recorded in `docs/QUEUE_BENCHMARK.md`. This document
does not repeat that measurement.

A new head SHA supersedes stale pending and running work
(`jobs/enqueue_review_job.py:67`). A stale reviewed head does not post
(`github/post_review.py`, `tests/test_fault_injection.py`).

## 4 - ✅ Docker sandbox

The model picks an allowlisted command id. It does not compose a shell string
(`verification/docker_sandbox.py:1`). If Docker is missing, the result is
inconclusive and the command is never run on the host
(`tests/test_doctor_docker.py`). Spec commands are passed as argv, never as a
shell string. Auto-install of Docker is forbidden.

## 5 - ✅ Human gate

`route_finding` (`notifications/gate.py:36`) is system-owned. The model
cannot set verification, public safety, status, or posting fields
(`contracts/finding_candidate.py`). Confidence is stored for calibration and
is not read by routing (`tests/test_eval_regression_gate.py`).
`allow_public_post` stays false until a human approves
(`tests/test_dashboard_api.py`). Restricted findings require a channel
declared `restricted`. Specialist mode stays off on the default policy
(`tests/test_specialists.py`). LangGraph stays off
(`tests/test_langgraph_engine.py`).

## 6 - ✅ Prompt versioning

`PromptRegistry.register` (`prompts/registry.py:27`) raises
`PromptVersionImmutable` on an existing name and version
(`tests/test_prompt_registry.py`). Hosted `prompt_versions` are insert-only.
One dispute does not rewrite prompts, policy, labels, or routing
(`tests/test_feedback_candidates.py`).

## 7 - ✅ Connector audit

`record_connector_run` (`connectors/audit.py:89`) persists `ConnectorAudit`
only. The payload is hashed, not stored. Token-shaped strings are redacted
(`connectors/audit.py:19`). The in-process GitHub result type is not imported
here.

## Settled - ✅

- ✅ Hosted Neon never holds source, diffs, findings, or model keys.
- ✅ Runners use outbound HTTPS. The dashboard exposes no webhook route.
- ✅ Jobs are Postgres rows claimed with skip-locked leases.
- ✅ Untrusted commands run only in Docker, or not at all.

## Open Decisions - ❓

- ❓ Which public HTTPS host will run the shared control plane.
- ❓ Which operating systems ship in v1.
