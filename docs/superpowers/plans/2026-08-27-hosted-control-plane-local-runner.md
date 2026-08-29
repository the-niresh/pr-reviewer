# Hosted Control Plane and Local Runner Implementation Plan

| Mark | Means |
|---|---|
| ⬜ | Not done yet. I tick it when it lands |
| ✅ | Done, or in scope and agreed |
| ❌ | Deliberately not doing this |
| ❓ | Open decision, waiting on me |
| ⚠️ | Known trap. Read before writing the code |

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans`. Use strict TDD for behavior work. Each task starts with a failing test, receives a code review, and ends with all project checks passing.

**Goal - ✅:** Let a user install `reviewer`, finish onboarding in a localhost UI, install the shared GitHub App on selected repositories, and receive real PR jobs without exposing a public port on the user's machine.

**Architecture:** A hosted FastAPI control plane receives GitHub webhooks, owns GitHub App secrets, stores shared job metadata in Neon, and leases jobs to paired runners. The installed Python runner maintains an outbound HTTPS connection, keeps model keys and private review data local, uses short-lived repository-scoped GitHub tokens, opens the Bun UI on localhost, and uses Docker for full-mode retrieval and verification.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, psycopg, Neon Postgres, Python `sqlite3`, local Postgres with pgvector in Docker for full mode, httpx, GitHub App API, operating-system secret storage, uv, Bun, TypeScript, pytest, mypy, ruff, and Playwright.

**Master Plan:** `docs/superpowers/plans/2026-08-25-ai-pr-reviewer.md`

**Phase Roadmap:** `docs/superpowers/plans/2026-08-27-ai-engineering-phase-roadmap.md`

## Non-Goals

- ❌ The installed runner does not receive Neon credentials.
- ❌ The installed runner does not receive the GitHub App private key or webhook secret.
- ❌ The user does not create a GitHub App, personal access token, database, tunnel, or public webhook URL.
- ❌ The control plane does not send arbitrary shell commands to a runner.
- ❌ Analysis-only mode does not execute PR code or call a result verified.
- ❌ The installer does not install Docker or request administrator access.
- ❌ v1 does not provide a hosted sandbox runner. The user's machine must be online for local review work.

## Runtime Modes

- ✅ **Full mode:** Requires Docker. Runs local Postgres with pgvector, repository retrieval, static checks, and Docker sandbox verification.
- ✅ **Analysis-only mode:** Does not require Docker. Uses the PR diff, one model call, static non-executing checks, and human approval for every finding.
- ✅ A user can move from analysis-only to full mode after Docker passes `reviewer doctor`.
- ✅ Moving from full mode to analysis-only stops local Postgres and sandbox containers cleanly but preserves the local data volume.
- ⚠️ Missing Docker never causes host-process execution.

## Data Boundary

### Hosted Neon - ✅

- ✅ User account ID and GitHub user ID.
- ✅ GitHub installation ID, numeric repository ID, repository display name, and permission state.
- ✅ Runner ID, runner credential hash, capabilities, last-seen time, assignment, and revocation state.
- ✅ Webhook delivery ID, event action, PR number, base SHA, head SHA, queue state, lease, attempts, and error class.
- ✅ Redacted lifecycle events, aggregate token counts, aggregate costs, latency, and product health.
- ❌ No model API keys, notification secrets, raw source files, raw diffs, embeddings, finding
  rationale, sandbox logs, or reusable GitHub installation tokens.

### Local Runner - ✅

- ✅ Operating-system secret references for the runner credential, model keys, and every notification
  secret (Slack, Telegram, Discord webhook or bot token).
- ✅ Local SQLite for daemon state, mode, settings, claimed jobs, PR snapshots, findings, human decisions, detailed events, and pending result acknowledgements.
- ✅ Full-mode local Postgres with pgvector for code chunks, embeddings, retrieval generations, and search.
- ✅ Short-lived repository-scoped GitHub installation tokens remain in memory and are discarded after the job.
- ✅ The runner reports only redacted state and aggregate usage to the control plane.

## Security Invariants

- ✅ The runner connects outbound over HTTPS. No inbound local port is needed except loopback UI traffic.
- ✅ Pairing codes are one-use, expire after 10 minutes, and are stored hashed.
- ✅ Runner credentials are unique, revocable, rotated, and stored hashed in Neon.
- ✅ One active runner assignment exists per repository in v1.
- ✅ A job lease is bound to runner ID, installation ID, repository ID, PR number, and head SHA.
- ✅ The token broker checks the lease before creating a repository-scoped GitHub installation token.
- ✅ Every denial reason returned by pairing, job claim, the token broker, or repository authorization
  is computable from data the caller may already see. Cases the caller cannot distinguish by right
  collapse to one reason.
- ✅ Job payloads contain typed identifiers and policy only. They never contain executable commands.
- ✅ Local UI binds to `127.0.0.1`, uses a random session secret, and protects state-changing requests from CSRF.
- ✅ Docker mode runs untrusted code with no network, no host secrets, no Docker socket, non-root user, resource limits, and a hard timeout.
- ✅ The runner sends every notification directly. The control plane holds no notification secret and
  never sends on the user's behalf, so a security finding never transits the hosted service.
- ✅ Model keys and notification secrets are read from the operating-system keyring **at call time**.
  They are never loaded into the daemon's environment, because a subprocess or a container escape
  inherits `os.environ` and does not inherit a keyring lookup.
- ✅ All credentials are redacted from logs, errors, traces, crash reports, and support bundles.

## User Onboarding

1. ✅ User installs a versioned and checksummed release.
2. ✅ User runs `reviewer`.
3. ✅ The daemon binds the UI to `127.0.0.1` and opens it in the browser.
4. ✅ The UI requests a one-time pairing code from the hosted control plane.
5. ✅ The user signs in with GitHub and installs the shared GitHub App on selected repositories. The UI
   states plainly, before the install, that `Contents: Read` is **repository-wide** because GitHub has
   no PR-scoped read grant, and that full mode indexes the whole default branch, not only changed files.
6. ✅ The control plane binds the installation and repositories to the paired runner.
7. ✅ The user selects OpenAI or Anthropic and enters the API key locally.
8. ✅ `reviewer doctor` checks control-plane access, model access, local ports, storage, Git, and Docker.
9. ✅ The user selects full mode when Docker passes or analysis-only mode when it does not.
10. ✅ The daemon starts as a user service and begins outbound job claims.

## File Structure

- ⬜ `src/pr_reviewer/contracts/runner.py` - runner, pairing, capability, job, lease, and acknowledgement contracts.
- ⬜ `src/pr_reviewer/control_plane/app.py` - hosted API composition and hosted database wiring.
- ⬜ `src/pr_reviewer/control_plane/pairing.py` - one-time pairing flow.
- ⬜ `src/pr_reviewer/control_plane/runner_auth.py` - runner authentication, rotation, and revocation.
- ⬜ `src/pr_reviewer/control_plane/runner_jobs.py` - claim, heartbeat, complete, and release endpoints.
- ⬜ `src/pr_reviewer/control_plane/token_broker.py` - repository-scoped GitHub token issuing.
- ⬜ `src/pr_reviewer/runner/client.py` - authenticated outbound control-plane client.
- ⬜ `src/pr_reviewer/runner/daemon.py` - local service loop and shutdown.
- ⬜ `src/pr_reviewer/runner/local_api.py` - loopback API composition with no hosted database dependency.
- ⬜ `src/pr_reviewer/runner/modes.py` - full and analysis-only capability policy.
- ⬜ `src/pr_reviewer/runner/secrets.py` - operating-system secret storage and file fallback.
- ⬜ `src/pr_reviewer/local_store/sqlite.py` - local state and pending acknowledgements.
- ⬜ `src/pr_reviewer/observability/trace.py` - cross-store trace join.
- ⬜ `src/pr_reviewer/cli/trace.py` - redacted trace view and export.
- ⬜ `src/pr_reviewer/local_store/postgres.py` - full-mode local pgvector connection.
- ⬜ `src/pr_reviewer/containers/runtime.py` - container runtime interface.
- ⬜ `src/pr_reviewer/containers/docker.py` - Docker implementation and isolation checks.
- ⬜ `src/pr_reviewer/cli/doctor.py` - onboarding and mode checks.
- ⬜ `src/pr_reviewer/cli/service.py` - systemd-user and launchd service setup.
- ⬜ `apps/web/src/app/onboarding/*` - pairing, repository, model, and runtime-mode screens.

## Phase Mapping - ✅

The phase roadmap controls learning order. This plan supplies runtime tasks inside those phases:

| Runtime task | Main phases |
|---|---|
| Task 1 | Phase 2 Security, Phase 4 Data Engineering |
| Task 1A | Phase 2 Security, Phase 4 Data Engineering, Phase 15 Governance |
| Task 1B | Phase 4 Data Engineering, Phase 6 Observability, Phase 15 Governance |
| Task 2 | Phase 2 Security, Phase 5 Backend and Connectors |
| Task 2A | Phase 2 Security, Phase 5 Backend and Connectors |
| Task 3 | Phase 5 Backend, Phase 12 Workflow, Phase 14 Reliability |
| Task 4 | Phase 2 Security, Phase 5 Backend and Connectors |
| Task 5 | Phase 3 Infrastructure, Phase 4 Data, Phase 18 Developer Experience |
| Task 5A | Phase 6 Observability and Tracing, Phase 15 Governance |
| Task 6 | Phase 2 Security, Phase 10 Tooling and Sandboxing |
| Task 7 | Phase 3 Infrastructure, Phase 4 Data, Phase 9 Memory and Retrieval |
| Task 8 | Phase 11 HITL, Phase 17 Frontend, Phase 18 Developer Experience |
| Task 9 | Phase 14 Reliability, Phase 15 Governance, Phase 18 Developer Experience, Phase 19 CI/CD |
| Task 10 | Phase 14 Reliability, Phase 19 CI/CD and FoodSpector Release |

- ✅ Lettered tasks such as 1A and 5A were inserted after the phase crosswalk already referenced task numbers. They run in place. Existing task numbers are not renumbered.
- ✅ Runtime task status and phase status are separate.
- ✅ A runtime task may be implemented only when its active phase prerequisites are approved.
- ⚠️ Completed master Tasks 1 through 6 do not remove the Phase 0, Phase 1, or Phase 2 design gates.

## Work Order

⚠️ Do not start Task 1 until Phase 0 and Phase 1 are approved and the Phase 2 threat-model design gate fixes identity, token, secret, and data boundaries.

### Task 1 - ✅ Hosted identity and data-boundary schema

**Files:**
- Create: hosted migration `<timestamp>_control_plane_identity.sql`
- Create: `src/pr_reviewer/contracts/runner.py`
- Create: `src/pr_reviewer/control_plane/repository_policy.py`
- Modify: `src/pr_reviewer/web/app.py`
- Create: `tests/test_control_plane_identity.py`
- Create: `tests/test_package_boundaries.py`
- Create: `docs/DATA_BOUNDARIES.md`

**Interfaces:**
- Produces: `RunnerCapabilities(mode, docker_available, retrieval_available, verification_available, platform, version)`
- Produces: installation, repository, runner, and repository-assignment rows.
- Produces: `authorize_repository(installation_id, repository_id, runner_id) -> RepositoryAuthorization`

**TDD steps:**
- ✅ Write failing migration tests for renamed repositories, duplicate installations, duplicate active assignments, revoked installations, and cross-installation access.
- ✅ Run `uv run pytest tests/test_control_plane_identity.py -v` and confirm the schema cases fail.
- ✅ Add numeric GitHub identities and foreign keys without changing any applied migration.
- ✅ Store runner credential hashes only. Add revocation time, last-seen time, version, capabilities, and assignment.
- ✅ Add repository authorization tests to every job and token lookup.
- ✅ Add package-boundary tests proving runner modules do not import hosted Neon settings, the GitHub App private key, or webhook secret.
- ✅ Compose hosted routes in `control_plane/app.py` and keep local routes in `runner/local_api.py`.
  This task owns the split of the existing `web/app.py`, which currently serves the webhook. Master
  Task 7 then edits whichever module the webhook route ends up in.
- ✅ Document every hosted and local field in `docs/DATA_BOUNDARIES.md`.
- ✅ Run all backend checks.

### Task 1A - ✅ Retire hosted local-only tables

**Files:**
- Create: hosted migration `<timestamp>_retire_local_only_tables.sql`
- Create: `src/pr_reviewer/control_plane/boundary.py`
- Create: `docs/DATA_BOUNDARIES.md`
- Modify: `tests/conftest.py`
- Test: `tests/test_hosted_boundary_enforcement.py`

Moving the `record_event.py` / `list_events_for_job.py` / `record_model_call.py` /
`fail_review_job.py` writers, and `tests/test_event_writer_target.py`, belong to Task 1B: they
need `local_store/` (Task 5) to exist first. Listing them here too was a leftover from before the
1A/1B split; removed so `scripts/check_task_files.py "Task 1A"` does not flag a Task 1B file
against a task that cannot build it yet.

**Interfaces:**
- Consumes: the hosted and local field lists written by Task 1.
- Produces: a hosted schema that can no longer physically store private review data.
- Produces: `assert_no_private_columns(db: Database) -> None` used as a startup and CI check.

**TDD steps:**
- ⬜ Write a failing test that fails while hosted Neon still has `findings`, `code_chunks`, `human_decisions`, `pull_requests`, or a `model_calls` and `agent_events` shape that accepts rationale, patch text, source text, or embeddings.
- ⬜ Run `uv run pytest tests/test_hosted_boundary_enforcement.py -v` and confirm the boundary cases fail against the current schema.
- ⬜ Migration `0001` created these tables when the design was a single hosted service. Immutable means never edit `0001`, not never drop what it made. Drop or re-scope them in a new migration and record the reason in the migration file.
- ⬜ Keep the redacted hosted lifecycle event stream. Move detailed events, model-call detail, findings, decisions, snapshots, and chunks to local state.
- ⬜ Retire only the tables with no live reader or writer: `findings`, `code_chunks`,
  `human_decisions`, `pull_requests`. All four have zero references in `src/`, so this is executable
  today.
- ⚠️ `agent_events` and `model_calls` have five live references and cannot move yet, because
  `local_store/` does not exist until Task 5. They stay hosted for now behind a documented exemption.
- ⬜ Give `assert_no_private_columns` an explicit `HOSTED_EXEMPTIONS` set containing exactly
  `agent_events` and `model_calls`, and a test asserting the set has not grown. Adding a new exemption
  must fail a build, the same way the package-boundary snapshot works.
- ⬜ Test that a hosted write of private review data is rejected by the schema, not only by convention.
- ⬜ Run `assert_no_private_columns` in CI against a freshly migrated hosted database.
- ⬜ Update `docs/DATA_BOUNDARIES.md` with the retired tables and the new writer targets.
- ⬜ Run all backend checks.

### Task 1B - ✅ Re-scope hosted events and move the detailed writers

⚠️ Runs **after** Task 5, because it needs `local_store/` to exist. Split out of Task 1A, which could
not move writers to a local store that had not been built yet.

**Files:**
- Create: hosted migration `<timestamp>_rescope_hosted_events.sql`
- Modify: `src/pr_reviewer/events/record_event.py`
- Modify: `src/pr_reviewer/events/list_events_for_job.py`
- Modify: `src/pr_reviewer/models/record_model_call.py`
- Modify: `src/pr_reviewer/jobs/fail_review_job.py`
- Modify: `src/pr_reviewer/contracts/errors.py` (new typed error class for `last_error`)
- Modify: `src/pr_reviewer/control_plane/boundary.py`
- Modify: `docs/DATA_BOUNDARIES.md`
- Test: `tests/test_hosted_event_rescope.py`

**TDD steps:**
- ✅ The data boundary permits **redacted lifecycle events** and **aggregate** token and cost numbers
  on the hosted plane. It forbids detailed events and per-call model detail. So this is a re-scope,
  not a deletion: constrain the hosted shape and move the detail local.
- ✅ Write failing tests that a hosted event row cannot carry a free-form payload, and that a hosted
  model-call row carries aggregates only, with no prompt, output, or output hash.
- ✅ Point the four writers at the local store for detail, and keep a redacted hosted write for
  lifecycle and aggregate cost.
- ✅ Constrain `review_jobs.last_error`. `fail_review_job` takes `error: str` and writes it straight to
  a hosted column, so any caller can put a stack trace, a file path, or a diff fragment into Neon.
  The allowlist reason documents the intent and enforces nothing. Replace the free string with a
  typed error class so prose cannot be represented, and update every caller.
- ⚠️ Found during Task 1A. It is the same defect class the task was built to close: a hosted column
  the allowlist permits, holding whatever a caller happens to pass.
- ✅ Remove `agent_events` and `model_calls` from `HOSTED_EXEMPTIONS`. The exemption set must end empty,
  and the test that guards its size must then assert exactly that.
- ✅ Run all backend checks.

### Task 2 - ✅ One-time runner pairing and GitHub App installation

**Files:**
- Create: hosted migration `<timestamp>_runner_protocol.sql`
- Create: `src/pr_reviewer/control_plane/pairing.py`
- Create: `src/pr_reviewer/control_plane/runner_auth.py`
- Create: `src/pr_reviewer/control_plane/pairing_api.py`
- Test: `tests/test_runner_pairing.py`
- Test: `tests/test_runner_auth.py`

**Interfaces:**
- Produces: `create_pairing_code(device_name: str, challenge: str) -> PairingChallenge`
- Produces: `approve_pairing(code, access: VerifiedInstallationAccess, repository_ids: list[int]) -> PairingApproval`
- Produces: `exchange_pairing_code(code, verifier) -> RunnerCredential`
- Produces: `rotate_runner_credential(runner_id, current_credential) -> RunnerCredential`
- Produces: `authenticate_runner(credential: str) -> AuthenticatedRunner`

**TDD steps:**
- ✅ Write failing tests for one-use code, 10-minute expiry, stored hash, PKCE verifier mismatch, wrong user, wrong installation, replay, concurrent exchange, and revoked installation.
- ✅ Test that the returned runner credential appears once and its plaintext is never stored.
- ✅ Require GitHub sign-in and a valid GitHub App installation before pairing approval. Express this
  as a `VerifiedInstallationAccess` value object carrying the user and installation together, which
  cannot be built from loose integers. Task 2A supplies its one real constructor; this task ships a
  test-only builder plus a test that no other module in `src/` constructs it.
- ⚠️ Never accept `github_user_id` and `installation_id` as separate trusted parameters. A caller can
  satisfy one and not the other, and that is a tenancy bypass.
- ✅ Carry the verified repository set on `VerifiedInstallationAccess` as `{github_repository_id: name}`,
  read from the same GitHub response that proved installation access. `approve_pairing` takes bare
  numeric IDs and rejects any ID absent from that set. Never accept a repository name from the caller.
- ✅ Bind selected numeric repository IDs to one active runner.
- ⚠️ Approval must not create the runner row or its `repository_assignments`. `repository_assignments`
  is `unique (repository_id)`, so an approved-but-never-exchanged pairing would hold those repositories
  forever and no later runner could claim them. Approval records the approved selection against the
  pairing row only. `exchange_pairing_code` creates the runner and its assignments in one transaction,
  which also keeps `runners.credential_hash` NOT NULL.
- ✅ Test that a repository ID absent from the verified set is denied. Selecting a repository outside
  your own installation is the tenancy attack `VerifiedInstallationAccess` exists to prevent.
- ✅ Test that an approved pairing that is never exchanged leaves its repositories claimable by a later
  runner. This is the regression test for the lockout above.
- ✅ Approval may pre-check for an already-assigned repository to give a better error, but the
  authoritative check is at exchange under the unique constraint. An approval-time check goes stale
  between approval and exchange.
- ✅ Repository rows are upserted at approval, not at exchange. `repositories` is
  `unique (installation_id, github_repository_id)`, so that write is idempotent and claims no
  exclusivity. Only `runners` and `repository_assignments` wait for exchange.
- ✅ Add credential rotation and immediate revocation.
- ✅ Run all backend checks.

### Task 2A - ✅ Hosted GitHub sign-in and installation access verification

⚠️ Found during Task 2. Task 2 requires "GitHub sign-in and a valid GitHub App installation before
pairing approval" and no task built it, so `approve_pairing` had nothing to trust. Task 2 defines the
`VerifiedInstallationAccess` contract with a test-only builder. This task supplies its one real
constructor.

**Files:**
- Create: hosted migration `<timestamp>_oauth_state.sql`
- Create: `src/pr_reviewer/control_plane/github_oauth.py`
- Create: `src/pr_reviewer/control_plane/oauth_api.py`
- Modify: `src/pr_reviewer/control_plane/pairing.py`
- Test: `tests/test_github_oauth.py`

**Interfaces:**
- Produces: `begin_sign_in(return_to: str) -> SignInChallenge` carrying a one-use `state` for the
  GitHub URL and a separate `binding_secret` for an httponly cookie.
- Produces: `complete_sign_in(code, state, binding_secret) -> VerifiedGitHubUser`
- Produces: `verify_installation_access(user: VerifiedGitHubUser, installation_id) -> VerifiedInstallationAccess | AccessDenied`
- Produces: the only non-test construction site for `VerifiedInstallationAccess`.

**TDD steps:**
- ✅ Write failing tests for a replayed `state`, an expired `state`, a `state` from a different
  browser session, a missing `state`, and a forged callback with no prior `begin_sign_in`.
- ✅ `state` is one-use, short-lived, stored hashed, and consumed atomically. It is CSRF protection,
  so a callback that cannot present a matching unconsumed `state` is rejected.
- ⚠️ Found during Task 2A. `state` alone cannot reject "state from a different browser session",
  because `state` travels through the browser and is exactly what a login-CSRF attacker replays.
  The flow needs a second value that never appears in a URL: a `binding_secret` issued at
  `begin_sign_in`, set as an httponly cookie, and required back at `complete_sign_in`. Store both
  hashed on one row and consume them together in one atomic statement. A callback presenting a valid
  `state` without the matching `binding_secret` is rejected.
- ⚠️ This is not a session system and must not grow into one. One row, one sign-in attempt, deleted
  or consumed when the flow ends. Do not name it `session_token`.
- ✅ Cookie attributes are part of the control and get a test each: `HttpOnly`, `Secure`,
  `SameSite=Lax`, `Path` scoped to the callback, and `Max-Age` matching the state expiry.
  `SameSite=Strict` is the trap: it sounds stronger and silently breaks the flow, because the
  cookie is not sent on the top-level navigation back from github.com.
- ✅ Validate `return_to` against an allowlist of known control-plane paths. An unvalidated
  `return_to` is an open redirect, and an open redirect on an OAuth callback leaks the code.
- ✅ Verify installation control by calling GitHub `/user/installations` with the **user's** OAuth
  token, and confirming `installation_id` is in the response. Do not infer it from anything local.
- ⚠️ The user's OAuth token is used once, in memory, then discarded. It is never persisted, never
  logged, and never reaches the runner. It is not in the Task 1 secret lifecycle table because it
  must never live long enough to have one.
- ✅ Do not add an installation-ownership table. GitHub is authoritative and a local copy becomes a
  stale second source of truth. Revisit only if measurement shows the API call is a real cost.
- ✅ Denial reasons follow the indistinguishability rule: "no such installation" and "installation
  exists but you do not control it" are one reason. See the Phase 2 record, section 6.
- ✅ Add a test asserting this module is the only non-test construction site for
  `VerifiedInstallationAccess` in `src/`, the same shape as the package-boundary snapshot.
- ✅ Any new hosted text, jsonb or array column needs an `ALLOWLIST` entry with a reason, then
  regenerate `docs/DATA_BOUNDARIES.md`.
- ✅ Run all backend checks.

### Task 3 - ✅ Outbound job claim, heartbeat, and acknowledgement protocol

**Files:**
- Create: `src/pr_reviewer/control_plane/runner_jobs.py`
- Create: `src/pr_reviewer/runner/client.py`
- Modify: `src/pr_reviewer/jobs/*.py`
- Test: `tests/test_runner_job_protocol.py`

**Interfaces:**
- Produces: `claim_job(runner: AuthenticatedRunner) -> JobEnvelope | NoJob`
- Produces: `heartbeat_job(runner_id, job_id, lease_token) -> LeaseState`
- Produces: `acknowledge_job(runner_id, job_id, lease_token, result: JobAcknowledgement) -> None`
- Produces: `JobEnvelope` with job ID, installation ID, repository ID, PR number, base SHA, head SHA, policy version, budget, and trace ID.
- Produces: `JobAcknowledgement` with terminal state, redacted error class, aggregate tokens, aggregate cost, latency, and local result hash.

**TDD steps:**
- ✅ Write failing tests for runner authentication, repository assignment, revoked runner, wrong lease, expired lease, duplicate claim, stale head SHA, offline runner, and duplicate acknowledgement.
- ✅ Keep `FOR UPDATE SKIP LOCKED` and bind each lease to the claiming runner.
- ✅ Use bounded HTTPS long polling or short polling with jitter. Do not require an inbound connection to the runner.
- ✅ Reject unknown fields and command strings in `JobEnvelope`.
- ✅ Queue jobs while the runner is offline and expire or supersede them by policy.
- ✅ Record only redacted lifecycle events in Neon.
- ✅ Run all backend checks.

### Task 4 - ✅ Short-lived GitHub token broker and local PR fetch

**Files:**
- Create: `src/pr_reviewer/control_plane/token_broker.py`
- Create: `src/pr_reviewer/runner/github_access.py`
- Modify: `src/pr_reviewer/github/app_client.py`
- Modify: `src/pr_reviewer/github/pull_request.py`
- Test: `tests/test_token_broker.py`
- Test: `tests/test_runner_github_access.py`

**Interfaces:**
- Produces: `issue_job_token(runner_id, job_id, lease_token) -> GitHubJobToken`
- Produces: a token restricted to the job repository and required read or review permissions.
- Produces: `fetch_job_snapshot(job: JobEnvelope, token: GitHubJobToken) -> PullRequestSnapshot`

**TDD steps:**
- ✅ Write failing tests for wrong runner, wrong repository, expired lease, stale head, excessive permissions, token replay after completion, and revoked installation.
- ✅ Keep the GitHub App private key on the control plane.
- ✅ Return the installation token only over authenticated HTTPS and never persist it locally or in Neon.
- ✅ Fetch PR metadata, files, and repository context directly from GitHub on the user's machine.
- ✅ Discard the token after the job finishes or the lease is lost.
- ✅ Run all backend checks.

### Task 5 - ✅ Local daemon, SQLite state, and secret storage

**Files:**
- Create: `src/pr_reviewer/runner/daemon.py`
- Create: `src/pr_reviewer/runner/secrets.py`
- Create: `src/pr_reviewer/local_store/sqlite.py`
- Create: local SQLite migration `<timestamp>_local_state.sql`
- Create: `tests/test_runner_daemon.py`
- Create: `tests/test_local_store.py`
- Create: `tests/test_secret_store.py`

**Interfaces:**
- Produces: `RunnerDaemon.start() -> None` and cooperative `RunnerDaemon.stop(deadline_seconds) -> None`
- Produces: `SecretStore.set(name, value)`, `get(name)`, and `delete(name)`
- Produces: local job, snapshot, finding, event, human-decision, and pending-acknowledgement stores.

**TDD steps:**
- ✅ Write failing tests for restart recovery, duplicate local job, lost network after completion, pending acknowledgement replay, graceful stop, and corrupted local state.
- ✅ Prefer the operating-system secret store. Test the mode `0600` file fallback separately.
- ✅ Test that no secret is ever placed in `os.environ`. Read from the keyring per call and assert the
  daemon environment stays clean, including in a spawned subprocess.
- ✅ Store a trace ID and a per-store sequence on every local event row so Task 5A can join hosted and local halves.
- ✅ Keep runner credential, model keys, GitHub tokens, and Slack secret out of SQLite.
- ✅ Redact secrets from logs, tracebacks, crash reports, and support bundles.
- ✅ Recover a claimed job after daemon restart only while its control-plane lease remains valid.
- ✅ Run all backend checks.

### Task 5A - ✅ Correlated trace IDs and cross-store trace reconstruction

**Files:**
- Create: `src/pr_reviewer/observability/trace.py`
- Create: `src/pr_reviewer/cli/trace.py`
- Modify: `src/pr_reviewer/control_plane/runner_jobs.py`
- Modify: `src/pr_reviewer/local_store/sqlite.py`
- Test: `tests/test_trace_join.py`
- Test: `tests/test_trace_cli.py`

**Interfaces:**
- Consumes: the `JobEnvelope` trace ID from Task 3, hosted `connector_runs` from master Task 8, and local events from Task 5.
- Produces: `TraceSegment` with origin of `hosted` or `local`, trace ID, span ID, parent span ID, timestamp, kind, and redacted payload.
- Produces: `reconstruct_trace(job_id: str, hosted, local) -> list[TraceSegment]` merged into one ordered timeline.
- Produces: `reviewer trace <job-id>` with a redacted human view and a machine-readable export.

**TDD steps:**
- ✅ Write a failing test that a trace assembled from only one store is reported as incomplete, naming which side is missing.
- ✅ Run `uv run pytest tests/test_trace_join.py -v` and confirm the join cases fail.
- ✅ Carry one trace ID from webhook receipt through job claim, token issue, GitHub calls, model calls, decisions, and posting. Every hosted and local row stores it.
- ✅ Add the trace ID to hosted `connector_runs` and to every local event row. The join key is explicit, never inferred from timestamps.
- ✅ Test ordering across two clocks. Use recorded sequence within a store and the causal span parent across stores. Never order a merged trace by wall-clock time alone.
- ✅ Test that the merged output carries no model key, GitHub token, raw patch, source text, or finding rationale beyond the configured redaction level.
- ✅ Test a hosted-only trace, a local-only trace, an offline runner that acknowledged late, and a superseded job.
- ✅ This task owns the Phase 6 proof gate. Reconstructing one review from its job ID must need no manual database work.
- ✅ Run all backend checks.

### Task 6 - ⬜ Container runtime contract and explicit runtime modes

**Files:**
- Create: `src/pr_reviewer/containers/runtime.py`
- Create: `src/pr_reviewer/containers/docker.py`
- Create: `src/pr_reviewer/runner/modes.py`
- Create: `src/pr_reviewer/cli/doctor.py`
- Create: `tests/test_container_runtime.py`
- Create: `tests/test_runner_modes.py`
- Create: `tests/test_doctor_docker.py`

**Interfaces:**
- Produces: `ContainerRuntime.probe() -> ContainerProbe`
- Produces: `ContainerRuntime.run(spec: SandboxSpec) -> SandboxResult`
- Produces: `select_runtime_mode(probe: ContainerProbe, requested: RuntimeMode) -> ModeDecision`
- Produces: typed `SandboxSpec` and `SandboxResult` contracts with no shell-string field.

**TDD steps:**
- ⬜ Write failing doctor tests for missing Docker CLI, stopped daemon, denied socket, failed pull, root container, network access, missing resource limits, and unsupported platform.
- ⬜ Implement Docker as the only v1 `ContainerRuntime`.
- ⬜ Full mode is available only after every required Docker isolation check passes.
- ⬜ Analysis-only mode sets retrieval and executable verification false and forces human approval.
- ⬜ Never auto-install Docker and never fall back to host command execution.
- ⬜ Show the exact disabled features before the user confirms analysis-only mode.
- ⬜ Run all backend checks.

### Task 7 - ⬜ Full-mode local Postgres and pgvector service

**Files:**
- Create: `src/pr_reviewer/local_store/postgres.py`
- Create: `src/pr_reviewer/local_store/postgres_migrations/0000_extensions.sql`
- Create: `docker-compose.runner.yml`
- Create: `tests/test_local_pgvector.py`
- Create: `tests/test_runner_compose.py`

**Interfaces:**
- Produces: `LocalVectorStore.start() -> StoreStatus`, `migrate()`, `health()`, and `stop(preserve_data: bool)`.
- Produces: a local-only Postgres URL generated by the runner and stored as a secret.

**TDD steps:**
- ⬜ Write failing tests for loopback-only binding, named volume, health check, pgvector extension, restart persistence, port collision, and clean stop.
- ⬜ Pin the pgvector image by digest and run it as a non-root user.
- ⬜ Generate a random local database password and keep it out of logs and process arguments.
- ⬜ Start this service only in full mode.
- ⬜ Keep private code chunks and embeddings off hosted Neon by default.
- ⬜ Preserve the volume on normal uninstall and delete it only after explicit confirmation.
- ⬜ Run all backend checks.

### Task 8 - ⬜ Local onboarding UI and user service

**Files:**
- Create: `src/pr_reviewer/cli/service.py`
- Create: `src/pr_reviewer/web/local_auth.py`
- Create: `apps/web/src/app/onboarding/*`
- Create: `apps/web/tests/onboarding.spec.ts`
- Create: `tests/test_user_service.py`
- Create: `tests/test_local_auth.py`

**Interfaces:**
- Produces: localhost onboarding for pairing, repository selection, model key, doctor checks, and runtime mode.
- Produces: `reviewer start`, `stop`, `status`, and `open`.
- Produces: systemd-user service on Linux and launchd user agent on macOS.

**TDD steps:**
- ⬜ Write failing tests for non-loopback binding, missing session secret, CSRF failure, reused pairing code, model-key echo, closed port, and browser-open failure.
- ⬜ Bind to `127.0.0.1` and use a random local session secret.
- ⬜ Submit model keys directly to the local daemon. Never send them through the hosted control plane.
- ⬜ Show full and analysis-only mode differences before confirmation.
- ⬜ Install a user service without administrator rights and verify restart after login.
- ⬜ Keep the CLI usable when no graphical browser exists.
- ⬜ Run backend, Bun, and Playwright checks.

### Task 9 - ⬜ Offline behavior, revocation, updates, and uninstall

**Files:**
- Create: `src/pr_reviewer/runner/update.py`
- Create: `src/pr_reviewer/runner/revocation.py`
- Modify: `src/pr_reviewer/cli/main.py`
- Create: `tests/test_runner_offline.py`
- Create: `tests/test_runner_update.py`
- Create: `tests/test_runner_uninstall.py`

**TDD steps:**
- ⬜ Test runner offline before claim, offline during model call, offline after local completion, revoked while running, credential rotation, and control-plane outage.
- ⬜ Retry redacted acknowledgements without repeating model calls or GitHub posts.
- ⬜ Stop new work immediately after runner or installation revocation.
- ⬜ Verify versioned update checksums before replacing files and keep the prior version for rollback.
- ⬜ Preserve local reviews and container volumes by default on uninstall.
- ⬜ Require explicit confirmation to remove model keys, runner credentials, SQLite data, and pgvector volumes.
- ⬜ Run all project checks.

### Task 10 - ⬜ End-to-end product proof and release gate

**Files:**
- Create: `tests/e2e/test_hosted_to_local_review.py`
- Create: `tests/e2e/test_analysis_only_mode.py`
- Create: `tests/e2e/test_runner_revocation.py`
- Create: `docs/PRODUCT_RUNTIME.md`
- Modify: `docs/INSTALL.md`

**TDD steps:**
- ⬜ Start a test control plane, Neon-compatible Postgres, local runner, local SQLite, local UI, and Docker sandbox.
- ⬜ Send one signed GitHub webhook and verify one hosted job is leased to the assigned runner.
- ⬜ Verify the runner receives a repository-scoped token, fetches the PR, reviews locally, and acknowledges redacted results.
- ⬜ Verify full mode performs retrieval and Docker verification without exposing an inbound local port.
- ⬜ Verify analysis-only mode works without Docker, marks executable verification inconclusive, and prevents auto-post.
- ⬜ Verify offline queueing, reconnect, stale-head supersession, runner revocation, secret redaction, and idempotent completion.
- ⬜ Record the exact install, pair, start, status, update, and uninstall commands.
- ⬜ Run all project checks and save the end-to-end report.

## Done Means - ⬜

- ⬜ Every runtime task has been reviewed under each mapped phase gate.
- ⬜ A user installs and starts `reviewer` without creating a database, GitHub App, personal token, tunnel, or public URL.
- ⬜ GitHub sends webhooks only to the hosted control plane.
- ⬜ The local runner receives jobs through outbound authenticated HTTPS.
- ⬜ The user selects repositories through the shared GitHub App installation.
- ⬜ The hosted schema physically cannot store private review data, proved by a startup and CI check rather than by convention.
- ⬜ One review can be reconstructed end to end from its job ID across the hosted and local stores, redacted, with no manual database work.
- ⬜ GitHub App secrets and Neon credentials never reach installed clients.
- ⬜ Model keys never reach the hosted control plane.
- ⬜ Full mode works only after Docker isolation and local pgvector checks pass.
- ⬜ Analysis-only mode works without Docker and cannot mark executable verification passed.
- ⬜ No untrusted PR code runs on the host.
- ⬜ Jobs wait safely while a runner is offline and resume without duplicate effects.
- ⬜ Runner credentials and repository assignments can be revoked immediately.
- ⬜ The localhost UI has session and CSRF protection.
- ⬜ Installer, update, rollback, and uninstall are tested from versioned assets.

## Traps - ⚠️

- ⚠️ Do not treat completion of this runtime plan as completion of the AI engineering phase roadmap.
- ⚠️ This plan and the master plan write into the same migration directories. Use a timestamp prefix, never a guessed next number.
- ⚠️ Localhost is not reachable from GitHub. Only the hosted control plane receives webhooks.
- ⚠️ Localhost is not an authentication method. Other local processes may call open ports.
- ⚠️ A reusable installation token on disk is a credential leak.
- ⚠️ A control-plane job must never contain a shell command.
- ⚠️ A Docker socket mounted into a sandbox gives the sandbox control of the host.
- ⚠️ Docker installed does not mean Docker isolation works. Doctor checks must prove required settings.
- ⚠️ Analysis-only mode is not verified mode.
- ⚠️ Do not send private code or model keys in hosted traces or support bundles.
- ⚠️ Migration `0001` was written for a single hosted service and still creates tables this architecture forbids. A boundary that lives only in prose is not a boundary.
- ⚠️ A trace split across two stores with no shared key is not a trace.
- ⚠️ Do not order a merged trace by wall-clock time. Two machines, two clocks.
- ⚠️ Do not lose completed local work when the acknowledgement request fails.
- ⚠️ Do not delete user data during normal uninstall or update.

## Open Decisions - ❓

- ❓ Which operating systems ship in v1: Linux only, or Linux and macOS?
- ❓ Which operating-system secret-store library will be supported in v1?
- ❓ Which host and public HTTPS domain will run the shared control plane?
