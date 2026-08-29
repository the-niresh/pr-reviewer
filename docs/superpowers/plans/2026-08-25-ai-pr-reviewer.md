# AI PR Reviewer Implementation Plan

| Mark | Means |
|---|---|
| ⬜ | Not done yet. I tick it when it lands |
| ✅ | Done, or in scope and agreed |
| ❌ | Deliberately not doing this |
| ❓ | Open decision, waiting on me |
| ⚠️ | Known trap. Read before writing the code |

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans`. Use strict TDD for behavior work. Each task starts with a failing test, receives a code review, and ends with all project checks passing.

**Goal - ✅:** Build an AI PR reviewer that can run in shadow mode on FoodSpector, prove its review quality with measured evals, protect private code and secrets, route unsafe findings to people, and ship through a safe public installer.

**Architecture:** The product has a hosted Python control plane and an installed Python runner. The hosted FastAPI service receives GitHub webhooks, owns GitHub App secrets, stores shared job metadata in Neon, and gives authenticated jobs to local runners over outbound HTTPS. The local runner opens the localhost UI, keeps user model keys local, fetches PR data with short-lived installation tokens, runs review and Docker verification, and posts approved findings.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, psycopg, plain SQL, Neon Postgres, local SQLite, local Postgres with pgvector in full mode, Docker, GitHub App API, OpenAI, Anthropic, pytest, ruff, mypy, uv, Bun, TypeScript, and Playwright.

**Spec:** `docs/specs/2026-08-25-ai-pr-reviewer-system-spec.md`

**Phase Roadmap:** `docs/superpowers/plans/2026-08-27-ai-engineering-phase-roadmap.md`

**Product Runtime Plan:** `docs/superpowers/plans/2026-08-27-hosted-control-plane-local-runner.md`

## Non-Goals

- ❌ The reviewer does not approve or merge pull requests.
- ❌ The reviewer does not post exploit details to public pull requests.
- ❌ The reviewer does not treat more comments as better review quality.
- ❌ The reviewer does not enable specialist agents without measured proof.
- ❌ The reviewer does not train or fine-tune a model in v1.
- ❌ The reviewer does not explore the repository in an agentic loop in v1. It clones and indexes the
  repository, and the system chooses the context before one model call. See the recorded decision below.

## Global Constraints

- ✅ Durable fixes only. Do not hide broken behavior with sleeps, swallowed errors, loose types, or fake success states.
- ✅ Backend, worker, agents, retrieval, verification, evals, and installer helper code use Python.
- ✅ Frontend uses TypeScript and Bun under `apps/web`.
- ✅ Use Neon Postgres for hosted control-plane data and local Docker Postgres with pgvector for full-mode private retrieval.
- ✅ Hosted Neon credentials, the GitHub App private key, and the webhook secret never leave the control plane.
- ✅ Installed runners never connect directly to Neon.
- ✅ Installed runners use outbound HTTPS only. They do not expose a public webhook port.
- ✅ User model keys stay in the operating-system secret store, with a mode `0600` file only as a documented fallback.
- ✅ Full mode requires a supported container runtime and provides repository retrieval plus executable verification.
- ✅ Analysis-only mode works without Docker, skips executable verification, marks results inconclusive, and keeps public auto-post disabled.
- ✅ Never install Docker automatically and never run untrusted PR code on the host.
- ✅ Use plain SQL and `psycopg`. Do not use Prisma or Drizzle.
- ✅ Use Postgres-backed jobs. Do not add Redis until a measured queue limit is reached.
- ✅ Do not use TigerData, Timescale, DiskANN, or pgvectorscale in v1.
- ✅ Applied SQL migrations are immutable. `schema_migrations` is keyed by filename, so a migration file can never be renamed after it is applied.
- ✅ Applied migrations `0001` through `0004` keep their numbers. Every new migration in every set uses a UTC timestamp prefix `YYYYMMDDHHMM_name.sql`, because two plans write into the same migration directories and a shared counter races.
- ✅ The one exception is the local pgvector extension bootstrap, which keeps a `0000_` prefix so it always sorts first.
- ✅ No plan or task states a literal migration number for new work. The author picks the timestamp when the file is written.
- ✅ Webhook HMAC verification happens before JSON parsing or state changes.
- ✅ GitHub deliveries are deduplicated by `X-GitHub-Delivery`.
- ✅ Repository names are labels, not identity. Scope data by installation ID and repository ID.
- ✅ A denial or error reason must be computable from data the caller is already authorised to see.
  Two states a caller cannot distinguish by right must return the same reason.
- ✅ No authorization lookup is unscoped. Filtering by repository ID alone is a cross-tenant read.
- ✅ A test that enforces a structural rule about the code parses the code, it does not grep it.
  Use `ast` for Python, an HTML parser for markup. A regex over source text produces silent false
  positives, and a security control that guesses from text is not a control. Precedent:
  `tests/test_package_boundaries.py`.
- ✅ Pull request code, diffs, comments, commit messages, and repository docs are untrusted input.
- ✅ Repository text reaches a prompt only through the single untrusted-input wrapper.
- ✅ Repository instruction files are read only from the default branch at a resolved commit SHA. A pull request never supplies the guidance used to review itself.
- ✅ A review that could not read every changed file reports partial coverage. It never presents a budget-truncated or patch-omitted review as complete.
- ✅ Diff packing is deterministic and carries a packing strategy version.
- ✅ File sensitivity is derived from the repository, never asserted by a model, and every score
  carries the evidence behind it.
- ✅ The model produces `FindingCandidate` records only. System code owns IDs, verification, public safety, status, and posting.
- ✅ Confidence is stored for later calibration. It does not decide posting.
- ✅ Untrusted PR commands run only inside a locked-down Docker container.
- ✅ Security findings never expose exploit details on a public PR.
- ✅ Restricted findings reach only channels the operator has declared `restricted`. Confidentiality
  is a declared property, never inferred from the transport.
- ✅ A generated repository profile is inferred model output. It may steer review focus and may never
  assert an invariant or influence routing, verification, or posting.
- ✅ A profile claim becomes authoritative only when a human promotes it into the default-branch
  instruction file.
- ✅ Every external call has a timeout, typed result, audit event, and allowlisted log metadata.
- ✅ Every model call stores provider, model, prompt version, tokens, latency, cost, and output hash.
- ✅ Auto-post stays disabled until eval thresholds and the FoodSpector shadow run both pass.
- ✅ Public installs use versioned release assets. Never execute a mutable script from `main`.
- ✅ Private code, snapshots, traces, and findings have retention and deletion rules.
- ✅ Plan and spec files stay ignored by git unless explicitly requested.

## Recorded Decision - ✅ Prepared context, not an agentic loop

✅ The repository is cloned and indexed (Tasks 7, 12, 13A) and the sandbox executes commands inside a
container (Task 14). What v1 does not do is give the model a tool loop and let it decide what to open
next.

✅ **Why.** An exploration loop varies its path per run, so repeated eval runs would measure path
variance on top of output variance, cost per PR would stop being predictable against the USD 0.25
budget, and a quality change could no longer be attributed to a prompt change because the exploration
changed too. That breaks the Phase 7 harness, the Phase 16 cost gate, and the Phase 20 regression gate
at the same time.

✅ **The strongest case for a loop is cross-file blast radius, and Task 13A's parsed code graph answers
that deterministically.** A call graph has a correct answer. An agent grepping for callers does not.

⬜ **Trigger to revisit.** After the Phase 8 baseline and the Phase 9 seven-way context comparison, if
high-value recall is demonstrably capped by cross-file context that retrieval, the profile, and the
graph all fail to supply. Then it becomes a gated experiment with a pass mark, exactly like specialist
mode in Phase 13. It never becomes a default.

## Measured Release Gates

- ✅ Baseline and retrieval reports use a manually checked holdout set with positive and negative PRs.
- ✅ Every published metric names the dataset version, prompt version, provider, model, retrieval mode, and run count.
- ✅ Auto-post requires at least 80% precision for eligible findings and no more than 0.25 false findings per reviewed PR on the holdout set.
- ✅ Critical and high security findings always remain private, even after the auto-post gate passes.
- ✅ Specialist mode stays disabled unless it improves high-value recall by at least 5 percentage points without lowering precision and improves useful findings per dollar by at least 20%.
- ✅ FoodSpector shadow mode runs on at least 30 non-draft PRs over at least 14 days before auto-post can be considered.
- ✅ The default per-PR model budget is USD 0.25 and is configurable per repository.
- ✅ Redis is reconsidered only if queue claim latency exceeds 2 seconds at the expected worker count or Postgres connection pressure becomes a measured limit.

## Phase and Task Tracking - ✅

- ✅ The phase roadmap controls AI engineering learning order and phase approval.
- ✅ This master plan controls small TDD code tasks for the complete reviewer.
- ✅ The product-runtime plan controls hosted control-plane and installed-runner tasks.
- ✅ One task may support several phases. A completed task is evidence, not automatic phase completion.
- ✅ Each phase needs a learning record, a reproduced proof gate, a review, and owner approval.
- ✅ Completed Tasks 1 through 6 stay complete, but Phase 0 is still active until the human-review map and failure matrix are approved.
- ✅ Phase 0, Phase 1, and the Phase 2 design gate are approved as of 2026-08-27. Implementation is unblocked.
- ⚠️ Do not infer phase order from task numbers. Use the phase roadmap crosswalk.
- ✅ Lettered tasks such as 10A and 10B were inserted after the numbering was already referenced by the roadmap crosswalk. They run in place, between Task 10 and Task 11. Existing task numbers are not renumbered.

## File Structure

- ✅ `pyproject.toml` - Python package config and test commands.
- ✅ `src/pr_reviewer/web/app.py` - FastAPI webhook route.
- ✅ `src/pr_reviewer/db/*.py` - Postgres access and migration runner.
- ✅ `src/pr_reviewer/db/migrations/0001_*.sql` through `0004_*.sql` - applied base schema.
- ✅ `src/pr_reviewer/jobs/*.py` - durable queue behavior.
- ✅ `src/pr_reviewer/events/*.py` - append-only event helpers.
- ✅ `src/pr_reviewer/github/*.py` - GitHub App and PR fetch code.
- ⬜ `src/pr_reviewer/github/lifecycle.py` - event action policy, supersession, and stale-head checks.
- ⬜ `src/pr_reviewer/github/repository_fallback.py` - bounded clone fallback for omitted patches.
- ⬜ `src/pr_reviewer/connectors/*.py` - typed connectors and allowlisted audit metadata.
- ⬜ `src/pr_reviewer/evals/*.py` - eval contracts, mining, matching, metrics, and runner.
- ⬜ `src/pr_reviewer/models/*.py` - provider adapters and model-call ledger.
- ⬜ `src/pr_reviewer/prompts/registry.py` - immutable prompt registry.
- ⬜ `src/pr_reviewer/contracts/finding_candidate.py` - untrusted model finding contract.
- ⬜ `src/pr_reviewer/reviewer/*.py` - baseline, diff budgeting, hunk rendering, specialists, and merge.
- ⬜ `src/pr_reviewer/retrieval/*.py` - chunking, embedding, indexing, hybrid search, repository
  profile, and code graph.
- ⬜ `src/pr_reviewer/notifications/*.py` - channel interface and confidentiality policy.
- ⬜ `src/pr_reviewer/verification/*.py` - Docker and static verification.
- ⬜ `src/pr_reviewer/gates/*.py` and `src/pr_reviewer/hitl/*.py` - routing and human decisions.
- ⬜ `src/pr_reviewer/workflow/*.py` - workflow interface and engines.
- ⬜ `src/pr_reviewer/reliability/*.py` - retry, circuit, budget, and queue controls.
- ⬜ `src/pr_reviewer/security/*.py` - repository policy, trusted instruction sources, prompt boundaries, and retention.
- ⬜ `src/pr_reviewer/web/local_auth.py` - localhost dashboard session checks.
- ⬜ `src/pr_reviewer/control_plane/*.py` - runner pairing, job claims, token broker, and runner revocation.
- ⬜ `src/pr_reviewer/runner/*.py` - outbound runner client, daemon, local state, and runtime modes.
- ⬜ `src/pr_reviewer/local_store/*.py` - SQLite state and full-mode local pgvector access.
- ⬜ `apps/web` - Bun and TypeScript dashboard.
- ⬜ `.github/workflows/*.yml` - CI and release checks.
- ⬜ `Dockerfile` and `compose.release.yml` - pinned release services.
- ⬜ `src/pr_reviewer/cli/*.py` and `scripts/install.sh` - public setup and installer.

## Work Order

✅ Phase 0, Phase 1, and the Phase 2 design gate are approved. ⚠️ Still complete the product-runtime plan through its authenticated job-claim demo before starting Task 7. The phase roadmap controls learning order. The runtime plan defines which work stays hosted and which work runs on the user's machine.

### Task 1 - ✅ Python scaffold and contracts

**Files:** `pyproject.toml`, `.gitignore`, `.env.example`, `README.md`, `src/pr_reviewer/contracts/*.py`, `tests/test_contracts.py`

**Status:** Completed and checked with ruff, mypy, and pytest.

### Task 2 - ✅ Postgres schema, migrations, and Neon

**Files:** `docker-compose.yml`, `src/pr_reviewer/db/*.py`, `src/pr_reviewer/db/migrations/0001_initial.sql`, `docs/DATABASE.md`, `tests/test_migrate.py`

**Status:** Completed against local Postgres and Neon with strict TLS.

### Task 3 - ✅ GitHub webhook ingress

**Files:** `src/pr_reviewer/web/app.py`, `src/pr_reviewer/github/verify_signature.py`, `tests/test_webhook.py`, `tests/test_github_signature.py`

**Status:** HMAC, required headers, malformed JSON, body limits, dedupe, and durable enqueue are covered.

### Task 4 - ✅ Durable review jobs

**Files:** `src/pr_reviewer/jobs/*.py`, `src/pr_reviewer/worker/main.py`, `tests/test_jobs.py`, `tests/test_worker.py`

**Status:** Enqueue, `FOR UPDATE SKIP LOCKED` claim, lease renewal, retry, completion, and failure are covered.

### Task 5 - ✅ Event spine and cost ledger

**Files:** `src/pr_reviewer/events/*.py`, `src/pr_reviewer/models/record_model_call.py`, `tests/test_events_and_models.py`

**Status:** Append order, JSON safety, model cost precision, latency, and atomic event writes are covered.

### Task 6 - ✅ GitHub App client and paged PR fetcher

**Files:** `src/pr_reviewer/github/tokens.py`, `src/pr_reviewer/github/app_client.py`, `src/pr_reviewer/github/pull_request.py`, `tests/test_github_pull_request.py`

**Status:** GitHub App JWT, installation token, PR normalization, and paged file fetch are complete.

**Known follow-up:** Task 7 adds installation and repository identity, PR action policy, superseded jobs, stale-head checks, and a fallback for omitted GitHub patches.

### Task 7 - ⬜ Installation identity and PR lifecycle safety

**Files:**
- Create: hosted migration `<timestamp>_pr_lifecycle.sql`
- Create: `src/pr_reviewer/github/lifecycle.py`
- Create: `src/pr_reviewer/github/repository_fallback.py`
- Modify: `src/pr_reviewer/contracts/github.py`
- Modify: `src/pr_reviewer/github/pull_request.py`
- Modify: `src/pr_reviewer/web/app.py`
- Test: `tests/test_github_lifecycle.py`
- Test: `tests/test_github_repository_fallback.py`

**Interfaces:**
- Produces: `RepositoryIdentity(installation_id: int, repository_id: int, owner: str, name: str)`
- Produces: `PullRequestSnapshot` with repository identity, draft state, base SHA, head SHA, and patch completeness.
- Produces: `handle_pull_request_event(delivery: GitHubDelivery) -> LifecycleDecision`
- Produces: `ensure_complete_diff(snapshot: PullRequestSnapshot, fetcher: RepositoryFetcher) -> PullRequestSnapshot`

**TDD steps:**
- ⬜ Write failing tests for `opened`, `reopened`, `ready_for_review`, `synchronize`, draft, closed, and unsupported actions.
- ⬜ Run `uv run pytest tests/test_github_lifecycle.py -v` and confirm the new cases fail.
- ⬜ Consume the installation and numeric repository IDs created by the product-runtime plan. Never edit an applied migration.
- ⬜ Add one active job per repository, PR number, and head SHA. Mark older active jobs `superseded` on a new head SHA.
- ⬜ Write failing tests for null patches, truncated patches, binary files, unsafe paths, clone timeout, and clone size limits.
- ⬜ Add a bounded shallow-clone or compare fallback. Never place repository paths outside the allocated work directory.
- ⬜ Record why each changed file has no usable patch, using the `OmissionReason` values Task 10A consumes. A missing patch is never treated as an unchanged file.
- ⬜ Run `uv run ruff check .`, `uv run mypy`, and `uv run pytest`.

### Task 8 - ⬜ Connector contracts and allowlisted audit logs

**Files:**
- Create: hosted migration `<timestamp>_connector_runs.sql`
- Create: `src/pr_reviewer/connectors/base.py`
- Create: `src/pr_reviewer/connectors/audit.py`
- Create: `src/pr_reviewer/connectors/github.py`
- Test: `tests/test_connector_contracts.py`
- Test: `tests/test_github_connector.py`

**Interfaces:**
- Produces: `ConnectorResult[T]` with connector, operation, outcome, typed value, error kind, status code, and latency.
- Produces: `ConnectorAudit` with trace ID, operation, external ID, byte counts, and payload hash only.
- Produces: `record_connector_run(db: Database, audit: ConnectorAudit, review_job_id: str | None) -> str`

**TDD steps:**
- ⬜ Write failing tests that reject raw headers, credential URLs, tokens, private keys, source text, and arbitrary request or response dictionaries.
- ⬜ Run `uv run pytest tests/test_connector_contracts.py -v` and confirm the secret canaries fail safely.
- ⬜ Implement typed audit fields and recursive redaction as a second defense.
- ⬜ Wrap the existing GitHub token and PR fetch calls without changing their public behavior.
- ⬜ Test timeout, GitHub error class, status code, latency, payload size, and audit event recording.
- ⬜ Store the job trace ID on every `connector_runs` row. It is the join key product-runtime Task 5A uses to merge hosted and local halves of one trace.
- ⬜ Run all backend checks.

### Task 9 - ⬜ Eval contracts, mined candidates, and checked holdout set

**Files:**
- Create: hosted migration `<timestamp>_eval_foundation.sql`
- Create: `src/pr_reviewer/evals/types.py`
- Create: `src/pr_reviewer/contracts/finding_candidate.py`
- Create: `src/pr_reviewer/evals/mine_candidates.py`
- Create: `src/pr_reviewer/evals/match_findings.py`
- Create: `src/pr_reviewer/evals/metrics.py`
- Create: `src/pr_reviewer/evals/run_eval.py`
- Create: `src/pr_reviewer/evals/fixture_reviewer.py`
- Create: `datasets/public/eval_cases.jsonl`
- Create: `docs/EVAL_DATASET.md`
- Test: `tests/test_eval_mining.py`
- Test: `tests/test_eval_matching.py`
- Test: `tests/test_eval_metrics.py`

**Interfaces:**
- Produces: `FindingCandidate` with concern, severity, category, changed file and lines, title, rationale, evidence, and confidence.
- Produces: `EvalCase` with ID, dev or holdout split, diff, expected labels, source evidence, and human auditor.
- Produces: `mine_eval_candidates(repo_path: Path, max_cases: int) -> list[EvalCandidate]`
- Produces: `match_findings(expected: list[EvalLabel], actual: list[FindingCandidate]) -> MatchResult`
- Produces: `compute_metrics(matches: list[MatchResult], reviewed_pr_count: int) -> EvalMetrics`
- Produces: `ReviewerCallable` as the injected under-test interface, so the harness never imports a model provider.
- Produces: `run_eval(config: EvalConfig, reviewer: ReviewerCallable) -> EvalReport`
- Produces: `FixtureReviewer` replaying recorded outputs for harness tests.

**TDD steps:**
- ⬜ Write failing tests that mining creates candidates only and never treats commit-message guesses as final labels.
- ⬜ Add positive and negative cases, source commit evidence, time-based split, and an explicit human audit field.
- ⬜ Write deterministic matching tests for concern, file, overlapping line range, and normalized category.
- ⬜ Add a separate `needs_human_match` result for semantic matches. Do not let an LLM judge silently set ground truth.
- ⬜ Test precision, recall, false findings per PR, selectivity, verified finding rate, latency, and cost.
- ⬜ Build the eval runner here, against an injected `ReviewerCallable`, not against a model. Phase 7 must be provable before Phase 8 exists.
- ⬜ Test the whole harness with `FixtureReviewer`: a perfect reviewer, a silent reviewer, a noisy reviewer, and a flaky reviewer scoring differently across repeats.
- ⬜ Test that `run_eval` makes no network call and imports nothing from `models/`. Add an import-boundary test.
- ⬜ Add a rule-adherence dimension: holdout cases that violate a known repository convention. Score
  three arms separately, retrieval-only, executable-check-only, and both, so the claim that one
  carrier beats the other is settled by a number instead of an opinion. This is the experiment the
  source article sets up and never runs, and it is the most publishable result in the build.
- ⬜ Keep private FoodSpector cases outside git. Commit only licensed public or synthetic cases.
- ⬜ Run all backend checks.

### Task 10 - ⬜ Model providers and immutable prompt registry

**Files:**
- Create: `src/pr_reviewer/models/provider.py`
- Create: `src/pr_reviewer/models/openai_provider.py`
- Create: `src/pr_reviewer/models/anthropic_provider.py`
- Create: `src/pr_reviewer/prompts/registry.py`
- Create: hosted migration `<timestamp>_prompt_registry_constraints.sql`
- Test: `tests/test_model_provider.py`
- Test: `tests/test_prompt_registry.py`

**Interfaces:**
- Produces: `ModelProvider.complete_json(request: ModelRequest) -> ModelResponse`
- Produces: `ModelRequest` with prompt version, schema name, quoted untrusted-input blocks, timeout, and token limit.
- Produces: `ModelResponse` with parsed JSON, output hash, provider IDs, token use, latency, and cost.

**TDD steps:**
- ⬜ Write failing tests for timeout, invalid JSON, schema mismatch, context limit, rate limit, provider error, token counts, and cost recording.
- ⬜ Write prompt-injection tests where a diff asks the model to reveal secrets, ignore policy, or post directly.
- ⬜ Implement OpenAI and Anthropic adapters behind the same typed interface.
- ⬜ Store immutable prompt versions and reject updates to an existing name and version.
- ⬜ Record detailed model calls and connector events in local state without storing API keys or unrestricted raw requests. Report aggregate tokens, cost, and latency to the control plane.
- ⬜ Run all backend checks.

### Task 10A - ⬜ Diff budgeting, context packing, and omission reporting

**Files:**
- Create: `src/pr_reviewer/contracts/review_context.py`
- Create: `src/pr_reviewer/reviewer/hunk_format.py`
- Create: `src/pr_reviewer/reviewer/diff_budget.py`
- Test: `tests/test_hunk_format.py`
- Test: `tests/test_diff_budget.py`

**Interfaces:**
- Consumes: `PullRequestSnapshot` and per-file patch completeness from Task 7.
- Produces: `ReviewContextItem` with source kind, file, line range, content, and content hash.
- Produces: `OmissionReason` of `token_budget`, `patch_omitted_by_github`, `patch_truncated_by_github`, `binary`, `generated`, `ignored_path`, or `file_size_limit`.
- Produces: `OmittedFile` with path, reason, and change size.
- Produces: `PackedDiff` with packing strategy version, ordered items, included files, omitted files, prompt tokens, and `covers_all_changed_files`.
- Produces: `render_hunks(file_patch: FilePatch) -> str` giving paired new and old hunk blocks with line numbers on new-side lines only.
- Produces: `pack_diff(snapshot, budget: ContextBudget, count_tokens: TokenCounter) -> PackedDiff`

**TDD steps:**
- ⬜ Write failing tests that a pull request under budget packs every changed file and sets `covers_all_changed_files` true.
- ⬜ Run `uv run pytest tests/test_diff_budget.py -v` and confirm the budget cases fail.
- ⬜ Write failing tests for a pull request over budget, one file larger than the whole budget, a zero-token budget, binary files, generated files, ignored paths, and renamed files.
- ⬜ Never drop a changed file silently. Every excluded file appears in `omitted_files` with a reason, and a GitHub-omitted patch keeps a different reason from a budget omission.
- ⬜ Test that packing is deterministic. The same snapshot and budget must produce the same item order and the same omission list on repeated runs, so the three eval repeats in Task 11 stay comparable.
- ⬜ Name the ordering rule, version it as `packing_strategy_version`, and store it on `PackedDiff`. Never order by dictionary or set iteration.
- ⬜ Test the hunk renderer round trip. Every rendered new-side line number must map back to a real head-file line so Task 17 can anchor a comment.
- ⬜ Test that the omission list reaches the prompt, the event spine, and the review result.
- ⬜ Set the default context budget per model in config, and test that the budget reserves an output allowance the packer cannot spend.
- ⬜ Accept an optional sensitivity score per file from Task 13A. A high-sensitivity file resists
  eviction and is dropped only after every lower-sensitivity file has gone. A dangerous file falling
  silently out of the packed diff is the worst omission this task exists to prevent. Determinism
  still holds: the score is an input to the ordering, never a source of nondeterminism.
- ⬜ Run all backend checks.

### Task 10B - ⬜ Trusted instruction sources and prompt input boundaries

**Files:**
- Create: `src/pr_reviewer/security/instruction_sources.py`
- Create: `src/pr_reviewer/security/prompt_boundaries.py`
- Test: `tests/test_instruction_sources.py`
- Test: `tests/test_prompt_boundaries.py`

**Interfaces:**
- Consumes: `RepositoryIdentity` and the repository fetcher from Task 7.
- Produces: `InstructionSource` with path, default branch name, resolved commit SHA, content hash, byte size, and truncation flag.
- Produces: `load_repository_instructions(identity, fetcher, policy) -> list[InstructionSource]`
- Produces: `wrap_untrusted(label: str, content: str) -> str` as the single approved way to place repository text in a prompt.

**TDD steps:**
- ⬜ Write failing tests that an instruction file added or edited on the pull request head never reaches the prompt as instructions.
- ⬜ Run `uv run pytest tests/test_instruction_sources.py -v` and confirm the head-branch cases fail.
- ⬜ Read instruction files only from the repository default branch at a resolved commit SHA. Never read them from the pull request head, from a base branch that is not the default branch, or from a fork.
- ⬜ Record the default branch name and resolved SHA on every `InstructionSource` and in the event spine, so a review can be replayed with the same guidance.
- ⬜ Test an allowlist of instruction file names, a maximum file count, a maximum byte size, and an explicit truncation marker.
- ⬜ Test that instruction text can only steer review focus. It cannot change routing, severity, verification, public safety, posting, or budget. Injection strings inside a default-branch instruction file must fail these tests.
- ⬜ Keep repository instructions disabled by default in v1 and enable them per repository, in line with auto-post and specialist mode.
- ⬜ Test that the diff, pull request title, body, commit messages, review comments, and retrieved chunks all reach the prompt through `wrap_untrusted`.
- ⬜ Add a canary test that fails if any prompt assembly path interpolates repository text without `wrap_untrusted`.
- ⬜ Run all backend checks.

### Task 11 - ⬜ Diff-only one-agent baseline

**Files:**
- Create: local migration `<timestamp>_finding_candidates_and_verification.sql`
- Modify: `src/pr_reviewer/contracts/finding_candidate.py`
- Modify: `src/pr_reviewer/contracts/review_context.py`
- Create: `src/pr_reviewer/reviewer/review_pull_request.py`
- Modify: `src/pr_reviewer/evals/run_eval.py`
- Test: `tests/test_review_pull_request.py`
- Test: `tests/test_eval_runner.py`

**Interfaces:**
- Consumes: `FindingCandidate` from Task 9.
- Consumes: `PackedDiff` from Task 10A and `wrap_untrusted` from Task 10B.
- Produces: `ReviewOutcome` with candidates, packing strategy version, and coverage.
- Produces: `review_pull_request(snapshot, packed: PackedDiff, context: list[ReviewContextItem], model) -> ReviewOutcome`
- Consumes: `run_eval` and `ReviewerCallable` from Task 9. This task supplies the real reviewer, not the harness.

**TDD steps:**
- ⬜ Write failing tests proving the model cannot set IDs, job IDs, verification, public safety, status, or posting fields.
- ⬜ Test malformed findings, lines outside the changed diff, empty evidence, duplicate candidates, and overlong output.
- ⬜ Implement the baseline with an empty retrieval context and one model call over the Task 10A packed diff.
- ⬜ Test that the prompt states which changed files were omitted, and that a partial-coverage review is never reported as complete.
- ⬜ Run at least three repeats per holdout case and store each run separately.
- ⬜ Save the first diff-only report with dataset, prompt, model, packing strategy version, run count, coverage, precision, recall, false findings per PR, latency, and cost.
- ⬜ Run all backend checks.

### Task 12 - ⬜ Code chunks, embedding generations, and pgvector storage

**Files:**
- Create: local pgvector migration `<timestamp>_retrieval_generations.sql`
- Create: `src/pr_reviewer/retrieval/chunk_code.py`
- Create: `src/pr_reviewer/retrieval/embed.py`
- Create: `src/pr_reviewer/retrieval/index_repository.py`
- Test: `tests/test_chunk_code.py`
- Test: `tests/test_index_repository.py`

**Interfaces:**
- Produces: embedding provider model name, dimensions, and batched embed method.
- Produces: `IndexGeneration` with repository ID, commit SHA, model, dimensions, and state.
- Produces: stable `CodeChunk` records with language, line range, content hash, and generation ID.

**TDD steps:**
- ⬜ Write failing tests for stable chunks, overlap, line ranges, renames, binary files, generated files, ignored paths, symlinks, and content hashes.
- ⬜ Add a schema and startup check for the v1 1536-dimension embedding contract.
- ⬜ Store model name and generation. Never mix embeddings from different models or dimensions.
- ⬜ Index the base commit in a new generation, then atomically mark it active.
- ⬜ Add full-text `tsvector` data and a GIN index. Use exact vector scan first and measure before adding an approximate vector index.
- ⬜ Run all backend checks.

### Task 13 - ⬜ Hybrid retrieval and measured comparison

**Files:**
- Create: `src/pr_reviewer/retrieval/rrf.py`
- Create: `src/pr_reviewer/retrieval/hybrid_search.py`
- Modify: `src/pr_reviewer/evals/run_eval.py`
- Test: `tests/test_rrf.py`
- Test: `tests/test_hybrid_search.py`

**Interfaces:**
- Produces: `reciprocal_rank_fusion(rankings: list[list[str]], k: int = 60) -> list[str]`
- Produces: `retrieve_context(query: RetrievalQuery, limit: int = 8) -> list[ReviewContextItem]`

**TDD steps:**
- ⬜ Write failing tests for exact identifiers, semantic matches, repository isolation, active generation, stale chunks, rank ties, and context token limits.
- ⬜ Implement vector and full-text queries scoped by installation, repository, and commit.
- ⬜ Merge ranks with reciprocal rank fusion and store chosen chunk IDs in the event spine.
- ⬜ Spend retrieved chunks from the same Task 10A context budget as the diff, and never let retrieval push a changed file out of the packed diff without recording the omission.
- ⬜ Pass every retrieved chunk through `wrap_untrusted`. Add a retrieval injection test where an indexed README or comment tells the model to ignore policy or post directly.
- ⬜ Run the same holdout cases with no retrieval and hybrid retrieval.
- ⬜ Keep retrieval enabled only if the report improves useful results without breaking the cost limit.
- ⬜ Run all backend checks.

### Task 13A - ⬜ Repository profile and code graph as measured context sources

**Files:**
- Create: `src/pr_reviewer/retrieval/repo_profile.py`
- Create: `src/pr_reviewer/retrieval/code_graph.py` (reads graphify `graph.json`, does not parse source itself)
- Create: `src/pr_reviewer/retrieval/sensitivity.py`
- Create: local pgvector migration `<timestamp>_repo_profile_and_graph.sql`
- Modify: `src/pr_reviewer/evals/run_eval.py`
- Modify: `src/pr_reviewer/security/instruction_sources.py`
- Test: `tests/test_repo_profile.py`
- Test: `tests/test_code_graph.py`

**Interfaces:**
- Produces: `RepoProfile` with repository ID, commit SHA, generating model, prompt version, generated-at
  time, content hash, and a list of `ProfileClaim`.
- Produces: `ProfileClaim` with kind, text, supporting file paths, and `status` of `candidate` or
  `promoted`. Never `verified`.
- Produces: `generate_repo_profile(repo_path, model, budget) -> RepoProfile`
- Produces: `CodeGraph` with import edges, call edges, and export ownership, plus
  `blast_radius(symbol, depth) -> list[str]`. Built from graphify's `graph.json`, not from a
  hand-written parser.
- Produces: `SensitivityScore` with path, fix density, caller count, structural flags, and the
  evidence behind each, so the score can always be explained.
- Produces: `score_sensitivity(repo_path, graph) -> dict[str, SensitivityScore]`

**TDD steps:**
- ⬜ Write failing tests that a profile claim can never enter a prompt as policy. A profile may steer
  review focus. It may not assert an invariant, change routing, severity, verification, or posting.
- ⬜ Run `uv run pytest tests/test_repo_profile.py -v` and confirm the policy cases fail.
- ⬜ A generated profile is model output, so it is inferred, not asserted. Keep it separate from the
  Task 10B instruction file, which is authoritative because a human wrote it. Never merge the two
  into one prompt block with equal weight.
- ⬜ Emit invariant-shaped claims as `candidate` only. A human promotes a candidate into the
  default-branch instruction file, exactly as a mined eval candidate is audited before it becomes
  ground truth in Task 9. There is no automatic promotion path.
- ✅ Use **graphify** as the code-graph extractor rather than writing a tree-sitter pass.
  Local, LLM-free, incremental (`graphify update <path>`), with a `watch` mode, so freshness is a
  cron job rather than an argument. Measured on this repo: 409 nodes, 1237 edges, function level,
  with `calls`, `contains`, `imports_from`, `imports`, `references`, `uses` and `inherits` relations.
  Covers Python and TypeScript. Installed at `/opt/graphify-venv`.
- ⬜ Read `graphify-out/graph.json` directly and build our own **directed** adjacency. The file is
  `directed: false` and `graphify path` traverses undirected, which collapses "what calls X" into
  "what X touches". Direction is recoverable because every link keeps `source` and `target`.
  Do not use the CLI's traversal for blast radius.
- ⬜ Every graphify link carries `confidence`, either `EXTRACTED` or `INFERRED` (measured here: 1061
  and 176). Count only `EXTRACTED` edges toward `SensitivityScore`, or the score silently inherits
  the extractor's guesses and stops being a parsed fact.
- ⬜ Install `tree_sitter_sql` in the graphify environment. It is missing, so `.sql` files contribute
  nothing to the graph, and a reviewer whose job includes migrations would be blind to its own schema.
- ⚠️ Never run `graphify install`. It wires PreToolUse hooks onto Read, Glob, Bash and Grep, spawning
  Python on every tool call, and appends to the global `CLAUDE.md`. Use the CLI directly.
- ⚠️ `graphify update` writes an untracked `graphify-out/` into the repository root. Add it to
  `.gitignore` before the first run, or every review dirties the working tree it is reviewing.
- ⬜ Stamp every profile with repository ID, commit SHA, model, and prompt version. Test that a
  profile older than its policy window is refused rather than silently used.
- ⬜ Store profiles and graphs in local state only. A profile summarises private source, so it never
  reaches hosted Neon.
- ⬜ Build the code graph with deterministic parsing, not a model. It answers "who calls this", which
  is a tool question with a correct answer.
- ⬜ Add `blast_radius` tests for direct callers, transitive callers at depth, cycles, re-exports,
  dynamic imports that cannot be resolved, and a symbol that does not exist.
- ⬜ Compute **sensitivity** per file from three deterministic sources: the ratio of `fix` and
  `revert` commits touching it, its caller count from the graph, and structural markers (auth,
  tokens, crypto, migrations, deletion, money) detected by path and imported symbol.
- ⚠️ This is the closest thing to a senior engineer's memory that a repository can supply. They know
  which code is dangerous because they were there when it broke. The agent cannot be there, but the
  commit that fixed it is still in the log. Verified on FoodSpector: the highest fix-density module
  is one of the three submit paths its `CLAUDE.md` warns about, and nobody had to write that down.
- ⬜ Test fix density on a synthetic history: a file with many fixes outranks a file with many
  commits, renames do not reset the count, and merge commits are not double counted.
- ⬜ Sensitivity is **routing input, not prompt text**. Prompt text competes for attention and can
  lose. Feed the score to the budget packer and the gate, and put only the **facts** in the prompt
  ("this file has 12 prior fixes and 40 callers"), never an adjective like "be careful".
- ⬜ Add profile-only, graph-only, and profile-plus-graph arms to the Task 13 comparison. Keep either
  source enabled only if it improves the stated quality gate without breaking the cost gate.
- ⬜ Test that profile generation cost is bounded and charged against the repository budget, not the
  per-PR budget.
- ⬜ Run all backend checks.

### Task 14 - ⬜ Docker-only verification and static checks

**Files:**
- Create: `src/pr_reviewer/verification/docker_sandbox.py`
- Create: `src/pr_reviewer/verification/static_checks.py`
- Create: `docker/sandbox/Dockerfile`
- Test: `tests/test_docker_sandbox.py`
- Test: `tests/test_static_checks.py`

**Interfaces:**
- Produces: `VerificationResult` with passed, failed, inconclusive, or not-applicable status.
- Produces: `verify_finding(candidate, snapshot, policy) -> VerificationResult`

**TDD steps:**
- ⬜ Write failing tests that the sandbox uses no network, no host secrets, no Docker socket, a non-root user, read-only root, dropped capabilities, and a temporary work directory.
- ⬜ Test CPU, memory, process, disk, output, and wall-time limits.
- ⬜ Test cleanup after success, failure, timeout, worker crash, and malicious child processes.
- ⬜ Pin the sandbox image by digest and allow only repository-configured command IDs. Never run a model-provided shell string.
- ⬜ Add static checks for file existence, changed-line membership, current head SHA, and evidence text.
- ⬜ If Docker is missing, return `inconclusive` and route to a person. Never fall back to host execution.
- ⬜ Run all backend checks.

### Task 15 - ⬜ Deterministic gate, human approval, and classified notification channels

**Files:**
- Create: `src/pr_reviewer/gates/route_finding.py`
- Create: `src/pr_reviewer/hitl/record_human_decision.py`
- Create: `src/pr_reviewer/notifications/channel.py`
- Create: `src/pr_reviewer/notifications/policy.py`
- Create: `src/pr_reviewer/connectors/slack.py`
- Create: `src/pr_reviewer/connectors/telegram.py`
- Create: `src/pr_reviewer/connectors/discord.py`
- Test: `tests/test_route_finding.py`
- Test: `tests/test_human_decisions.py`
- Test: `tests/test_notification_policy.py`
- Test: `tests/test_notification_connectors.py`

**Interfaces:**
- Produces: system-owned `Finding` from a candidate, verification result, snapshot, and policy.
- Produces: `RouteDecision` with discard, human queue, private alert, or public post.
- Produces: append-only `HumanDecision` with actor, action, note, original hash, and edited hash.
- Produces: `NotificationChannel` with kind, destination reference, and `confidentiality` of
  `restricted` or `ordinary`.
- Produces: `Notification` with event kind, severity, redaction level, body, and idempotency key.
- Produces: `select_channels(notification, policy) -> list[NotificationChannel]`

**TDD steps:**
- ⬜ Test that the model cannot bypass routing through severity, confidence, rationale, or injected text.
- ⬜ Test that unsafe security findings always route privately.
- ⬜ Test that unverified and inconclusive findings queue for a person.
- ⬜ Test that a finding on a high-sensitivity file routes to a human even when verified and
  public-safe. Sensitivity spends human attention where a senior reviewer would have spent theirs.
- ⬜ Test that public posting stays off by default and requires both release gates.
- ⬜ Implement Slack, Telegram, and Discord behind one channel interface. Each gets timeouts, safe
  templates, idempotency, retry, and allowlisted audit data. The plumbing is nearly identical; the
  policy is the part that matters.
- ⬜ Separate the two jobs notifications do. A private security alert is a **security control**.
  A "your PR was reviewed" ping is a **convenience**. Test that they cannot share a channel unless
  that channel is marked `restricted`.
- ⬜ Test that restricted content is refused on an `ordinary` channel rather than downgraded. A
  Telegram group is trivial to add a member to, so the channel's confidentiality is a declared
  property the operator sets, never inferred from the transport.
- ⬜ Test notification previews. A lock-screen push reading "SQL injection in auth.ts line 42" is a
  disclosure. Restricted notifications carry a title with no finding detail and a body behind the
  app, and the test asserts on the title, not only the body.
- ⬜ Test delivery failure, partial fan-out to several channels, duplicate suppression by
  idempotency key, and a revoked webhook.
- ⬜ Keep human feedback append-only. Never update prompts online from one decision.
- ⬜ Run all backend checks.

### Task 16 - ⬜ Workflow interface and simple Python engine

**Files:**
- Create: hosted migration `<timestamp>_workflow_runs.sql`
- Create: `src/pr_reviewer/workflow/engine.py`
- Create: `src/pr_reviewer/workflow/simple_engine.py`
- Modify: `src/pr_reviewer/worker/main.py`
- Test: `tests/test_workflow_engine.py`
- Test: `tests/test_review_job_pipeline.py`

**Interfaces:**
- Produces: `WorkflowEngine.run(workflow_id, input) -> WorkflowResult`
- Produces: `WorkflowEngine.resume(workflow_id) -> WorkflowResult`
- Produces: `WorkflowEngine.get_state(workflow_id) -> WorkflowState`

**TDD steps:**
- ⬜ Test fetch, baseline review, retrieval, verification, routing, and storage as idempotent workflow steps.
- ⬜ Test resume after a crash at each step without repeating a completed external effect.
- ⬜ Keep `review_jobs` as queue state. Store workflow step state separately to avoid two competing job states.
- ⬜ Add node deadlines, cancellation on superseded head SHA, and event rows for every transition.
- ⬜ Wire the local runner daemon to the simple engine without importing LangGraph.
- ⬜ Run all backend checks.

### Task 17 - ⬜ Stale-safe and idempotent GitHub review posting

**Files:**
- Create: `src/pr_reviewer/github/post_review.py`
- Modify: `src/pr_reviewer/connectors/github.py`
- Modify: `src/pr_reviewer/github/lifecycle.py`
- Test: `tests/test_post_review.py`

**Interfaces:**
- Produces: `post_review(ref, head_sha, findings, idempotency_key) -> PostedReview`

**TDD steps:**
- ⬜ Test current-head verification immediately before posting.
- ⬜ Test GitHub diff side and line anchors, renamed files, deleted lines, outdated lines, and summary-only fallback.
- ⬜ Test one posted review per repository, PR, head SHA, and policy version.
- ⬜ Test that private security details and rejected findings never enter the public body.
- ⬜ Record GitHub review ID, comment IDs, response status, and event rows.
- ⬜ Run all backend checks.

### Task 18 - ⬜ Reliability, budgets, retention, and fault tests

**Files:**
- Create: hosted migration `<timestamp>_reliability_and_budget.sql`
- Create: `src/pr_reviewer/reliability/retry.py`
- Create: `src/pr_reviewer/reliability/circuit.py`
- Create: `src/pr_reviewer/reliability/budget.py`
- Create: `src/pr_reviewer/security/retention.py`
- Create: `tests/test_fault_injection.py`
- Create: `tests/test_budget.py`
- Create: `tests/test_retention.py`

**Interfaces:**
- Produces: capped exponential retry with jitter and `Retry-After` support.
- Produces: durable connector circuit state and half-open probes.
- Produces: atomic per-job budget reservation in the local runner and aggregate repository budget enforcement in the control plane.
- Produces: retention jobs for expired snapshots, code generations, raw traces, and connector metadata.

**TDD steps:**
- ⬜ Test GitHub timeout, provider timeout, rate limit, Neon interruption, worker crash, lease expiry, duplicate delivery, and duplicate post.
- ⬜ Test dead-job state, manual requeue, queue depth, claim latency, and worker capacity metrics.
- ⬜ Test concurrent budget reservations so two workers cannot exceed one repository budget.
- ⬜ Add health, readiness, queue, cost, rejection-rate, and circuit-state endpoints.
- ⬜ Test repository uninstall and retention deletion without removing shared installation data.
- ⬜ Run a Postgres queue benchmark at the expected worker count and record the result before considering Redis.
- ⬜ Run all backend checks.

### Task 19 - ⬜ Specialist-agent experiment and optional LangGraph adapter

**Files:**
- Create: `src/pr_reviewer/workflow/langgraph_engine.py`
- Create: `src/pr_reviewer/reviewer/specialists.py`
- Create: `src/pr_reviewer/reviewer/aggregate_findings.py`
- Test: `tests/test_specialists.py`
- Test: `tests/test_aggregate_findings.py`
- Test: `tests/test_langgraph_engine.py`

**Interfaces:**
- Produces: concern-specific security, correctness, test, and documentation reviewers.
- Produces: deterministic merge by repository, head SHA, file, overlapping lines, and normalized category.
- Produces: a LangGraph adapter that passes the same `WorkflowEngine` tests as the simple engine.

**TDD steps:**
- ⬜ Test partial specialist timeout, duplicate findings, conflicting severity, unsafe security text, and missing agents.
- ⬜ Run the same holdout set with the one-agent and specialist paths.
- ⬜ Measure precision, high-value recall, false findings per PR, latency, total cost, and useful findings per dollar.
- ⬜ Keep the specialist and LangGraph path disabled unless all specialist release gates pass.
- ⬜ Record a rejected experiment honestly if it does not pass.
- ⬜ Run all backend checks.

### Task 20 - ⬜ Eval regression gates, feedback controls, and drift checks

**Files:**
- Modify: `src/pr_reviewer/evals/run_eval.py`
- Create: `src/pr_reviewer/evals/regression_gate.py`
- Create: `src/pr_reviewer/evals/feedback_candidates.py`
- Create: `docs/EVALS.md`
- Test: `tests/test_eval_regression_gate.py`
- Test: `tests/test_feedback_candidates.py`

**Interfaces:**
- Produces: `compare_eval_reports(candidate, baseline, thresholds) -> GateResult`
- Produces: feedback candidates that need repeated evidence and human audit before entering an eval set.

**TDD steps:**
- ⬜ Test regression blocks for precision, false findings per PR, high-value recall, cost, and latency.
- ⬜ Test that one dispute cannot change prompts, policies, labels, or routing.
- ⬜ Require repeated evidence and human audit before feedback becomes an eval candidate.
- ⬜ Report confidence calibration with Brier score and calibration buckets, but keep confidence out of routing.
- ⬜ Add drift alerts for rejection rate, dispute rate, no-finding rate, cost, latency, and retrieval misses.
- ⬜ Publish exact eval commands and machine-readable reports.
- ⬜ Run all backend checks.

### Task 21 - ⬜ Authenticated local dashboard API

**Files:**
- Create: `src/pr_reviewer/web/local_auth.py`
- Create: `src/pr_reviewer/web/dashboard_api.py`
- Create: `src/pr_reviewer/web/schemas.py`
- Test: `tests/test_dashboard_auth.py`
- Test: `tests/test_dashboard_api.py`

**Interfaces:**
- Produces: loopback-only jobs, findings, events, costs, evals, approvals, health, and connector-status endpoints backed by local state.

**TDD steps:**
- ⬜ Test non-loopback denial, unauthenticated denial, runner scope, repository scope, write CSRF protection, cookie flags, and CORS rules.
- ⬜ Keep GitHub webhook routes on the hosted control plane. The installed dashboard service exposes no webhook route.
- ⬜ Test pagination, stable ordering, redacted events, approval races, and not-found behavior.
- ⬜ Serve the merged hosted and local trace from product-runtime Task 5A. Do not build a second, local-only trace view that silently omits the hosted half.
- ⬜ Use the paired runner identity for account data and a separate random local session for localhost access.
- ⬜ Run all backend checks.

### Task 22 - ⬜ Bun and TypeScript review dashboard

**Files:**
- Create: `apps/web/package.json`
- Create: `apps/web/bun.lock`
- Create: `apps/web/src/app/*`
- Create: `apps/web/src/components/*`
- Create: `apps/web/tests/dashboard.spec.ts`

**Interfaces:**
- Consumes: Task 21 API.
- Produces: approval queue, finding details, retrieved context, workflow trace, connector status, cost, and eval views.

**TDD steps:**
- ⬜ Write failing Playwright tests for login, repository scope, approval, rejection, private security display, trace, costs, and eval comparison.
- ⬜ Build a work-focused dashboard with no public security text in notifications or page titles.
- ⬜ Add loading, empty, partial-failure, stale-data, and permission-denied states.
- ⬜ Test desktop and mobile layouts with screenshots.
- ⬜ Run `cd apps/web && bun test` and `cd apps/web && bun run build`.

### Task 23 - ⬜ CI, release containers, and supply-chain checks

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `.github/workflows/release.yml`
- Create: `Dockerfile`
- Create: `docker-compose.ci.yml`
- Create: `compose.release.yml`
- Test: `tests/test_release_config.py`

**TDD steps:**
- ⬜ Write failing release-config tests for root containers, mutable image tags, missing health checks, missing checksums, and secret-bearing build arguments.
- ⬜ Run ruff, mypy, pytest, migration-from-empty, migration-upgrade, Bun tests, frontend build, and Playwright in CI.
- ⬜ Add dependency lock checks, secret scanning, container scanning, and generated-file checks.
- ⬜ Add a migration filename check for every set: unique names, a valid `0000_`, `000N_`, or timestamp prefix, deterministic sort order, and no rename of an already-applied file.
- ⬜ Build pinned API, worker, UI, and sandbox images as non-root users.
- ⬜ Generate checksums and a software bill of materials for versioned release assets.
- ⬜ Test startup, health checks, graceful stop, and rollback with the prior release.
- ⬜ Run all project checks locally before enabling release publishing.

### Task 24 - ⬜ FoodSpector deployment and shadow rollout

**Files:**
- Create: `docs/DEPLOY_FOODSPECTOR.md`
- Create: `docs/RUNBOOK.md`
- Create: `config/food-spector.policy.example.toml`
- Test: `tests/test_foodspector_policy.py`

**TDD steps:**
- ⬜ Write failing policy tests for auto-post enabled before release gates, repositories outside the allowlist, missing kill switch, and excessive per-PR budget.
- ⬜ Deploy the shared control plane behind a stable HTTPS webhook URL and pair the FoodSpector local runner with auto-post disabled.
- ⬜ Limit the GitHub App to FoodSpector repositories and least-privilege permissions.
- ⬜ Run at least 30 non-draft PRs over at least 14 days in shadow mode.
- ⬜ Record human labels, false findings, missed findings, useful findings, cost, latency, and queue delay.
- ⬜ Test kill switch, model-provider disable, queue pause, rollback, backup restore, and repository uninstall.
- ⬜ Approve auto-post only if the measured release gates pass. Otherwise keep human approval.

### Task 25 - ⬜ Versioned public installer and setup wizard

**Files:**
- Create: `scripts/install.sh`
- Create: `scripts/uninstall.sh`
- Create: `src/pr_reviewer/cli/main.py`
- Create: `src/pr_reviewer/cli/doctor.py`
- Create: `docs/INSTALL.md`
- Test: `tests/test_installer.py`
- Test: `tests/test_doctor.py`

**Interfaces:**
- Produces: `pr-reviewer setup`, `doctor`, `start`, `stop`, `status`, and `uninstall`.
- Produces: a versioned release command that downloads and verifies the application bundle checksum.

**TDD steps:**
- ⬜ Test install in a clean Linux container from a versioned GitHub release asset.
- ⬜ Pair the runner with the hosted control plane through a one-time browser or device code.
- ⬜ Read model API keys and optional Slack secrets with hidden input. Prefer the operating-system secret store and use `~/.config/pr-reviewer` mode `0600` only as a fallback.
- ⬜ Never place secrets in command arguments, shell history, logs, URLs, checksums, or browser query strings.
- ⬜ Do not ask the user for a Neon URL, GitHub App private key, webhook secret, personal access token, or public webhook URL.
- ⬜ Check control-plane reachability, runner pairing, model keys, port use, disk space, and Docker sandbox support.
- ⬜ Offer full mode when Docker checks pass. Offer analysis-only mode when Docker is absent and show its limits before saving the choice.
- ⬜ Start the local runner daemon and UI, then open localhost only in an interactive desktop session.
- ⬜ Install the runner as a user service so reviews continue after the onboarding terminal closes.
- ⬜ Make uninstall preserve data by default. Require a separate confirmed flag to delete data and secrets.
- ⬜ Run all project checks.

### Task 26 - ⬜ Hiring README, architecture, security, and measured proof

**Files:**
- Modify: `README.md`
- Create: `docs/ARCHITECTURE.md`
- Create: `docs/SECURITY.md`
- Create: `docs/DEMO.md`
- Create: `docs/assets/dashboard-screenshot.png`

**TDD steps:**
- ⬜ Publish real diff-only, retrieval, verification, and specialist reports, including failed experiments.
- ⬜ Show precision, recall, false findings per PR, selectivity, verified finding rate, latency, and cost per PR.
- ⬜ Document the event spine, Postgres queue, trust boundaries, Docker sandbox, human gate, prompt versions, and connector audit model.
- ⬜ Record FoodSpector shadow-run totals without publishing private code or security details.
- ⬜ Run the installer on a clean machine and record redacted output.
- ⬜ Capture dashboard screenshots and a full signed-webhook-to-human-decision demo.
- ⬜ Document known limits, data retention, rollback, and why Redis, TigerData, and specialist mode are disabled or enabled.
- ⬜ Run secret scans and all project checks.

## Done Means - ⬜

- ⬜ Every Phase 0 through Phase 20 topic has an approved learning record and reproduced proof gate.
- ⬜ Every master and product-runtime task maps back to at least one phase.
- ⬜ A signed GitHub webhook creates one installation-scoped job and returns quickly.
- ⬜ A new head SHA supersedes stale work and cannot receive an old review.
- ⬜ Omitted GitHub patches use a bounded fallback or produce a clear incomplete result.
- ⬜ A pull request too large for the context budget packs deterministically, reports every omitted file with a reason, and is never reported as full coverage.
- ⬜ Repository instruction files come only from the default branch at a recorded SHA, and a pull request cannot change the guidance used to review it.
- ⬜ The one-agent baseline has a repeatable public eval report.
- ⬜ Retrieval is enabled only after a measured comparison.
- ⬜ Model output cannot set verification, public safety, status, or posting fields.
- ⬜ Untrusted commands run only inside the locked-down Docker sandbox.
- ⬜ Human approval controls public posting until both release gates pass.
- ⬜ Security findings route privately, and only to channels declared restricted.
- ⬜ Notifications reach Slack, Telegram, or Discord without a restricted finding ever landing on an
  ordinary channel or in a push preview.
- ⬜ A repository profile and a code graph are each enabled only after the measured comparison, and
  neither can assert an invariant.
- ⬜ The eval harness runs and is proved on recorded fixtures before any model provider exists.
- ⬜ The hosted schema physically cannot store private review data.
- ⬜ Every external call and workflow step is traceable without exposing secrets or private code, across both the hosted and local stores.
- ⬜ Costs are limited before model calls and reported per PR and repository.
- ⬜ Queue, provider, GitHub, database, and worker failures have tested recovery paths.
- ⬜ The authenticated dashboard shows queue, findings, traces, approvals, costs, and evals.
- ⬜ FoodSpector completes the shadow run with a recorded decision on auto-post.
- ⬜ A fresh user can install a versioned release, enter secrets safely, and open the UI.
- ⬜ The installed runner receives real jobs through outbound HTTPS without a tunnel or public local port.
- ⬜ Full mode requires Docker. Analysis-only mode never claims executable verification.
- ⬜ CI checks backend, database changes, frontend, security, release images, and installer behavior.
- ⬜ README claims are backed by commands, reports, screenshots, and measured results.

## Traps - ⚠️

- ⚠️ The source roadmap has 21 entries numbered Phase 0 through Phase 20.
- ⚠️ Do not use the source list as a literal implementation dependency order.
- ⚠️ Do not mark a phase complete because one related task passed.
- ⚠️ Never edit an applied migration to make a new test pass, and never rename one. `schema_migrations` is keyed by filename.
- ⚠️ Two plans write into the same migration directories. A hardcoded next number in a plan is a collision waiting for the first reorder.
- ⚠️ A GitHub signature proves GitHub sent the payload. It does not replace installation and repository authorization.
- ⚠️ GitHub can omit or truncate patches. An empty patch is not proof that a file has no changes.
- ⚠️ Repository text can contain prompt injection. Treat it as quoted data, never as policy.
- ⚠️ Reading `AGENTS.md`, `CLAUDE.md`, or a policy file from the pull request head lets a pull request write its own review instructions.
- ⚠️ A token budget that silently drops a changed file looks exactly like a clean review of that file.
- ⚠️ Non-deterministic packing breaks repeated eval runs before it breaks anything else.
- ⚠️ A failed reproduction does not prove a finding is false. It may be inconclusive.
- ⚠️ A read-only checkout is not a sandbox. Untrusted code can still read secrets and use the network.
- ⚠️ Do not gate on self-reported confidence.
- ⚠️ Do not post exploit details to public PRs.
- ⚠️ A Telegram or Discord group is not a private channel. Membership changes without you noticing.
- ⚠️ A push notification preview is a disclosure. It renders on a locked screen.
- ⚠️ A generated profile that states an invariant wrongly poisons every later review, and no single
  review will look wrong enough to catch it.
- ⚠️ Do not learn directly from one developer dispute.
- ⚠️ Do not build specialist agents before the baseline and eval runner exist.
- ⚠️ An agentic exploration loop is not a free upgrade. It costs the reproducibility that the whole eval
  story depends on, which is the one thing here the reference implementations do not have.
- ⚠️ An eval harness that can only run by calling a real model cannot gate the model. Build it against an injected reviewer.
- ⚠️ Hosted tables created by migration `0001` still contradict the data boundary until product-runtime Task 1A retires them.
- ⚠️ Do not add Redis, Timescale, or pgvectorscale without measured need.
- ⚠️ Do not expose dashboard endpoints without auth because the webhook route is public.
- ⚠️ Do not pipe a mutable `main` script into a shell.
- ⚠️ Do not claim localhost can receive GitHub webhooks without a public HTTPS path.
- ⚠️ Do not give installed clients Neon credentials, GitHub App secrets, or reusable installation tokens.
- ⚠️ Do not silently call analysis-only output verified when Docker is missing.

## Open Decisions - ❓

- ❓ Which real FoodSpector PR will be used for the Phase 0 walkthrough?
- ❓ Which host and public HTTPS domain will run the shared control plane?
- ❓ Which licensed public repositories will supply the publishable holdout cases?
- ❓ Should the first public release use GitHub user login only, or also support a generated local admin session?
