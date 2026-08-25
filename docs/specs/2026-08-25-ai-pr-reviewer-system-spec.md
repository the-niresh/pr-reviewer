# AI PR Reviewer System Spec

| Mark | Means |
|---|---|
| ⬜ | Not done yet. I tick it when it lands |
| ✅ | Done, or in scope and agreed |
| ❌ | Deliberately not doing this |
| ❓ | Open decision, waiting on me |
| ⚠️ | Known trap. Read before writing the code |

## Goal 1 - ✅ Build a hiring-grade AI PR reviewer

Build an AI pull request reviewer that shows serious AI systems work: GitHub webhooks, durable jobs, retrieval, structured findings, sandbox verification, human approval, traces, cost tracking, evals, and a public installer.

## Goal 2 - ✅ Optimize for selectivity

The system exists to reclaim senior reviewer time. It should surface findings worth human attention. It should not maximize comment count.

## Goal 3 - ✅ Prove claims with evals

The project must publish numbers: precision, recall, false positive rate, cost per PR, verified finding rate, and one-agent versus multi-agent comparison.

## Non-Goal 1 - ❌ Replace human review

The system does not approve or merge PRs. It prepares and posts review findings only within the configured gate.

## Non-Goal 2 - ❌ Publicly disclose security issues

Security findings that explain an exploit must route to private review. They must not be posted on public PRs by default.

## Non-Goal 3 - ❌ Depend on Tiger Data in v1

Use plain Postgres with pgvector first. Keep the data model compatible with later pgvectorscale or Timescale adoption if volume proves the need.

## Architecture - ✅

The system is a modular monolith with a background worker. A GitHub webhook creates durable delivery and job rows. A worker fetches the PR diff, retrieves code context, runs review workflow nodes, verifies findings where possible, applies the gate, and posts or queues findings. Every important action writes to an append-only event spine.

## Tech Stack - ✅

- TypeScript
- Next.js for UI and webhook route
- Postgres for truth, jobs, and events
- pgvector for code memory
- `pg` for runtime Postgres access
- Plain SQL migration files
- LangGraph behind a `WorkflowEngine` interface
- OpenAI and Anthropic behind model provider interfaces
- Docker Compose for local Postgres
- Neon Postgres for hosted demo and production environments
- GitHub App integration
- Vitest for unit and integration tests
- Playwright for UI smoke checks

## Finding Contract - ✅

Every finding must be stored as a typed record:

```ts
type Finding = {
  id: string;
  reviewJobId: string;
  concern: "security" | "correctness" | "tests" | "docs" | "maintainability";
  severity: "critical" | "high" | "medium" | "low" | "info";
  category: string;
  filePath: string;
  lineStart: number;
  lineEnd: number;
  title: string;
  rationale: string;
  evidence: string[];
  confidence: number;
  verified: boolean;
  verificationMethod: "sandbox" | "static" | "not_applicable" | "failed";
  publicSafe: boolean;
  status: "draft" | "queued_for_human" | "posted" | "rejected" | "disputed";
};
```

## Invariants - ✅

- ✅ Every GitHub webhook payload is HMAC-verified before JSON parsing that changes system state.
- ✅ Every GitHub delivery is deduplicated by `X-GitHub-Delivery`.
- ✅ Webhook response returns quickly after durable enqueue.
- ✅ Every model output is validated against the Finding schema.
- ✅ Every finding has file, line, rationale, evidence, confidence, and verification status.
- ✅ Security findings with unsafe disclosure route privately.
- ✅ Append-only event rows cannot be updated or deleted through app code.
- ✅ No human approval decision is overwritten.
- ✅ Confidence is never the only gate for trust.
- ✅ Prompt versions and model names are stored with each model call.
- ✅ Cost is recorded per model call and rolled up per job.
- ✅ Installer never prints secrets.

## Work Order - ⬜

1. ✅ Create the repo scaffold, locked spec, contracts, and test commands.
2. ✅ Create Postgres schema for deliveries, jobs, findings, chunks, prompts, decisions, and events.
3. ⬜ Build GitHub webhook ingress with HMAC, dedupe, and durable enqueue.
4. ⬜ Build worker job claiming and retry state.
5. ⬜ Build event spine helpers and cost ledger.
6. ⬜ Build GitHub App client and PR diff fetcher.
7. ⬜ Build code chunker, indexer, embeddings, and pgvector storage.
8. ⬜ Build hybrid retrieval with vector search, full-text search, and reciprocal rank fusion.
9. ⬜ Build model provider interface and prompt registry.
10. ⬜ Build one-agent reviewer baseline.
11. ⬜ Build sandbox and static verification.
12. ⬜ Build gate and human approval queue.
13. ⬜ Build GitHub posting with private security routing.
14. ⬜ Build LangGraph workflow engine behind an interface.
15. ⬜ Add specialist agents and compare against the baseline.
16. ⬜ Build mined golden set from git history.
17. ⬜ Build eval harness and publish metrics.
18. ⬜ Build trace, review queue, and cost dashboard.
19. ⬜ Build public installer, setup wizard, doctor, demo, and uninstall.
20. ⬜ Add docs, screenshots, and hiring-focused README.

## Done Means - ⬜

- ⬜ A fresh user can install locally from a terminal flow.
- ⬜ The UI opens on localhost with a working dashboard.
- ⬜ A GitHub webhook can create a review job.
- ⬜ A worker can review a real PR.
- ⬜ Findings are structured and stored.
- ⬜ Retrieved context is visible in the trace.
- ⬜ Verified findings are marked separately from model-only findings.
- ⬜ Human approval controls public posting.
- ⬜ Security findings do not disclose exploit steps publicly.
- ⬜ Eval report compares no retrieval, retrieval, one agent, and multi-agent.
- ⬜ README shows real metrics and install steps.

## Traps - ⚠️

- ⚠️ Do not gate only on self-reported confidence. It is not calibrated unless measured.
- ⚠️ Do not post security exploit details to public PRs.
- ⚠️ Do not parse or persist untrusted webhook input before HMAC checks.
- ⚠️ Do not keep job state only in memory.
- ⚠️ Do not build four agents before a one-agent baseline exists.
- ⚠️ Do not let installer echo secrets or commit `.env.local`.
- ⚠️ Do not make the dashboard the main project. The main project is verified review quality.

## Open Decisions - ❓

- ❓ Should the first hosted install domain be `get.pr-reviewer.dev`, a GitHub Pages URL, or a raw GitHub release asset?
- ❓ Which repo should be the first public demo target besides FoodSpector?
- ❓ Should v1 auto-post safe findings or require human approval for all findings until evals pass?
- ❓ Which sandbox should v1 use first: Docker-only, local process with read-only checkout, or both?
