# Phase 1 - ✅ System Architecture

| Mark | Means |
|---|---|
| ⬜ | Not done yet. I tick it when it lands |
| ✅ | Done, or in scope and agreed |
| ❌ | Deliberately not doing this |
| ❓ | Open decision, waiting on me |
| ⚠️ | Known trap. Read before writing the code |

**Status - ✅ APPROVED 2026-08-27.** Component table, trust boundaries, dependency rule and the four
ADRs are approved by the owner, including that ADR-004 is explicitly not reversible. Proof gate
reproduced, three gaps found and closed. Phase 2 is now the active phase.

## Provenance - ✅

✅ Assembled from the spec, the master plan, and the product-runtime plan, which already contain most
of these decisions scattered across three files. This phase collects them, fills the gaps, and states
the rules in a form a test can enforce. The proof gate at the bottom found three real gaps.

## 1 - ✅ Why there are two planes

Two facts force the whole shape, and everything else follows from them.

1. ⚠️ **GitHub cannot deliver a webhook to a laptop.** It needs a stable public HTTPS endpoint.
2. ⚠️ **The user's private source must not leave their machine.** Their model key must not either.

So there is a **hosted control plane** that is publicly reachable and owns the GitHub App secrets, and
an **installed local runner** that holds the code and the keys and talks **outbound only**. The runner
never listens on a public port. The control plane never sees a diff.

Everything awkward about this system is the cost of holding both facts at once. It is worth naming
because a reader will ask "why not just host it all", and the answer is that hosting it all means
uploading a customer's private source to your server.

## 2 - ✅ Component table

Every component against the eight attributes the proof gate demands. `t/o` is timeout.

### Hosted control plane

| Component | Trigger | In → Out | Stores | t/o | Retry | Fallback |
|---|---|---|---|---|---|---|
| Webhook ingress | GitHub delivery | signed payload → 202 | delivery ID, job row | 10s | GitHub retries | reject, GitHub redelivers |
| Pairing | user starts onboarding | device name → one-time code | code hash, expiry | 5s | none, user retries | code expires in 10 min |
| Runner auth | every runner call | credential → runner identity | credential hash | 2s | none | 401, runner backs off |
| Job claim | runner polls | runner identity → job envelope or none | lease, attempt count | 30s poll | runner re-polls with jitter | lease expires, job requeues |
| Token broker | runner requests, holds lease | lease → repo-scoped token | nothing, token is not persisted | 5s | 1 retry | job fails, lease released |
| Hosted database | any of the above | SQL → rows | identity, jobs, redacted events, aggregate cost | 5s | connection retry | job stays queued |

### Local runner

| Component | Trigger | In → Out | Stores | t/o | Retry | Fallback |
|---|---|---|---|---|---|---|
| Runner client | daemon loop | outbound HTTPS → job envelope | pending acks | 30s | backoff with jitter | queue locally, retry |
| Daemon | service start | job → acknowledgement | claimed job state | per step | per step | resume on restart while lease holds |
| GitHub access | job claimed | token → PR snapshot | snapshot, locally | 20s | 2 retries | job fails, no partial review |
| Diff budget | snapshot ready | snapshot → packed diff | packed items, omissions | none, pure | none | omit with a reason, never silently |
| Reviewer | packed diff ready | context → finding candidates | model call ledger | 120s | fallback model chain | job fails, cost recorded |
| Retrieval (full mode) | before the model call | query → chunks | chunks, embeddings | 10s | 1 retry | proceed with diff only |
| Sandbox (full mode) | candidate needs proof | spec → result | logs, locally | hard wall clock | none | `inconclusive`, route to a human |
| Gate | candidates verified | candidate + policy → route | findings | none, pure | none | queue for a human |
| Notifications | route says alert | finding → message | delivery receipt | 10s | 3 retries | surface in the dashboard |
| Poster | human approved | findings → one review | review and comment IDs | 20s | idempotent retry | leave queued, never double-post |
| Local SQLite | everything above | SQL → rows | snapshots, findings, decisions, detailed events | 2s | none | daemon halts loudly |
| Local pgvector (full mode) | indexing and retrieval | SQL → rows | chunks, embeddings, profile, graph | 5s | 1 retry | drop to analysis-only |

## 3 - ✅ Trust boundaries

Four boundaries. Crossing one changes what the data is allowed to be.

| # | Boundary | What crosses inward | What must never cross outward |
|---|---|---|---|
| B1 | Internet → control plane | signed GitHub webhooks, authenticated runner calls | GitHub App private key, webhook secret, Neon credentials |
| B2 | Control plane → runner | job envelope (typed IDs and policy only), short-lived repo-scoped token | Neon credentials, App private key, reusable tokens |
| B3 | Runner → control plane | terminal state, redacted error class, aggregate tokens, cost, latency, result hash | source, diffs, rationale, sandbox logs, model keys, embeddings |
| B4 | Untrusted content → prompt | repository text, only via `wrap_untrusted` | any path that lets that text set policy or reach a shell |

⚠️ B4 is the one people forget is a boundary at all. A diff is data. A retrieved README is data. An
instruction file from the **default branch** is guidance, and even then it may only steer focus.

## 4 - ✅ Dependency rule

A boundary that is only prose is a wish. This one is a test (`tests/test_package_boundaries.py`).

- ✅ `contracts/*` is imported by everything and imports nothing of ours. It is the shared vocabulary.
- ❌ `control_plane/*` must not import `runner/*`, `local_store/*`, `reviewer/*`, `retrieval/*`,
  `verification/*`, or `containers/*`. The control plane cannot review.
- ❌ `runner/*` and `local_store/*` must not import hosted database settings, the GitHub App private
  key, or the webhook secret. The runner cannot reach Neon.
- ✅ `connectors/*` may be imported by both planes, and holds no credential itself. Credentials are
  passed in by whichever plane owns them.
- ✅ `jobs/*` is hosted queue state. `workflow/*` is local step state. They are deliberately separate,
  so no component has two competing opinions about what a job is doing.

## 5 - ✅ Failure paths

| Failure | Immediate effect | Recovery | Who is told |
|---|---|---|---|
| Control plane down | runner cannot claim | runner retries with jitter, jobs queue in Neon | dashboard health |
| Runner offline | jobs sit unclaimed | claimed on reconnect, stale ones superseded or expired | dashboard |
| Runner crashes mid-review | lease expires | job requeues, workflow resumes at the last durable step | event spine |
| Model provider down | review cannot run | fallback model chain, then job fails with cost recorded | dashboard, notification |
| Neon interrupted | claims and acks fail | connection retry, runner holds pending acks locally | health endpoint |
| Ack lost after local completion | control plane thinks it is running | pending-ack replay, no model call repeats | event spine |
| Docker missing or broken | no executable verification | analysis-only mode, findings marked `inconclusive` | onboarding and dashboard |
| Head SHA moves mid-review | work is now stale | supersede, never post to an old SHA | event spine |
| Budget exhausted | review stops | partial result marked partial, never presented as complete | dashboard |

## 6 - ✅ Architecture decision records

### ADR-001 - ✅ Neon Postgres with pgvector, not a bundled vendor store

**Context.** The source article consolidates vectors, events and rollups into one commercial
Postgres-compatible product, in a sponsored placement.
**Decision.** Take the *argument* (one store beats three, one pool, one backup, real joins) and reject
the *vendor*. Plain Postgres with `pgvector`, Neon for the hosted plane, local Docker Postgres for
private full-mode retrieval.
**Consequences.** No approximate-nearest-neighbour index and no hypertables. At thousands of chunks
and hundreds of events a day, exact scan plus a GIN index is fine and free.
**Reversal trigger.** Measured vector scan latency exceeding the review budget at real chunk counts,
or event volume making time-partitioning necessary. Measure before switching.

### ADR-002 - ✅ Postgres-backed job queue, not Redis

**Context.** A durable queue is needed for webhook to review handoff.
**Decision.** `FOR UPDATE SKIP LOCKED` on a Postgres table, with leases bound to a runner.
**Consequences.** One fewer service to run, back up and secure. Claim latency is higher than Redis.
**Reversal trigger.** Claim latency above 2 seconds at the expected worker count, or Postgres
connection pressure becoming a measured limit. Benchmark is part of Task 18.

### ADR-003 - ✅ A simple Python engine behind `WorkflowEngine`, not LangGraph in v1

**Context.** The review is a resumable multi-step workflow. LangGraph is the default choice.
**Decision.** Define the `WorkflowEngine` interface first (`run`, `resume`, `get_state`) and implement
it in plain Python. LangGraph becomes a second implementation that must pass the same tests.
**Consequences.** More code written by us, and total control over resume semantics and step state.
**Reversal trigger.** Only if specialist mode passes its Phase 13 gate and the fan-out genuinely needs
what LangGraph provides. The interface exists so this is an addition, not a rewrite.

### ADR-004 - ✅ Docker-only isolation, with no host fallback

**Context.** Verification runs code from a stranger's pull request.
**Decision.** Untrusted commands run only in a locked-down container: no network, no host secrets, no
Docker socket, non-root, read-only root, dropped capabilities, resource and wall-clock limits.
**Consequences.** Full mode requires Docker. Without it the product runs analysis-only, which cannot
claim executable verification and cannot auto-post.
**Reversal trigger.** None. ⚠️ There is no acceptable configuration in which untrusted PR code runs on
the host. This ADR is not reversible, only replaceable by a stronger isolation primitive.

## Proof gate - ✅ Reproduced

✅ Reviewed every component in section 2 against its eight attributes, and confirm no secret or private
code path crosses an undeclared boundary. Three gaps found, and all three are closed. Each was an
already-approved rule that the plans were simply silent about, so none needed a new decision:

- ⚠️ **G1. Notification secrets are undeclared.** The runtime plan's Data Boundary lists the runner
  credential and model keys, and never mentions the Slack, Telegram or Discord webhook secret. Only a
  Task 5 test step mentions it in passing. ✅ **Closed.** Runtime plan Data Boundary now lists notification secrets as runner-local, and a
  security invariant states the runner sends directly so a finding never transits the hosted service.
- ⚠️ **G2. `web/app.py` has no declared owner.** It currently serves the webhook. Runtime Task 1 says
  hosted routes move to `control_plane/app.py` and local routes live in `runner/local_api.py`, but no
  task lists `web/app.py` in its files. ✅ **Closed.** Runtime Task 1 now lists `web/app.py` and owns the split.
- ⚠️ **G3. Eval reports are ambiguous.** The spec lists them under hosted Neon. A report holds metrics,
  which is fine, but it also names dataset case IDs that come from private repositories.
  ✅ **Closed.** Spec now splits hosted `eval_reports` (aggregate only) from local `eval_results`
  (case-level).

## Settled - ✅

- ✅ Component table, trust boundaries and dependency rule approved as written.
- ✅ All four ADRs approved. ADR-004 has no reversal trigger by design.
- ✅ G1, G2 and G3 closed. They applied constraints already approved, so they needed no new call.

## Open Decisions - ❓

- ❓ Should the four ADRs move to a browsable `docs/adr/` directory? Offered, not yet decided.
