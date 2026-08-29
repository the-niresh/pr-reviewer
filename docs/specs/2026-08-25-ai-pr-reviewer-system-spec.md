# AI PR Reviewer System Spec

| Mark | Means |
|---|---|
| ⬜ | Not done yet. I tick it when it lands |
| ✅ | Done, or in scope and agreed |
| ❌ | Deliberately not doing this |
| ❓ | Open decision, waiting on me |
| ⚠️ | Known trap. Read before writing the code |

## Source - ✅ Blog Input

✅ This spec is based on the Antern article, "Designing an AI Pull-Request Review Agent", read on 2026-08-26.

✅ We keep the parts that make the system serious: five-step design, typed findings, webhook HMAC, idempotency, fast webhook ACK, retrieval, specialist review path, event spine, human approval, reliability, cost control, and evals.

✅ We change the vendor choice. The data store is Neon Postgres with pgvector. We do not use TigerData, Timescale, or pgvectorscale in v1.

✅ The article calls its implementation list a 20-phase roadmap but numbers it from Phase 0 through Phase 20. This spec treats all 21 entries as required topic coverage, not as a safe literal build order.

## Goal 1 - ✅ Build a real AI PR reviewer for FoodSpector

Build an AI pull request reviewer that can be used on FoodSpector while real users depend on that product. The reviewer must reduce review noise, catch useful issues, keep a trace of its work, and avoid public security disclosure.

## Goal 2 - ✅ Show serious AI engineering

The project must show backend engineering, agent design, retrieval, structured outputs, verification, human approval, evals, security, reliability, cost control, and local install flow.

## Goal 3 - ✅ Optimize for selectivity

The system exists to save senior reviewer time. It should surface findings worth attention. It should not maximize comment count.

## Goal 4 - ✅ Prove claims with numbers

The README must show precision, recall, false positive rate, verified finding rate, cost per PR, and a one-agent versus specialist-agent comparison.

## Goal 5 - ✅ Publish a local installer

A public user must be able to run one terminal command, answer setup prompts, enter keys locally, start the API, worker, and UI, and see a dashboard on localhost.

## Non-Goal 1 - ❌ Replace human review

The system does not approve or merge PRs. It prepares findings, verifies them when possible, posts only when the gate allows it, and routes hard cases to people.

## Non-Goal 2 - ❌ Publicly disclose security issues

Findings that explain an exploit must not be posted on public PRs by default. They route to a private connector, such as Slack, email, or the local approval queue.

## Non-Goal 3 - ❌ Use TigerData in v1

Use Neon Postgres with pgvector and plain SQL. Do not add TigerData, Timescale, DiskANN, or pgvectorscale unless measured volume proves plain Postgres is not enough.

## Non-Goal 4 - ❌ Start with four model calls by default

Build a one-agent baseline first. Add specialist agents only after the eval harness proves better findings per dollar.

## Non-Goal 5 - ❌ Explore the repository in an agentic loop

The repository is cloned, indexed, profiled and graphed, and the sandbox executes commands. The model
still receives context the system chose, in one call. A tool loop that decides what to open next makes
cost unpredictable and makes a quality change impossible to attribute, which breaks evaluation, the
cost gate, and the regression gate together. Revisit only if measured recall proves capped by
cross-file context the code graph cannot supply.

## Architecture - ✅

The product has a hosted Python control plane and an installed Python runner. The hosted FastAPI service receives GitHub webhooks, verifies HMAC, deduplicates deliveries, stores durable jobs in Neon, and returns quickly. It owns GitHub App secrets and leases typed jobs to paired runners over outbound HTTPS.

The installed runner opens the localhost UI, keeps model keys and private review data local, requests short-lived repository-scoped GitHub tokens, fetches PR data, runs review, applies gates, and posts approved findings. The user's machine does not expose a public webhook port.

Hosted Neon stores users, GitHub installations, repository identities, runner registrations, webhook deliveries, job leases, redacted lifecycle events, aggregate costs, and eval reports. Local SQLite stores daemon state, PR snapshots, findings, detailed events, and pending acknowledgements. Full mode uses local Docker Postgres with pgvector for private code chunks and embeddings.

The workflow sits behind a `WorkflowEngine` interface. v1 uses a simple Python engine in the local runner. LangGraph can be added behind the same interface only after specialist eval gates pass.

## Delivery Tracking Model - ✅

The project uses three linked levels of tracking:

- ✅ A **phase** is an AI engineering concept and review gate. It explains what must be understood and proved.
- ✅ A **task** is a small TDD code unit in the master or product-runtime plan.
- ✅ A **gate** is reproducible evidence that the phase is complete.

The phase roadmap is `docs/superpowers/plans/2026-08-27-ai-engineering-phase-roadmap.md`. The master task plan is `docs/superpowers/plans/2026-08-25-ai-pr-reviewer.md`. The product-runtime task plan is `docs/superpowers/plans/2026-08-27-hosted-control-plane-local-runner.md`.

✅ Phases define the learning and review order. Tasks define the implementation order inside those phases. One task may support several phases.

✅ Completed code is phase evidence, not automatic phase completion. Each phase needs its own learning record, proof gate, review, and owner approval.

✅ The adapted phase order is:

1. ✅ Phase 0: Cognitive Design.
2. ✅ Phase 1: System Architecture.
3. ✅ Phase 2: Security and Trust Boundaries.
4. ✅ Phase 3: Infrastructure.
5. ✅ Phase 4: Data Engineering.
6. ✅ Phase 5: Backend, API, and Connectors.
7. ✅ Phase 6: Observability and Tracing.
8. ✅ Phase 7: Evaluation Foundation.
9. ✅ Phase 8: LLM and Reasoning Baseline.
10. ✅ Phase 9: Memory Architecture and Retrieval.
11. ✅ Phase 10: Tooling and Sandboxing.
12. ✅ Phase 11: Human-in-the-Loop.
13. ✅ Phase 12: Workflow Orchestration.
14. ✅ Phase 13: Multi-Agent Systems.
15. ✅ Phase 14: Reliability.
16. ✅ Phase 15: Governance.
17. ✅ Phase 16: Economics and Cost Control.
18. ✅ Phase 17: Frontend Engineering.
19. ✅ Phase 18: Developer Experience.
20. ✅ Phase 19: CI/CD for AI and FoodSpector Release.
21. ✅ Phase 20: Continuous Learning.

⚠️ This order intentionally differs from the source list. Evaluation is defined before model and agent experiments. Security, infrastructure, data, and event recording are designed before later AI behavior. HITL and sandbox rules are proved before public posting. Frontend starts after backend and event contracts are stable.

## Tech Stack - ✅

- ✅ Python 3.12 or newer for backend, agents, worker, evals, and installer helper code.
- ✅ FastAPI for webhook and dashboard APIs.
- ✅ `psycopg` plus plain SQL migrations for database access.
- ✅ Neon Postgres for hosted control-plane data.
- ✅ Python `sqlite3` for installed runner state.
- ✅ Docker Postgres with pgvector for private full-mode retrieval.
- ✅ pgvector for local code embeddings.
- ✅ Postgres full-text search for exact code and identifier search.
- ✅ OpenAI and Anthropic behind model provider interfaces.
- ✅ GitHub App auth for fetching PR data and posting reviews.
- ✅ Hosted Postgres-backed jobs for v1 queueing.
- ✅ Outbound HTTPS job claims from installed runners.
- ✅ Slack, Telegram, and Discord notification connectors behind one channel interface.
- ✅ Every channel carries a declared confidentiality of `restricted` or `ordinary`.
- ✅ Local approval queue in the app for human review.
- ✅ Docker is required for full mode.
- ✅ Analysis-only mode works without Docker, skips executable verification, and requires human approval.
- ✅ `uv` for Python package commands.
- ✅ Bun for the TypeScript frontend only.
- ✅ TypeScript frontend under `apps/web`.
- ✅ pytest, ruff, and mypy for backend checks.
- ✅ Playwright for UI smoke checks once `apps/web` exists.

## Connector Model - ✅

Each external service is a connector with a typed contract:

```python
class ConnectorResult(BaseModel):
    connector: str
    operation: str
    ok: bool
    status_code: int | None
    external_id: str | None
    error_kind: str | None
    request_bytes: int
    response_bytes: int
    payload_hash: str | None
    latency_ms: int
```

✅ Required v1 connectors:

- ✅ GitHub connector: fetch installation token, PR metadata, files, patch, comments, and post review.
- ✅ Control-plane connector: pair runner, claim job, renew lease, request job token, acknowledge result, rotate credential, and revoke runner.
- ✅ Model connector: call OpenAI or Anthropic with timeout, retry, structured output, token cost, and prompt version.
- ✅ Hosted database health check and local pgvector health check.
- ✅ Notification connectors: Slack, Telegram, and Discord, sending security or approval alerts
  without secrets in logs and without finding detail in a push title.
- ✅ Sandbox connector: run bounded verification commands and return logs.

## Finding Contract - ✅

The model produces an untrusted candidate:

```python
class FindingCandidate(BaseModel):
    concern: Literal["security", "correctness", "tests", "docs", "maintainability"]
    severity: Literal["critical", "high", "medium", "low", "info"]
    category: str
    file_path: str
    line_start: int
    line_end: int
    title: str
    rationale: str
    evidence: list[str]
    confidence: float
```

System code adds trusted state before storage or routing:

```python
class Finding(BaseModel):
    id: str
    review_job_id: str
    head_sha: str
    candidate: FindingCandidate
    verification_status: Literal["passed", "failed", "inconclusive", "not_applicable"]
    verification_method: Literal["sandbox", "static", "not_applicable"]
    verifier_version: str | None
    public_safe: bool
    status: Literal["draft", "queued_for_human", "posted", "rejected", "disputed"]
    connector_trace_ids: list[str]
```

## Data Model - ✅

- ✅ Hosted `github_deliveries` stores webhook delivery IDs and minimal event metadata.
- ✅ Hosted `review_jobs` stores durable job state, assigned runner, attempts, leases, and retry timestamps.
- ✅ Hosted installation, repository, runner, pairing, and repository-assignment tables enforce account boundaries.
- ✅ Local `pull_request_snapshots` stores fetched PR metadata and file patches.
- ✅ Local `code_chunks` stores repo path, line range, content, hash, embedding, and text-search vector.
- ✅ `prompt_versions` stores immutable prompt text and version metadata.
- ✅ Local `model_calls` stores provider, model, prompt version, tokens, cost, latency, and structured output hash.
- ✅ Local `findings` stores typed finding records.
- ✅ Local `human_decisions` stores approvals, rejects, edits, and disputes.
- ✅ Local `agent_events` stores detailed append-only spans, tool calls, decisions, and errors.
- ✅ Hosted `connector_runs` stores allowlisted connector metadata only.
- ✅ `eval_cases` stores mined cases from git history.
- ✅ Hosted `eval_reports` stores aggregate metrics only: dataset version, prompt version, model,
  retrieval mode, run count, and the rolled-up numbers.
- ✅ Local `eval_results` stores case-level rows, because a case names content from a private repository.

## Invariants - ✅

- ✅ Every GitHub webhook payload is HMAC-verified before JSON parsing that changes system state.
- ✅ Every GitHub delivery is deduplicated by `X-GitHub-Delivery`.
- ✅ Webhook response returns quickly after durable enqueue.
- ✅ Job state is stored in Postgres, not process memory.
- ✅ Installed runners connect outbound only and never receive Neon credentials or GitHub App secrets.
- ✅ Model keys and private review data remain local.
- ✅ Short-lived GitHub installation tokens are repository-scoped, kept in memory, and discarded after the job.
- ✅ Full mode requires Docker and local pgvector.
- ✅ Analysis-only mode cannot mark executable verification passed or auto-post.
- ✅ Missing Docker never causes untrusted code to run on the host.
- ✅ Every external call has a timeout and an event row.
- ✅ Every model output is validated against the `FindingCandidate` schema.
- ✅ Repository text reaches a prompt only through the single untrusted-input wrapper.
- ✅ Repository instruction files are read only from the default branch at a resolved commit SHA, never from the pull request head.
- ✅ Every review records which changed files it read and which it omitted, with a reason for each omission.
- ✅ A review that omitted a changed file reports partial coverage and is never presented as complete.
- ✅ Diff packing is deterministic and carries a packing strategy version in every eval report.
- ✅ Every finding has file, line, rationale, evidence, confidence, verification status, and public-safety status.
- ✅ Confidence is metadata only until calibration is measured.
- ✅ Verified findings are stronger than confidence-only findings.
- ✅ Security findings with unsafe disclosure route privately, and only to channels declared restricted.
- ✅ A restricted notification's title carries no finding detail, because a push preview renders on a locked screen.
- ✅ A generated repository profile is inferred, not asserted. It may steer review focus and never sets policy.
- ✅ A profile claim becomes authoritative only when a human promotes it into the default-branch instruction file.
- ✅ Prompt versions and model names are stored with each model call.
- ✅ Cost is recorded per model call and rolled up per job.
- ✅ Human approval decisions are append-only.
- ✅ Installer never prints secrets.
- ✅ Plan and spec files stay ignored by git unless you explicitly ask to track them.

## Autonomy Policy - ✅

- ✅ v1 default: all findings queue for human approval unless the user enables auto-post.
- ✅ Auto-post can only post public-safe, schema-valid findings.
- ✅ Critical security findings always route privately.
- ✅ Unverified findings can be shown in the dashboard, but must be marked as unverified.
- ✅ Once evals show stable precision and recall, safe verified findings may auto-post.

## Work Order - ⬜

1. ✅ Keep master-plan Tasks 1 through 6 as completed implementation evidence.
2. ⬜ Complete and approve the Phase 0 cognitive-design gate using one real FoodSpector PR.
3. ⬜ Complete and approve the Phase 1 architecture gate and ADR set.
4. ⬜ Complete the Phase 2 threat-model design gate before adding control-plane identity or token endpoints.
5. ⬜ Complete `docs/superpowers/plans/2026-08-27-hosted-control-plane-local-runner.md` through its authenticated job-claim demo under Phases 3 through 6.
6. ⬜ Continue master-plan Task 7 with hosted and local data boundaries fixed.
7. ⬜ Complete Phase 7 evaluation foundations before model, retrieval, verification, or specialist comparisons.
8. ⬜ Measure the Phase 8 one-agent baseline before enabling retrieval or specialist mode.
9. ⬜ Prove sandbox and HITL gates before any public posting path can be enabled.
10. ⬜ Complete the FoodSpector shadow run before enabling auto-post.
11. ⬜ Ship the versioned installer only after full and analysis-only end-to-end tests pass.

## Done Means - ⬜

- ⬜ A fresh user can install locally from a terminal command.
- ⬜ Every Phase 0 through Phase 20 topic has a learning record and a reproduced proof gate.
- ⬜ Every implementation task maps back to at least one approved phase.
- ⬜ The setup flow asks for secrets without printing them.
- ⬜ The UI opens on localhost with a working dashboard.
- ⬜ The user does not provide a Neon URL, GitHub App secret, personal token, tunnel, or public URL.
- ⬜ The installed runner receives jobs over outbound authenticated HTTPS.
- ⬜ Full mode requires Docker and analysis-only mode shows its limits clearly.
- ⬜ A GitHub webhook can create a review job.
- ⬜ A worker can review a real PR.
- ⬜ Findings are structured and stored.
- ⬜ Retrieved context is visible in the trace.
- ⬜ Model calls show provider, model, prompt version, tokens, latency, and cost.
- ⬜ Verified findings are marked separately from model-only findings.
- ⬜ Human approval controls public posting.
- ⬜ Security findings do not disclose exploit steps publicly.
- ⬜ Eval report compares no retrieval, retrieval, one agent, specialist agents, and sandbox verification.
- ⬜ README shows real metrics, install steps, screenshots, and limits.

## Traps - ⚠️

- ⚠️ Do not gate only on self-reported confidence.
- ⚠️ Do not post security exploit details to public PRs.
- ⚠️ Do not treat a Telegram or Discord group as private. Its membership changes without you.
- ⚠️ Do not let a generated codebase summary assert an invariant. One wrong line poisons every review.
- ⚠️ Do not parse or persist untrusted webhook input before HMAC checks.
- ⚠️ Do not hardcode the next migration number in a plan. Two plans share the migration directories.
- ⚠️ Do not read review guidance from the branch under review.
- ⚠️ Do not let a context budget drop a changed file without saying so.
- ⚠️ Do not keep job state only in memory.
- ⚠️ Do not build four agents before a one-agent baseline exists.
- ⚠️ Do not add Redis until Postgres job polling is measured as the bottleneck.
- ⚠️ Do not add Timescale or pgvectorscale until event or chunk volume proves the need.
- ⚠️ Do not let installer echo secrets or commit `.env`.
- ⚠️ Do not give installed runners Neon credentials or GitHub App secrets.
- ⚠️ Do not store private source, raw diffs, model keys, or sandbox logs in hosted Neon.
- ⚠️ Do not run PR code on the host when Docker is missing.
- ⚠️ Do not call analysis-only output verified.
- ⚠️ Do not claim localhost can receive GitHub webhooks.
- ⚠️ Do not make the dashboard the main project. The main project is verified review quality.
- ⚠️ Do not follow the article's phase table as a literal dependency order.
- ⚠️ Do not mark a phase complete only because one related code task passed.

## Open Decisions - ❓

- ❓ Which operating systems ship in v1: Linux only, or Linux and macOS?
- ❓ Which operating-system secret-store library will be supported in v1?
- ❓ Which host and public HTTPS domain will run the shared control plane?
- ❓ Which licensed public repositories will supply publishable holdout cases?
- ❓ Which real FoodSpector PR will be used for the Phase 0 walkthrough?
