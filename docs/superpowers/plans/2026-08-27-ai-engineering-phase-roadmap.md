# AI PR Reviewer AI Engineering Phase Roadmap

| Mark | Means |
|---|---|
| ⬜ | Not done yet. I tick it when it lands |
| ✅ | Done, or in scope and agreed |
| ❌ | Deliberately not doing this |
| ❓ | Open decision, waiting on me |
| ⚠️ | Known trap. Read before writing the code |

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` for code tasks. Use strict TDD. Stop after each phase gate so the owner can inspect the design, tests, proof, and learning record.

**Goal - ✅:** Build the full AI PR reviewer while teaching and proving each AI engineering concept one phase at a time.

**Architecture:** Phases are learning and system gates. Tasks in the master and product-runtime plans are the smaller TDD code units used to complete those gates. A task may support several phases, but a phase is complete only when its written proof gate passes.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, psycopg, plain SQL, Neon Postgres, local SQLite, local Postgres with pgvector, Docker, GitHub App API, OpenAI, Anthropic, pytest, ruff, mypy, uv, Bun, TypeScript, and Playwright.

**Spec:** `docs/specs/2026-08-25-ai-pr-reviewer-system-spec.md`

**Master Plan:** `docs/superpowers/plans/2026-08-25-ai-pr-reviewer.md`

**Product Runtime Plan:** `docs/superpowers/plans/2026-08-27-hosted-control-plane-local-runner.md`

## Why This Order - ✅

The source article contains a useful 21-topic coverage list numbered Phase 0 through Phase 20. Its literal order is not a safe build order. It places frontend before stable backend contracts, evaluation after multi-agent work, observability after model work, and infrastructure and data after retrieval.

This roadmap keeps every topic but uses dependency order:

1. ✅ Decide what the system should do and where people must decide.
2. ✅ Fix architecture, trust boundaries, infrastructure, and data ownership.
3. ✅ Build backend facts and event recording before model behavior.
4. ✅ Define evaluation before the baseline, retrieval, and specialist experiments.
5. ✅ Add sandbox verification and human gates before public posting.
6. ✅ Add workflow and specialist complexity only after simpler paths are measured.
7. ✅ Finish with reliability, governance, cost, UI, release, and learning loops.

## Tracking Rules - ✅

- ✅ Phase numbers in this file define the learning and review order.
- ✅ Task numbers in the implementation plans define the TDD build order inside a phase.
- ✅ Do not infer phase status from task status. Completed Tasks 1 through 6 are evidence for several phases, not proof that Phases 0 through 6 are complete.
- ✅ Each phase ends with one written learning record, one design or code review, and one proof gate.
- ✅ The learning record states the question, options, decision, failure modes, tests, result, and remaining limits.
- ✅ A phase is marked complete only after the proof is reproduced and the owner approves it.
- ✅ Later enabling work may already exist, but no new implementation skips the active phase gate.
- ✅ Changes to autonomy, public posting, security routing, model choice, prompts, or retrieval require rerunning the related eval and release gates.

## Current State - ⬜

- ✅ Master Tasks 1 through 6 are implemented and tested.
- ✅ The system spec, master plan, and product-runtime plan exist.
- ✅ Phase 0 is complete. The map, failure matrix, autonomy level and selectivity policy are approved,
  and the proof gate was reproduced against FoodSpector commit `43ec43a`. Record:
  `docs/phases/phase-0-cognitive-design.md`.
- ✅ Phase 1 is complete. Component table, trust boundaries, dependency rule and four ADRs approved.
  Record: `docs/phases/phase-1-system-architecture.md`.
- ✅ The Phase 2 **design gate** is approved. Record: `docs/phases/phase-2-security-design-gate.md`.
- ✅ **Implementation is unblocked.** Master Task 10A is the recommended first coding task.
- ⬜ The Phase 2 **test gate** stays open until the end of the build.
- ⬜ Phases 3 and 4 are the next learning gates, and their task work is the runtime plan's identity,
  boundary and job-claim tasks.
- ⬜ Phase 1 has architecture material but still needs a complete ADR set and owner approval.
- ⚠️ Do not start product-runtime Task 1 or master Task 7 until Phases 0, 1, and the Phase 2 threat-model design gate are approved.
- ⚠️ Applied migration `0001` still creates hosted tables the data boundary forbids. Product-runtime Task 1A retires them and must run before any further hosted schema work.

## Phase 0 - ✅ Cognitive Design

**Article topic:** Phase 0, Cognitive Design.

**Learning goal:** Understand the human review system before assigning work to software or a model.

**Required outputs:** A senior-reviewer workflow map, mechanical-versus-judgment table, precise trigger, typed output, autonomy table, selectivity policy, failure matrix, and definition of a useful finding.

**Task map:** System spec goals, non-goals, Finding contract, invariants, and autonomy policy. No new product code is required for this phase.

**Proof gate:** Walk one real FoodSpector PR through the human map. Every system step must trace back to a human need or an identified failure. The owner approves the map before new implementation starts.

## Phase 1 - ✅ System Architecture

**Article topic:** Phase 1, System Architecture.

**Learning goal:** Turn the cognitive design into clear service, module, data, and trust boundaries.

**Required outputs:** Hosted control-plane and local-runner diagram, data-flow diagram, dependency rule, connector boundaries, runtime modes, failure paths, and ADRs for Neon, Postgres jobs, simple Python workflow, and local Docker isolation.

**Task map:** Master Tasks 1 through 8 and product-runtime Tasks 1 through 7 contain architecture evidence.

**Proof gate:** Review every component against its trigger, input, output, owner, stored data, timeout, retry rule, and fallback. No secret or private-code path may cross an undeclared boundary.

## Phase 2 - ⬜ Security and Trust Boundaries

**Article topic:** Phase 11, Security.

**Learning goal:** Design security before adding more endpoints, connectors, model calls, or command execution.

**Required outputs:** Threat model, asset list, attacker list, GitHub App permission table, tenant-isolation rules, prompt-injection boundaries, a single untrusted-input wrapper, default-branch-only instruction sources, secret lifecycle, public-security-disclosure policy, and sandbox threat model.

**Task map:** Master Tasks 3, 6 through 8, 10, 10B, 13 through 15, 17, 18, 23, and 25. Product-runtime Tasks 1, 1A, 2 through 6, and 8 through 10.

**Proof gate:** HMAC, tenant isolation, repository scope, secret canaries, token expiry, runner revocation, unsafe finding routing, and host-execution denial all have failing-then-passing tests.

## Phase 3 - ⬜ Infrastructure

**Article topic:** Phase 13, Infrastructure.

**Learning goal:** Build the minimum durable hosted and local runtime needed by later phases.

**Required outputs:** Hosted FastAPI control plane, Neon environments, local runner service, local state directories, Docker runtime checks, release container setup, health checks, and backup and recovery rules.

**Task map:** Master Tasks 2, 23 through 25. Product-runtime Tasks 1, 5 through 10.

**Proof gate:** A clean test environment starts, reports health, survives a process restart, and shuts down without losing durable state or exposing a public local port.

## Phase 4 - ⬜ Data Engineering

**Article topic:** Phase 14, Data Engineering.

**Learning goal:** Match each data shape to its access, retention, privacy, and consistency needs.

**Required outputs:** Hosted Neon schema, local SQLite schema, local pgvector schema, immutable migrations, job leases, append-only records, retention rules, and deletion paths.

**Task map:** Master Tasks 2, 4, 5, 7 through 9, 12, 18, and 20. Product-runtime Tasks 1, 1A, 5, 7, 9, and 10.

**Proof gate:** Fresh migration, repeat migration, rollback procedure, lease concurrency, tenant isolation, retention, and delete-account tests pass on Postgres compatible with Neon. The hosted schema also passes `assert_no_private_columns`, proving the data boundary in the schema rather than in prose.

## Phase 5 - ⬜ Backend, API, and Connectors

**Article topic:** Phase 3, Backend and API.

**Learning goal:** Build typed, authenticated, idempotent boundaries around GitHub and the local runner.

**Required outputs:** Webhook ingress, GitHub connector, runner pairing, job claim and heartbeat, short-lived token broker, PR lifecycle, connector result contract, and stale-safe review posting.

**Task map:** Master Tasks 3, 4, 6 through 8, 17, and 21. Product-runtime Tasks 2 through 4 and 8.

**Proof gate:** One signed webhook is acknowledged after durable enqueue, one assigned runner claims it, one repository-scoped token fetches the PR, and retries produce no duplicate job or review.

## Phase 6 - ⬜ Observability and Tracing

**Article topic:** Phase 10, Observability and Tracing.

**Learning goal:** Make every important action reconstructable before model behavior becomes complex.

**Required outputs:** Correlation IDs, append-only events, connector records, model-call ledger, trace reconstruction, redaction policy, latency records, cost records, and failure alerts.

**Task map:** Master Tasks 5, 8, 10, 18, 20 through 22, and 26. Product-runtime Tasks 3 through 5, 5A, 9, and 10.

**Proof gate:** Starting from one review job ID, reconstruct webhook receipt, job claims, GitHub calls, model calls, decisions, posting, cost, and errors without reading secrets or unrestricted private source. The trace spans the hosted and local stores, so product-runtime Task 5A owns this gate and `reviewer trace <job-id>` is the reproduction command.

## Phase 7 - ⬜ Evaluation Foundation

**Article topic:** Phase 9, Evaluation.

**Learning goal:** Define ground truth and metrics before choosing prompts, retrieval, or more agents.

**Required outputs:** Mined candidate set, human-checked holdout set, positive and negative PRs, deterministic finding matching, repeated runs, precision, recall, false findings per PR, selectivity, verification rate, review coverage, packing strategy version, latency, and cost.

**Task map:** Master Tasks 9, 10A, 11, 13, 14, 19, 20, 24, and 26. Task 9 alone must satisfy the proof gate.

**Proof gate:** The eval runner produces a versioned report from a frozen holdout set, driven by a recorded `FixtureReviewer` and making no model call. A human checks uncertain matches. No LLM judge silently changes ground truth. The harness must be provable here, before Phase 8 supplies a real reviewer.

## Phase 8 - ⬜ LLM and Reasoning Baseline

**Article topic:** Phase 5, LLM and Reasoning.

**Learning goal:** Measure the smallest useful model path before adding retrieval or specialist agents.

**Required outputs:** Provider interface, OpenAI and Anthropic adapters, immutable prompt registry, structured `FindingCandidate` output, quoted untrusted input, deterministic diff budgeting with reported omissions, one-agent diff-only review, and baseline eval report.

**Task map:** Master Tasks 10, 10A, 10B, 11, and 18.

**Proof gate:** The same holdout set runs at least three times per case. The report names dataset, prompt, provider, model, run count, quality, latency, and cost.

## Phase 9 - ⬜ Memory Architecture and Retrieval

**Article topic:** Phase 6, Memory Architecture.

**Learning goal:** Give the reviewer only the repository context that improves measured review quality.

**Required outputs:** Stable code chunks, embedding generations, exact identifier search, vector search, reciprocal rank fusion, freshness checks, repository isolation, one shared context budget with the packed diff, a candidate-only repository profile, and a deterministic code graph for blast radius.

**Task map:** Master Tasks 10A, 12, 13, and 13A. Product-runtime Task 7.

**Proof gate:** Compare no retrieval, vector-only, text-only, hybrid, profile-only, graph-only, and profile-plus-graph on the frozen eval set. Keep each source only if it improves the stated quality and cost gates. A source that does not help is disabled and the negative result is recorded.

## Phase 10 - ⬜ Tooling and Sandboxing

**Article topic:** Phase 7, Tooling and Sandboxing.

**Learning goal:** Turn model claims into checked evidence without letting untrusted PR code reach the host.

**Required outputs:** Typed tool registry, capability scopes, Docker-only execution, resource limits, network rules, static checks, test reproduction, log limits, and analysis-only behavior.

**Task map:** Master Tasks 14 and 23. Product-runtime Tasks 6, 7, and 10.

**Proof gate:** Malicious fixtures cannot access host files, Docker socket, metadata services, secrets, or unrestricted network. Missing Docker never falls back to host execution.

## Phase 11 - ⬜ Human-in-the-Loop

**Article topic:** Phase 19, Human-in-the-Loop.

**Learning goal:** Spend human attention only where consequence, uncertainty, or disclosure risk requires it.

**Required outputs:** Deterministic gate, approval queue, private security route, classified notification channels for Slack, Telegram, and Discord, approve, reject, edit, dispute, stale-head check, and analysis-only restrictions.

**Task map:** Master Tasks 15, 17, 21, 22, and 24. Product-runtime Tasks 8 and 10.

**Proof gate:** A public-safe verified finding can reach approval, a high security finding routes privately to a channel declared restricted, a restricted push title carries no finding detail, an inconclusive finding cannot auto-post, and every human decision is append-only.

## Phase 12 - ⬜ Workflow Orchestration

**Article topic:** Phase 4, Workflow Orchestration.

**Learning goal:** Coordinate review steps through explicit state and typed transitions without binding the system to one framework.

**Required outputs:** `WorkflowEngine` contract, simple Python engine, typed state, step deadlines, resume points, cancellation, stale-job handling, and event hooks.

**Task map:** Master Tasks 16 through 18. Product-runtime Tasks 3 through 5 and 9.

**Proof gate:** Kill the worker at each durable boundary and resume without repeating model calls, verification, or GitHub posting.

## Phase 13 - ⬜ Multi-Agent Systems

**Article topic:** Phase 8, Multi-Agent Systems.

**Learning goal:** Test whether specialist reasoning is worth its extra calls, latency, merge errors, and failure paths.

**Required outputs:** Specialist contracts, selective routing, parallel execution, merge and dedup rules, disagreement handling, timeout policy, and optional LangGraph adapter.

**Task map:** Master Tasks 19 and 20.

**Proof gate:** Specialist mode remains disabled unless it beats the one-agent baseline by the measured recall, precision, and useful-findings-per-dollar gates in the master plan.

## Phase 14 - ⬜ Reliability

**Article topic:** Phase 12, Reliability.

**Learning goal:** Prove that expected service, worker, model, database, and network failures have bounded outcomes.

**Required outputs:** Timeout policy, retry classes, backoff, circuit breakers, job leases, idempotency keys, dead-letter state, stale protection, offline acknowledgements, and fault tests.

**Task map:** Master Tasks 4, 7, 8, 10, 17, 18, and 23. Product-runtime Tasks 3, 4, 6, 9, and 10.

**Proof gate:** Fault injection covers GitHub retry, model timeout, database disconnect, runner crash, control-plane outage, lost acknowledgement, stale head, and duplicate delivery without duplicate effects.

## Phase 15 - ⬜ Governance

**Article topic:** Phase 15, Governance.

**Learning goal:** Make changes, access, decisions, retention, and disputes inspectable and reversible where possible.

**Required outputs:** Audit queries, prompt history, model history, role rules, repository assignments, retention, deletion, dispute records, feedback evidence threshold, and autonomy-change record.

**Task map:** Master Tasks 8 through 10, 15, 17, 20 through 22, 24, and 26. Product-runtime Tasks 1, 2, 8, and 9.

**Proof gate:** For any posted finding, show who or what approved it, what evidence and versions were used, what data remains, how to dispute it, and how access is revoked.

## Phase 16 - ⬜ Economics and Cost Control

**Article topic:** Phase 16, Economics and Cost Control.

**Learning goal:** Measure quality per dollar and stop work before a repository budget is exceeded.

**Required outputs:** Provider price table, token counts, per-call and per-PR cost, model budget, budget reservation, hard block, dashboard totals, and quality-versus-cost report.

**Task map:** Master Tasks 5, 10, 11, 13, 18 through 20, 22, 24, and 26.

**Proof gate:** Concurrent jobs cannot overspend a repository budget, and the eval report compares useful findings per dollar across baseline, retrieval, verification, and specialist modes.

## Phase 17 - ⬜ Frontend Engineering

**Article topic:** Phase 2, Frontend Engineering.

**Learning goal:** Give users a quiet work surface for repeated review, approval, tracing, and setup tasks.

**Required outputs:** Local auth, onboarding, review list, finding detail, approval queue, trace view, cost view, health state, empty state, loading state, error state, and keyboard-safe actions.

**Task map:** Master Tasks 21, 22, and 25. Product-runtime Task 8.

**Proof gate:** Playwright covers onboarding, review inspection, approval, rejection, private security routing, trace display, cost display, narrow screens, and localhost security checks.

## Phase 18 - ⬜ Developer Experience

**Article topic:** Phase 17, Developer Experience.

**Learning goal:** Make local development, prompt work, diagnosis, install, update, and support repeatable without exposing secrets.

**Required outputs:** `reviewer` CLI, doctor checks, prompt inspection, trace export with redaction, test fixtures, install, start, stop, status, update, rollback, and uninstall.

**Task map:** Master Tasks 10, 20 through 23, 25, and 26. Product-runtime Tasks 5, 8, and 9.

**Proof gate:** A clean supported machine can install, pair, diagnose, start, update, roll back, and uninstall from versioned assets without administrator rights or secret output.

## Phase 19 - ⬜ CI/CD for AI and FoodSpector Release

**Article topic:** Phase 18, CI/CD for AI.

**Learning goal:** Gate software, prompt, model, retrieval, and release changes with the checks that match their risk.

**Required outputs:** Python and frontend CI, migration checks, security scans, container checks, eval regression gate, signed release assets, canary path, rollback, and FoodSpector shadow run.

**Task map:** Master Tasks 20 and 23 through 26. Product-runtime Tasks 9 and 10.

**Proof gate:** Release checks pass, install proof passes from a versioned asset, and FoodSpector completes at least 30 non-draft PRs over at least 14 days with the measured release gates recorded.

## Phase 20 - ⬜ Continuous Learning

**Article topic:** Phase 20, Continuous Learning.

**Learning goal:** Improve from checked outcomes without letting noisy or hostile feedback silently change behavior.

**Required outputs:** Dispute review, feedback evidence threshold, old-feedback decay, drift report, dataset versioning, prompt comparison, model comparison, and autonomy-change approval.

**Task map:** Master Tasks 9, 20, 24, and 26.

**Proof gate:** A proposed prompt, model, retrieval, or routing change is tested against the frozen holdout and recent checked cases. It cannot ship when precision, noise, safety, or cost gates regress.

## Done Means - ⬜

- ⬜ Every article topic from Phase 0 through Phase 20 has a mapped phase in this roadmap.
- ⬜ Every phase has a learning record, task map, tests, proof gate, and owner approval.
- ⬜ Every master and product-runtime task maps back to at least one phase.
- ⬜ Cognitive design and system architecture are approved before new implementation resumes.
- ⬜ Evaluation is defined before LLM, retrieval, verification, and specialist comparisons.
- ⬜ Security, HITL, and sandbox gates pass before public posting can be enabled.
- ⬜ The one-agent baseline is measured before specialist mode is built or enabled.
- ⬜ FoodSpector shadow evidence passes before auto-post is considered.
- ⬜ The public README reports measured results and known limits without publishing private code or secrets.

## Traps - ⚠️

- ⚠️ The source calls this a 20-phase roadmap but numbers it from 0 through 20, which is 21 entries.
- ⚠️ Do not copy the source's literal build order. It places several dependent topics too late.
- ⚠️ Do not mark a phase complete because one related task passed.
- ⚠️ Do not build the dashboard before backend and event contracts are stable.
- ⚠️ Do not build specialist agents before the one-agent baseline and eval set exist.
- ⚠️ Do not let an LLM judge silently create ground truth.
- ⚠️ An eval harness that needs a live model cannot gate the model, and Phase 7 cannot close on a Phase 8 task.
- ⚠️ A trace split across the hosted and local stores with no shared join key is not a trace.
- ⚠️ Do not treat model confidence as a posting decision.
- ⚠️ Do not read review guidance from the branch under review.
- ⚠️ Do not treat a chat group as a private channel, and do not put finding detail in a push title.
- ⚠️ Do not let a model-generated codebase summary assert an invariant.
- ⚠️ Do not let a context budget drop a changed file without saying so.
- ⚠️ Do not run untrusted code on the host when Docker is missing.
- ⚠️ Do not publish private security details, source, traces, or model keys.

## Open Decisions - ❓

- ❓ Which real FoodSpector PR will be used for the Phase 0 walkthrough?
- ❓ Which operating systems ship in v1: Linux only, or Linux and macOS?
- ❓ Which operating-system secret-store library will be supported in v1?
- ❓ Which host and public HTTPS domain will run the shared control plane?
- ❓ Which licensed public repositories will supply publishable holdout cases?
