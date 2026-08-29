# AI PR Reviewer Phase Specs

| Mark | Means |
|---|---|
| ⬜ | Not done yet. I tick it when it lands |
| ✅ | Done, or in scope and agreed |
| ❌ | Deliberately not doing this |
| ❓ | Open decision, waiting on me |
| ⚠️ | Known trap. Read before writing the code |

**Purpose - ✅:** This file is the learning layer. The plan files say *what to build*. This says *what the idea is, what you must decide, and what you should be able to explain afterwards*. Read a phase here first, then open the task in the plan file.

**Master Plan:** `docs/superpowers/plans/2026-08-25-ai-pr-reviewer.md`
**Product Runtime Plan:** `docs/superpowers/plans/2026-08-27-hosted-control-plane-local-runner.md`
**Phase Roadmap:** `docs/superpowers/plans/2026-08-27-ai-engineering-phase-roadmap.md`
**Spec:** `docs/specs/2026-08-25-ai-pr-reviewer-system-spec.md`

## How to use this with Cursor without going dumb - ✅

The risk is real. A spec detailed enough for Cursor to one-shot is a spec that teaches you nothing, because you end up reviewing finished code instead of making decisions. These six moves put you back in the loop. They cost maybe 20 extra minutes per task and they are the whole difference.

1. ✅ **Read the Concept, then close the file.** Answer the phase's "Answer these" questions out loud or in a scratch file, from memory. Whatever you cannot answer is what you are about to build blind. Go back and read that part again.
2. ✅ **Make the "Decide before you code" calls yourself.** Never paste those into Cursor as a question. Write your answer as a one-line note in the task's brief file with a reason. If you genuinely cannot decide, that is a ❓ for the bottom of this file, not a prompt for the model.
3. ✅ **Write the failing test yourself, or predict it.** Best case you write it. Second best: before Cursor writes it, write down what it should assert and what error message a wrong implementation would produce. Then compare.
4. ✅ **Only let Cursor implement once the test is red and you can say why it is red.** "It fails because the function does not exist" is not an answer. "It fails because nothing yet maps an omitted file to a reason, so `omitted_files` comes back empty" is.
5. ✅ **Make Cursor quiz you after it is green.** Literally: "ask me five questions about why this code is the way it is, one at a time, and do not accept a vague answer." Answer without scrolling up.
6. ✅ **Never accept a diff you cannot explain line by line.** If a chunk is opaque, ask for the explanation, then delete that chunk and rewrite it yourself. Retyping a thing you just understood is how it sticks.

⚠️ The failure mode is not Cursor writing bad code. It is Cursor writing good code you cannot defend six weeks later when it breaks.

## How to read a phase - ✅

- **Concept** is the idea itself, independent of this project. This is the part worth learning.
- **Why here** explains the dependency order, which differs deliberately from the source article.
- **Decide before you code** are calls that are yours, and Cursor must not make them. Decide them as you enter the
  phase. Only the ones you genuinely cannot settle become ❓ entries in Open Decisions at the bottom.
- **Build** points at the tasks in the plan files. It does not repeat them.
- **Proof gate** is the reproducible evidence that closes the phase.
- **Answer these** is retrieval practice. If you cannot answer, you have not learned it yet.
- **Traps** are the mistakes that look correct while you are making them.

## Current position - ⬜

- ✅ Master Tasks 1 through 6 are implemented and tested.
- ⬜ Phase 0 is active. No phase has a written gate yet.
- ⚠️ Tasks being done is not phases being done. Six shipped tasks are evidence for parts of Phases 1 through 6, and prove none of them.

---

## Phase 0 - ⬜ Cognitive Design

**Concept.** Before you decide what software to build, describe what a person actually does today. Not the documented process, the real one, including the micro-decisions they make without noticing. Then, for each step, decide what kind of component it is: a trigger, a deterministic tool call, a language-model judgement, or a human checkpoint. Most bad agent systems come from skipping this and letting the model do steps that were never judgement calls. The output of this phase is a map, not code.

The four component types matter. A trigger is an event you react to. A tool is anything with a correct answer you can compute (does this file exist, does this line number resolve). An LLM step is where natural language or fuzzy judgement is genuinely required. A human checkpoint is where the consequence of being wrong is high and the action is hard to reverse. Sorting your steps into these four buckets is most of the design.

**Why here.** Everything downstream is an answer to a question this phase asks. If you cannot say what a useful finding is, you cannot write an eval for it, and if you cannot write an eval you cannot tell whether any later phase helped.

**Decide before you code.**
- What counts as a **useful finding**? Write the definition in one sentence. A reviewer would have said this, and would have wanted to be told.
- Which review steps are **mechanical** (a tool can decide) versus **judgement** (only a model or a person can)?
- What is the **autonomy level** at launch, chosen from consequence of error, reversibility, and how mature the system is? Not from what feels impressive.
- What is the **selectivity policy**: how many findings per PR is too many, and what do you do when the model wants to say more?

**Build.** No product code. The output is the system spec's goals, non-goals, Finding contract, invariants, and autonomy policy, plus a written workflow map and a failure matrix.

**Proof gate.** Take one real FoodSpector PR. Walk it through the human map end to end. Every step the system will take must trace back to a human need or a named failure mode. If a step traces to neither, delete it from the design.

**Answer these.**
1. Name a review step that feels like it needs an LLM but is actually a tool call.
2. Why does maximising the number of comments make a review bot worse, not better?
3. What is the difference between "the model was wrong" and "the finding was not useful"?
4. Give one failure mode where the system is confidently wrong and no test would catch it.

**Traps.**
- ⚠️ Writing the map from how you imagine review works, rather than watching a real one.
- ⚠️ Choosing autonomy by ambition. Autonomy is earned with evidence, and this phase has none yet.

---

## Phase 1 - ⬜ System Architecture

**Concept.** Turn the map into components with hard edges. For each one, name its trigger, its input, its output, its owner, what it stores, its timeout, its retry rule, and its fallback. The discipline that matters most here is the **trust boundary**: a line across which data changes from trusted to untrusted, or a secret must not cross. Draw those lines before you write code, because retrofitting a boundary into a running system is the hardest refactor there is. You already have proof of that, since migration `0001` is now on the wrong side of one.

The second idea is the **seam**. Where you might swap an implementation later (workflow engine, model provider, storage), put an interface with the smallest possible surface and code against it. One implementation behind an interface is normally over-engineering. It is justified exactly when you have a named, likely swap.

**Why here.** Every later phase either respects these boundaries or quietly violates them. Cheap to draw now, expensive to discover later.

**Decide before you code.**
- Where exactly does **untrusted** begin? Name every input that a PR author can influence.
- Which secrets exist, who holds each one, and which processes must never see them?
- Which seams are real (a swap you can name and expect) and which would be speculative?

**Build.** Master Tasks 1 through 8 and runtime Tasks 1 through 7 carry the evidence. The deliverable for the phase itself is a component table, a data-flow diagram, and short ADRs for the four load-bearing calls: Neon over a vendor store, Postgres-backed jobs over Redis, a simple Python workflow engine over LangGraph, and local Docker isolation.

**Proof gate.** Review every component against the eight attributes above. No secret and no private-code path may cross a boundary you have not declared.

**Answer these.**
1. What is a trust boundary, and name three in this system.
2. Why is "one implementation behind an interface" usually wrong, and why is the `WorkflowEngine` seam an exception?
3. An installed runner needs PR data from GitHub. Why does it not hold a GitHub App private key, and what does it hold instead?
4. What does an ADR record that a code comment cannot?

**Traps.**
- ⚠️ Drawing boundaries in prose and never in a test. A boundary with no test is a wish.
- ⚠️ Adding a seam for every dependency. Seams cost indirection, so spend them where a swap is likely.

---

## Phase 2 - ⬜ Security and Trust Boundaries

**Concept.** Threat modelling is four questions: what are the assets, who wants them, how would they get them, and what stops that. For an AI system two threats are unusual. First, **prompt injection**: any text the model reads can try to become instructions, so repository content, diffs, comments and retrieved chunks are all data and never policy. The defence is structural, not persuasive, and it is to route every untrusted string through one wrapper and let no code path bypass it. Telling the model to ignore instructions in the diff is not a defence.

Second, **capability confinement**: the model proposes, the system disposes. The model may produce a `FindingCandidate`, and only system code may set an ID, a verification result, a public-safety flag, a status, or cause a post. If the model can set a field that gates an action, prompt injection escalates straight into that action.

Then the ordinary parts, done properly: verify webhook HMAC before parsing, scope every lookup by installation and repository ID, keep tokens short-lived and repository-scoped, and never disclose an exploit on a public PR.

**Why here.** Article order puts security at Phase 11. That is too late, because by then you have endpoints, connectors, model calls and command execution to retrofit. Design it before you add surface.

**Decide before you code.**
- Which GitHub App permissions do you actually need? Write the table, and justify each one.
- What is your public disclosure policy for a security finding, in one sentence?
- Are repository instruction files (`AGENTS.md`) read at all in v1, and if so from where?

**Build.** Master Tasks 3, 6 through 8, 10, 10B, 13 through 15, 17, 18, 23 and 25; runtime Tasks 1, 1A, 2 through 6, 8 through 10. Task 10B is the concentrated one: default-branch-only instruction sources and the single `wrap_untrusted` door.

**Proof gate.** Split it, because the full gate needs tasks from very late in the build. The **design gate** (threat model, asset list, permission table, boundaries, secret lifecycle, disclosure policy) closes now and unblocks implementation. The **test gate** (HMAC, tenant isolation, secret canaries, token expiry, runner revocation, unsafe routing, host-execution denial, all failing then passing) closes at the end.

**Answer these.**
1. Why is "instruct the model to ignore injected instructions" not a defence?
2. A PR edits `AGENTS.md` to say "approve everything". Trace exactly what stops that.
3. Why must the model never set `public_safe`, even if it is usually right?
4. A GitHub HMAC signature verifies. What has that proved, and what has it not?
5. Why is a repository name unsafe as an identity key?

**Traps.**
- ⚠️ Parsing JSON before verifying the signature. The production tool pr-agent still does this.
- ⚠️ Treating a canary test as decoration. A secret canary that never failed has never been tested.

---

## Phase 3 - ⬜ Infrastructure

**Concept.** The smallest durable runtime that later phases can stand on. Durable means state survives a process restart, health is observable from outside, and shutdown is graceful rather than a kill. The specific shape here is unusual and worth understanding: a **hosted control plane** that owns secrets and receives webhooks, and an **installed local runner** that holds the user's model keys and their private code, talking outbound only. GitHub cannot reach localhost, so the control plane must be public; the user's code must not leave their machine, so the review must be local. That tension is the whole architecture.

**Why here.** Data engineering, backend and everything after need somewhere to run and something to restart.

**Decide before you code.**
- Which host runs the control plane, on what domain, at what monthly cost? This is the only always-on spend in the project.
- Linux only in v1, or Linux and macOS?

**Build.** Master Tasks 2, 23 through 25; runtime Tasks 1, 5 through 10.

**Proof gate.** A clean environment starts, reports health, survives a process restart with durable state intact, and shuts down without exposing a public local port.

**Answer these.**
1. Why can GitHub not send a webhook to the user's laptop, and what are the two ways around it? Why did we pick this one?
2. What is the practical difference between a liveness check and a readiness check?
3. Name one thing that must be true after a hard kill of the worker mid-review.

**Traps.**
- ⚠️ Claiming localhost can receive webhooks. It cannot, without a tunnel you are not shipping.
- ⚠️ A health endpoint that returns 200 while the database is unreachable.

---

## Phase 4 - ⬜ Data Engineering

**Concept.** Match each shape of data to how it is accessed, how long it lives, how private it is, and how consistent it must be. Four ideas do the work here. **Immutable migrations**: applied schema changes are never edited, because a checksum somewhere already recorded them. **Append-only records**: events and human decisions are written, never updated, so history cannot be rewritten. **Leases**: a worker claims a job for a bounded time, so a crashed worker's job returns to the queue instead of stranding. **Retention**: private data has an expiry and a deletion path, decided now rather than after someone asks.

The hard part on this project is the boundary. Hosted Neon may hold identity, job state, redacted events and aggregate costs. Findings, rationale, diffs, chunks and decisions are local. Migration `0001` predates that rule and violates it, which is what runtime Task 1A exists to fix.

**Why here.** Backend and event recording write into these tables. Getting the shapes wrong here is expensive everywhere after.

**Decide before you code.**
- How long does a PR snapshot live? A finding? A raw trace?
- What happens to data on repository uninstall versus account deletion?

**Build.** Master Tasks 2, 4, 5, 7 through 9, 12, 18, 20; runtime Tasks 1, 1A, 5, 7, 9, 10.

**Proof gate.** Fresh migration, repeat migration, rollback, lease concurrency, tenant isolation, retention and delete-account tests all pass on Neon-compatible Postgres, and the hosted schema passes `assert_no_private_columns`.

**Answer these.**
1. Why is `FOR UPDATE SKIP LOCKED` the right primitive for claiming a job, and what breaks without `SKIP LOCKED`?
2. Two workers claim at the same instant. Explain why only one wins.
3. Why does a lease need an owner ID and not just an expiry?
4. `schema_migrations` is keyed by filename. What does that forbid, and why did that push us to timestamp prefixes?
5. Why is an append-only decision log worth more than a mutable status column?

**Traps.**
- ⚠️ Editing an applied migration to make a test pass. You already burned four fix rounds on this.
- ⚠️ Assuming immutable means the tables it created can never be dropped. It does not.

---

## Phase 5 - ⬜ Backend, API, and Connectors

**Concept.** Typed, authenticated, idempotent boundaries around everything external. **Idempotency** is the key word: the network will deliver the same message twice, so every entry point needs a natural key that makes the second delivery a no-op. GitHub hands you `X-GitHub-Delivery` for exactly this. A **connector** is the pattern of wrapping an external service in a typed result that records what happened (operation, status, latency, byte counts, hash) without recording what was said (headers, tokens, bodies). That distinction is what lets you debug in production without leaking.

The webhook rule that people get wrong: acknowledge fast, but only after the work is durably queued. Returning 200 before the job is safely stored means GitHub thinks you have it and you do not.

**Why here.** These are the facts the model will later reason about. Build the facts first.

**Decide before you code.**
- Which PR actions trigger a review, and which are ignored? `opened`, `reopened`, `ready_for_review`, `synchronize`, draft, closed.
- When a new commit lands mid-review, do you cancel or let the stale run finish?

**Build.** Master Tasks 3, 4, 6 through 8, 17, 21; runtime Tasks 2 through 4, 8.

**Proof gate.** One signed webhook is acknowledged after durable enqueue, one assigned runner claims it, one repository-scoped token fetches the PR, and a retried delivery produces no second job and no second review.

**Answer these.**
1. What exactly makes an endpoint idempotent, and what is the natural key here?
2. Why acknowledge after the enqueue rather than before?
3. What may a connector audit record, and what must it never record?
4. Why is a repository-scoped token that expires in minutes safer than one that lasts a day, given both are secret?

**Traps.**
- ⚠️ In-memory dedup. It dies with the process and does nothing across two replicas.
- ⚠️ Logging a request or response body "just for debugging". That is how tokens end up in logs.

---

## Phase 6 - ⬜ Observability and Tracing

**Concept.** In a deterministic system you debug by reading code. In an agent system you cannot, because the same input can produce a different output, so you debug by reading history. That makes the **event spine** load-bearing rather than nice to have: one append-only stream, one row per span, carrying trace ID, parent span, timestamp, kind, cost, latency and outcome. One stream then serves three consumers at once, a trace viewer, an audit trail, and a cost ledger.

The correlation idea is **trace ID plus span parent**. A trace ID ties every row for one review together; the parent link gives you the shape. On this project the trace is split across two machines, hosted and local, so the join key must be explicit and the ordering must be causal. Two clocks will disagree, so never sort a merged trace by wall time.

**Why here.** Article order puts this at Phase 10, after the model work. That is backwards: you want the recorder running before the behaviour gets complicated, not after.

**Decide before you code.**
- What is the redaction level for a trace you would hand to a user in a support bundle?
- Does the model's raw prompt get stored, hashed, or dropped?

**Build.** Master Tasks 5, 8, 10, 18, 20 through 22, 26; runtime Tasks 3 through 5, 5A, 9, 10. Runtime Task 5A owns the cross-store join and the `reviewer trace <job-id>` command.

**Proof gate.** From one review job ID, reconstruct webhook receipt, job claims, GitHub calls, model calls, decisions, posting, cost and errors, across both stores, with no manual database work and no secrets or unrestricted private source in the output.

**Answer these.**
1. Why does a non-deterministic system need history in a way a deterministic one does not?
2. What is a span, and what does the parent link buy you that a flat list does not?
3. Why can a merged trace not be ordered by timestamp?
4. What is the difference between a redacted trace and a useful one, and how do you get both?

**Traps.**
- ⚠️ Splitting a trace across two stores with no shared key. That is not a trace, it is two logs.
- ⚠️ Storing the full prompt with private source in it, then shipping it in a support bundle.

---

## Phase 7 - ⬜ Evaluation Foundation

**Concept.** This is the phase that separates engineering from demoing, and it is the one both reference implementations skip. Evaluation needs four things. **Ground truth**: cases where you know the right answer, ideally labelled by something other than your own opinion. **Matching**: a deterministic rule for deciding whether a produced finding corresponds to an expected one, since string equality will not do and an LLM judge silently inventing ground truth is worse than no eval. **Metrics** that fit the job: precision (of what it said, how much was right), recall (of what mattered, how much it caught), and false findings per PR, which is the one a reviewer actually feels. **Repeats**, because a model is non-deterministic, so a single run is an anecdote.

The mining trick is the good idea here. A commit that fixes a bug tells you its parent contained that bug. That gives you labels from history rather than from taste, and the set grows every time anyone fixes anything. Mining produces *candidates*, though, not truth: a commit message is a guess, so a human still audits before a case enters the holdout set.

**Why here.** Article order puts evaluation at Phase 9, after multi-agent work. Then you have no way to know whether the agents helped. Define the ruler before you start cutting.

**Decide before you code.**
- What counts as a **match**? Same file and overlapping lines, or also the same category? What do you do with a semantic near-match?
- What is the **holdout** split rule? Time-based is usually right, because it prevents leaking future fixes into past cases.
- Which licensed public repositories supply publishable cases, given FoodSpector cases cannot be committed?

**Build.** Master Task 9 is the phase. It now also owns `run_eval` and a `FixtureReviewer`, built against an injected `ReviewerCallable`, so the harness exists before any model does. Tasks 10A, 11, 13, 14, 19, 20, 24 and 26 feed it later.

**Proof gate.** The eval runner produces a versioned report from a frozen holdout set, driven by recorded fixtures and making no model call. A human checks uncertain matches. Task 9 alone must satisfy this.

**Answer these.**
1. Precision is 95% and recall is 20%. Describe the reviewer's experience of using this tool.
2. Why is "false findings per PR" more useful to a reviewer than precision?
3. Why must mining produce candidates rather than labels?
4. Why does the harness take an injected reviewer instead of importing the model provider?
5. Why three runs per case rather than one?

**Traps.**
- ⚠️ Letting an LLM judge quietly set ground truth. Then you are measuring agreement with yourself.
- ⚠️ A holdout set you tune against. The moment you look at it to fix a prompt, it is a dev set.

---

## Phase 8 - ⬜ LLM and Reasoning Baseline

**Concept.** The smallest thing that could work, measured. One model call, the diff, structured output, no retrieval and no specialists. This is the baseline every later claim is measured against, and skipping it is why most agent systems cannot tell you whether their complexity earns its keep.

Three techniques matter. **Structured output**: you ask for a schema and you validate against it, and a response that does not parse is a failure rather than something to salvage. **Prompt versioning**: prompts are immutable and versioned, so a metric can name the prompt that produced it, because "we improved the prompt" with no version is not a result. **Context packing**: the diff usually does not fit, so you must decide what to include, in what order, and how to say what you left out. That last part is Task 10A and it is the piece the plan was missing.

The subtle failure here is silent truncation. A token budget that drops a changed file produces a review that looks clean on that file. The system does not know, the model does not know, and the human infers there was nothing to say. Three parties agree and all three are wrong.

**Why here.** After evaluation, so the baseline produces a number. Before retrieval and specialists, so those have something to beat.

**Decide before you code.**
- Which provider and model is the v1 default, and what is the fallback chain?
- What is the context budget per model, and how much output allowance is reserved?
- When the diff does not fit, what order do you drop files in, and why that order?

**Build.** Master Tasks 10, 10A, 10B, 11 and 18.

**Proof gate.** The same holdout set runs at least three times per case. The report names dataset, prompt version, provider, model, packing strategy version, run count, coverage, quality, latency and cost.

**Answer these.**
1. Why must packing be deterministic, and what specifically breaks if it is not?
2. A PR changes 60 files and only 40 fit. What does the model see, what does the human see, and what does the report say?
3. Why does the prompt registry reject an update to an existing name and version?
4. Why is a response that fails schema validation a failure rather than something to repair?
5. What is the difference between a patch GitHub omitted and a file your budget dropped, and why do they need different reasons?

**Traps.**
- ⚠️ Tuning the prompt against the holdout set. See Phase 7.
- ⚠️ Reporting a metric without the prompt version. It is not reproducible and therefore not a result.

---

## Phase 9 - ⬜ Memory Architecture and Retrieval

**Concept.** The diff alone lacks context: what calls this function, what the convention is, whether this helper already exists. Retrieval supplies that. Two search modes are needed because code has two kinds of query. **Vector search** finds things that mean something similar and is bad at exact symbol names. **Full-text search** finds `parse_delivery_id` exactly and knows nothing about meaning. **Reciprocal rank fusion** merges two ranked lists without needing their scores to be comparable, which is why it is the standard answer.

Two correctness details decide whether this works at all. **Generations**: embeddings from different models or dimensions must never mix, so an index build is a generation that becomes active atomically. **Freshness**: a chunk from an old commit can be actively wrong, so retrieval is scoped by installation, repository and commit.

Retrieval has a structural blind spot worth knowing. It returns chunks relevant to the diff, so it can never tell you a **global** property like "this codebase soft-deletes everywhere", because no single chunk states it. Two other sources fill that gap and they differ in kind. A **repository profile** is a model-written summary, so it is inferred and can be confidently wrong, which is why its invariant-shaped claims stay candidates until a human promotes them. A **code graph** is parsed rather than generated, so it is a tool with a correct answer, and it is what actually answers blast radius.

And retrieved text is untrusted. An indexed README is an easier injection vector than the diff precisely because nobody reviewing the PR can see it.

**Grounding is not enforcement.** These are two failure modes, not one, and memory only fixes the
first. Grounding stops the reviewer being a confident stranger to the codebase, and retrieval is the
right tool. Enforcement stops a rule being violated silently, and retrieval cannot do it, because
retrieval is probabilistic: a rule about auth may not surface for a diff that does not look
auth-related, which is exactly the case where it was needed. The question that sorts any rule is
whether it can be violated without anyone noticing. Missing auth on function 476 can, so mechanise it
as a test or a constraint. "This abstraction will hurt in a year" cannot, so retrieve it. A written
convention that is always loaded is genuinely stronger than one sitting in a file the model may or
may not read, but it is still a claim nobody verified. Note also that most senior knowledge is not
mechanisable at all: "this module is fragile", "we tried that in March and rolled it back". Retrieval
is its only home.

**Why here.** After the baseline, so there is a number to beat. Retrieval that does not measurably improve the result is cost and latency you added for nothing.

**Decide before you code.**
- What is a chunk? Function, class, fixed window with overlap? Justify it for the languages you review.
- How many chunks enter the prompt, and do they come out of the same budget as the diff?
- How often is a repository profile regenerated, and what does a stale one cost you?

**Build.** Master Tasks 10A, 12, 13 and 13A; runtime Task 7.

**Proof gate.** Run the frozen eval set four ways: no retrieval, vector only, text only, hybrid. Keep hybrid only if it improves the stated quality gate without breaking the cost gate. A result that says retrieval did not help is a real result and gets recorded.

**Answer these.**
1. Why does pure vector search struggle with exact identifiers?
2. What does RRF do that score averaging cannot?
3. Why must the index be a generation with an atomic switch?
4. A retrieved chunk is from a commit three weeks old. What can go wrong?
5. Why is a model-written repo summary held to a different standard than a hand-written instruction file?
5. Why is a retrieved README a better injection vector than the diff itself?

**Traps.**
- ⚠️ Mixing embedding models or dimensions in one table. Silent, and the results just get worse.
- ⚠️ Letting retrieved chunks push a changed file out of the packed diff without recording it.

---

## Phase 10 - ⬜ Tooling and Sandboxing

**Concept.** A model claim becomes evidence only when something checks it. Two kinds of check exist. **Static** checks are cheap and safe: does this file exist, is this line inside the diff, does the quoted evidence text appear at that line. **Executable** checks are expensive and dangerous: run the test and see whether the bug reproduces. That second one is the differentiator, and it means running untrusted code from a stranger's PR.

Sandbox rules are not negotiable and each closes a specific hole: no network (exfiltration), no host secrets (theft), no Docker socket (that mount is root on the host), non-root user, read-only root filesystem, dropped capabilities, CPU, memory, process, disk, output and wall-clock limits, and a temporary work directory cleaned on every exit path including crash.

Two pieces of judgement. A failed reproduction does **not** prove the finding is false, it may be **inconclusive**, and collapsing those two is how you drop real bugs. And if Docker is missing you degrade to analysis-only and say so. You never fall back to running it on the host.

**Why here.** Before human-in-the-loop and before any posting path, because verification is what makes a finding worth a person's attention.

**Decide before you code.**
- Which commands may run at all? An allowlist of repository-configured IDs, never a model-supplied shell string.
- What are the resource limits, and what does hitting one mean: failed or inconclusive?

**Build.** Master Tasks 14 and 23; runtime Tasks 6, 7 and 10.

**Proof gate.** Malicious fixtures cannot reach host files, the Docker socket, cloud metadata endpoints, secrets or unrestricted network. Missing Docker never causes host execution.

**Answer these.**
1. Why is mounting the Docker socket into a sandbox equivalent to giving away the host?
2. Passed, failed, inconclusive, not applicable. Give a concrete example of each.
3. Why is "a read-only checkout" not a sandbox?
4. Docker is installed and the daemon is running. Why is that still not proof that isolation works?
5. Why can the sandbox never accept a command string produced by the model?

**Traps.**
- ⚠️ Treating an inconclusive result as a clean bill of health.
- ⚠️ Cleanup that only runs on the success path. Test the crash path.

---

## Phase 11 - ⬜ Human-in-the-Loop

**Concept.** Human attention is the scarcest resource in the system, so spend it only where consequence, uncertainty or disclosure risk demands it. The routing decision must be **deterministic**: given a finding, a verification result and a policy, the destination is computed by system code, never argued for by the model. If the model can influence routing through severity, confidence or persuasive rationale, prompt injection reaches straight through to the action.

This is the single place where this design departs most from the reference. The article routes on the model's self-reported confidence. That number is poorly calibrated, was never measured, and yet gates everything. Here confidence is stored for later calibration and decides nothing. Verification decides.

Notifications do two jobs that must not share a channel. A private security alert is a **security control**, and whatever app receives it becomes your disclosure boundary. A "your PR was reviewed" ping is a **convenience**. So a channel carries a confidentiality the operator declares, restricted or ordinary, never inferred from the transport, because a chat group gains members without anyone telling you. Push previews count as disclosure too: a title reading "SQL injection in auth.ts line 42" renders on a locked screen.

Human decisions are **append-only**: approve, reject, edit and dispute are all recorded as new rows with actor, note and content hashes. You need that to defend a finding later, and you need it as input to Phase 20 without letting one annoyed developer retrain the system.

**Why here.** Before any public posting path can exist.

**Decide before you code.**
- What is the routing table? For each combination of concern, severity, verification status and public safety, name the destination.
- Who may approve, and does that differ by severity?
- Which channels exist (Slack, Telegram, Discord), and which of them is declared restricted?

**Build.** Master Tasks 15, 17, 21, 22, 24; runtime Tasks 8 and 10. Task 15 owns the channel interface and its confidentiality policy.

**Proof gate.** A public-safe verified finding reaches the approval queue, a high-severity security finding routes privately, an inconclusive finding cannot auto-post, and every human decision is append-only.

**Answer these.**
1. Why is self-reported confidence a bad gate, given the model is often right?
2. Why keep storing confidence at all if it decides nothing?
3. A critical security finding is verified and public-safe. Where does it go, and why not to the PR?
4. Why append-only rather than a status column you update?
5. Why is a channel's confidentiality declared by the operator rather than inferred from the app?

**Traps.**
- ⚠️ Any routing rule that reads a model-supplied field.
- ⚠️ Building an approval queue nobody can keep up with. Escalation rate is a metric, and a rising one is a design failure.

---

## Phase 12 - ⬜ Workflow Orchestration

**Concept.** A review is a sequence of steps with external effects: fetch, review, verify, route, post. Any of them can crash. Orchestration is about making the sequence **resumable without repeating effects**. Two ideas carry it. **Durable step state**, stored separately from the queue state so you do not have two competing sources of truth about what a job is doing. And **idempotent steps**, so a step that already ran can be recognised and skipped rather than re-run, because re-running a model call costs money and re-running a post duplicates a comment.

Then the operational bits: a deadline per node so nothing hangs forever, cancellation when the head SHA moves and the work is now pointless, and an event row per transition so the trace shows the shape.

The engine sits behind a `WorkflowEngine` interface with `run`, `resume` and `get_state`. v1 is a simple Python engine. LangGraph, if ever, is a second implementation that must pass the same tests.

**Why here.** After the steps exist and are individually correct. Orchestrating steps you have not built is guessing.

**Decide before you code.**
- Which steps are durable boundaries, meaning a crash after them must not re-run them?
- On a new head SHA mid-run: cancel immediately, or finish and discard?

**Build.** Master Tasks 16 through 18; runtime Tasks 3 through 5 and 9.

**Proof gate.** Kill the worker at every durable boundary and resume. No repeated model call, no repeated verification, no duplicate GitHub post.

**Answer these.**
1. Why keep workflow step state separate from `review_jobs` queue state?
2. Which step is the most expensive to accidentally repeat, and which is the most damaging?
3. What does `resume` need to know that `run` does not?
4. Why must the LangGraph adapter pass the same tests rather than its own?

**Traps.**
- ⚠️ Two job states that can disagree. Then neither is trustworthy.
- ⚠️ A retry that re-posts. Idempotency at the effect, not just at the step.

---

## Phase 13 - ⬜ Multi-Agent Systems

**Concept.** The default agent-tutorial pattern is fan-out into specialists and merge. It is intuitive, it mirrors how humans divide review, and it costs several model calls instead of one. The honest question is whether it is worth that, and the honest answer requires the baseline from Phase 8 and the harness from Phase 7.

If you do build it, the hard part is not the fan-out, it is the **merge**. Two specialists find the same bug and describe it differently. One says high, one says medium. One quietly times out. Deduplication must be deterministic (repository, head SHA, file, overlapping lines, normalised category), disagreement needs a stated rule, and a partial failure must produce a clearly partial result rather than a confident one.

Note what the field evidence says: the mature production tool ships one call per command and no specialist fan-out at all, after years with paying users.

**Why here.** Late, and gated. This is an experiment with a pass mark, not a feature.

**Decide before you code.**
- On severity disagreement, does the highest win, or does it route to a human?
- One specialist times out. Partial result, or fail the run?

**Build.** Master Tasks 19 and 20. This phase is also where an agentic exploration loop would be
argued for, under the same rules: it is a gated experiment, never a default. See the recorded decision
in the master plan.

**Proof gate.** Specialist mode stays disabled unless it improves high-value recall by at least 5 percentage points without lowering precision, and improves useful findings per dollar by at least 20%. A failed experiment is recorded honestly and is a publishable result.

**Answer these.**
1. Why can this phase not run before Phases 7 and 8?
2. Two specialists report the same bug with different severities. What happens and why?
3. What is "useful findings per dollar" and why is it a better gate than recall alone?
4. Why is a recorded negative result worth more here than quietly shipping the feature?
5. Why does an agentic exploration loop break the Phase 7 harness, the Phase 16 gate and the Phase 20
   gate all at once?

**Traps.**
- ⚠️ Shipping it because it feels more sophisticated. That is how you get four times the cost for the same output.
- ⚠️ A merge that silently drops a finding when two agents disagree.

---

## Phase 14 - ⬜ Reliability

**Concept.** Everything external fails: GitHub rate-limits, the model times out, Neon drops a connection, the runner goes offline, a worker dies mid-job. Reliability is not preventing that, it is bounding what happens when it does.

The toolkit is small and each piece has a precise job. **Timeouts** on every external call, because a call with no timeout is a hang. **Retry classification**, because retrying a 500 is right and retrying a 400 is a bug, and `Retry-After` is a header you obey rather than guess past. **Exponential backoff with jitter**, where the jitter matters because synchronised retries are how you turn a blip into an outage. **Circuit breakers**, so a dead dependency fails fast instead of consuming every worker, with a half-open probe to recover. **Idempotency keys** so a retry does not duplicate an effect. **Dead-letter state**, because a job that can never succeed must stop and be visible rather than retry forever.

The specific case worth thinking about here: the runner finishes the review, then loses the network before acknowledging. The work is done and the control plane does not know. That must not repeat the model calls.

**Why here.** After the pieces exist. You cannot inject a fault into a step you have not built.

**Decide before you code.**
- Which errors are retryable, which are terminal, and which are ambiguous?
- Max attempts and total time budget before a job is dead-lettered?

**Build.** Master Tasks 4, 7, 8, 10, 17, 18, 23; runtime Tasks 3, 4, 6, 9, 10.

**Proof gate.** Fault injection covers GitHub retry, model timeout, database disconnect, runner crash, control-plane outage, lost acknowledgement, stale head and duplicate delivery, with no duplicate effects.

**Answer these.**
1. Why does backoff need jitter? Describe the failure without it.
2. What does a circuit breaker protect, the failing dependency or your own workers?
3. The runner completes locally then goes offline before acknowledging. Walk through recovery.
4. Why is a dead-letter state better than infinite retry?
5. Which of your effects are idempotent today, and which are only idempotent because of a key you added?

**Traps.**
- ⚠️ Retrying a non-retryable error. It wastes budget and hides the real fault.
- ⚠️ A wait loop with no hard deadline. Bound every one and report the timeout loudly.

---

## Phase 15 - ⬜ Governance

**Concept.** For any decision the system made, can you show who or what made it, on what evidence, under which versions, and can you reverse it. Four capabilities. **Audit**: reconstruct the decision. **Versioning**: prompts, models, policies and datasets are named and pinned, so a metric can point at what produced it. **Access**: who may see what, and revocation that takes effect immediately. **Retention and deletion**: what is kept, for how long, and how it goes away on request.

The one specific to AI systems is the **autonomy change record**. Turning on auto-post is a governance event, not a config tweak, and it needs the evidence that justified it recorded alongside it, so you can answer "why did you let it post" a year later.

**Why here.** After the mechanisms exist to govern.

**Decide before you code.**
- Who can change the autonomy level, and what evidence must be attached?
- What does a developer dispute actually entitle them to?

**Build.** Master Tasks 8 through 10, 15, 17, 20 through 22, 24, 26; runtime Tasks 1, 2, 8, 9.

**Proof gate.** For any posted finding, show who or what approved it, what evidence and versions were used, what data remains, how to dispute it, and how access is revoked.

**Answer these.**
1. What must be pinned for a metric to be reproducible six months from now?
2. Why is enabling auto-post a governance event rather than a setting?
3. A user uninstalls from one repository. What is deleted, what is kept, and why?
4. Why must a dispute be recorded even when the finding was correct?

**Traps.**
- ⚠️ Versioning the prompt but not the model, or the dataset, or the packing strategy.
- ⚠️ Revocation that stops new work but leaves a running job holding a live token.

---

## Phase 16 - ⬜ Economics and Cost Control

**Concept.** Two separate jobs: measure cost, and stop before you exceed it. Measuring means per-call token counts and prices rolled up per PR and per repository, which needs the model-call ledger from Phase 6. Stopping means a **budget reservation before the call, not accounting after it**, because an accounting system tells you what you spent and a reservation prevents spending it.

Concurrency is the subtle part. Two workers each check "am I under budget", both see yes, both spend, and together they are over. The reservation must be atomic against the same row the other worker reads.

The metric that matters is not cost per PR, it is **useful findings per dollar**. That is what makes the specialist comparison in Phase 13 decidable, and it is why retrieval and verification each need a cost column next to their quality column.

**Why here.** After the ledger exists and before the expensive experiments.

**Decide before you code.**
- Default per-PR budget, and per-repository period budget. The plan says USD 0.25 per PR. Do you agree?
- On hitting the budget mid-review: fail, or return a partial result marked partial?

**Build.** Master Tasks 5, 10, 11, 13, 18 through 20, 22, 24, 26.

**Proof gate.** Concurrent jobs cannot overspend a repository budget, and the eval report compares useful findings per dollar across baseline, retrieval, verification and specialist modes.

**Answer these.**
1. Why is reservation before the call different from accounting after it?
2. Two workers, one budget. Describe the race and the fix.
3. Why is useful findings per dollar a better decision metric than cost per PR?
4. The budget runs out with two files unreviewed. What does the user see?

**Traps.**
- ⚠️ A budget check that is a read followed by a write. That is the race.
- ⚠️ Counting tokens from the request only. Output tokens usually cost more.

---

## Phase 17 - ⬜ Frontend Engineering

**Concept.** This is a work surface, not a marketing page. It is scanned and operated by someone doing the same task repeatedly, so information design beats decoration: summary before detail, state encoded in form as well as text so what needs attention reads at a glance, and the states that actually occur (loading, empty, partial failure, stale, permission denied) designed rather than discovered.

The security-specific parts: the UI binds to `127.0.0.1`, and **localhost is not authentication** because other local processes can reach an open port, so there is still a session secret and CSRF protection on state-changing requests. And private security detail must never surface in a notification, a page title or a tab title, since those leak past the screen.

**Why here.** Article order puts frontend at Phase 2. Building UI before the backend contracts are stable means rebuilding it. After Phase 6, the shapes are settled.

**Decide before you code.**
- What is the one screen a user lives on, and what is on it?
- GitHub login only, or also a generated local admin session?

**Build.** Master Tasks 21, 22, 25; runtime Task 8.

**Proof gate.** Playwright covers onboarding, review inspection, approval, rejection, private security routing, trace display, cost display, narrow screens and the localhost security checks.

**Answer these.**
1. Why is binding to `127.0.0.1` not sufficient protection?
2. What is CSRF, and why does a localhost-only app still need protection from it?
3. Name three states besides success that this UI must handle, with a concrete trigger for each.
4. Why must a security finding never appear in a notification title?

**Traps.**
- ⚠️ Treating the dashboard as the project. The project is verified review quality.
- ⚠️ Building it before the event and finding contracts stop moving.

---

## Phase 18 - ⬜ Developer Experience

**Concept.** DX here has two audiences: you, working on this daily, and a stranger installing it once. For you it means the loop is fast and diagnosis is possible: fixtures that make a test runnable without network, a way to inspect a prompt, a trace export that is safe to paste into an issue. For the stranger it means `doctor` tells them what is wrong in words they can act on, and install, start, stop, status, update, rollback and uninstall all work without administrator rights.

Two rules that keep biting people. **Secrets never appear in command arguments**, because those land in shell history and process listings, so read them from hidden input into the OS secret store. And **uninstall preserves data by default**, with deletion behind a separate confirmed flag, because a tool that eats your data on uninstall gets uninstalled once.

**Why here.** After the pieces exist, before the public release depends on them.

**Decide before you code.**
- Which OS secret-store library for v1, and what is the documented fallback?
- What does `doctor` check, and in what order, so the first failure is the most useful one?

**Build.** Master Tasks 10, 20 through 23, 25, 26; runtime Tasks 5, 8, 9.

**Proof gate.** A clean supported machine can install, pair, diagnose, start, update, roll back and uninstall from versioned assets, without administrator rights and without any secret reaching the terminal output.

**Answer these.**
1. Why is passing an API key as a command-line argument unsafe, in two distinct ways?
2. Why does `doctor` need an order rather than just a list of checks?
3. What makes an error message actionable rather than merely accurate?
4. Why does uninstall preserve data by default?

**Traps.**
- ⚠️ A doctor that reports "Docker: not working". Say which check failed and what to do.
- ⚠️ Piping a script from `main` into a shell. Versioned assets with checksums, always.

---

## Phase 19 - ⬜ CI/CD for AI and FoodSpector Release

**Concept.** Normal CI gates code. An AI system has three more things that change behaviour and are not code: **prompts**, **models** and **retrieval configuration**. Each needs a gate matching its risk, and the gate for all three is the eval regression check: run the frozen holdout set, compare against the recorded baseline, and block if precision, false findings per PR, high-value recall, cost or latency regress past threshold.

Release adds supply chain: pinned images by digest, non-root containers, checksums, an SBOM, and a tested rollback. Then the shadow run, which is the real gate. The system reviews live PRs and posts nothing while humans label what it found. Thirty non-draft PRs over fourteen days, and only then is auto-post even a question.

**Why here.** Last, because it gates everything before it.

**Decide before you code.**
- What regression threshold blocks a merge, versus warns?
- Who labels the shadow run output, and how long does that take per PR realistically?

**Build.** Master Tasks 20, 23 through 26; runtime Tasks 9 and 10.

**Proof gate.** Release checks pass, install proof passes from a versioned asset, and FoodSpector completes at least 30 non-draft PRs over at least 14 days with the measured gates recorded.

**Answer these.**
1. Name three non-code changes that alter behaviour and must be gated.
2. Why is a shadow run better evidence than the holdout set alone?
3. Why 14 days rather than 30 PRs as fast as possible?
4. Why pin container images by digest rather than tag?

**Traps.**
- ⚠️ Shipping a prompt change through code review alone.
- ⚠️ Counting draft PRs, or your own PRs, toward the shadow run.

---

## Phase 20 - ⬜ Continuous Learning

**Concept.** The system should get better from what actually happened, without letting noise or malice steer it. The danger is **feedback poisoning**: one developer rejects a correct finding because it was inconvenient, and if that single rejection changes behaviour, the system has learned to be quieter about a real problem.

Three defences. A **minimum evidence threshold**, so a pattern needs repeated independent occurrences before it becomes an eval candidate. A **human audit** before anything enters ground truth. And **decay**, so old feedback about code that no longer exists stops voting.

Then **drift**: rejection rate, dispute rate, no-finding rate, cost, latency and retrieval miss rate are all monitored, because a model provider can change behaviour underneath you with no deploy on your side.

Note what learning means here. Nothing is trained and nothing is fine-tuned. Learning is: propose a change to a prompt, a model, retrieval or routing; test it against the frozen holdout and recent checked cases; ship only if nothing regresses.

**Why here.** Last, because it needs the eval harness, the decision log and the drift metrics to already exist.

**Decide before you code.**
- How many independent occurrences before feedback becomes an eval candidate?
- What is the decay window for old feedback?

**Build.** Master Tasks 9, 20, 24, 26.

**Proof gate.** A proposed prompt, model, retrieval or routing change is tested against the frozen holdout plus recent checked cases, and cannot ship when precision, noise, safety or cost regress.

**Answer these.**
1. Describe a concrete feedback-poisoning scenario for this reviewer.
2. Why does old feedback need to decay rather than persist?
3. Your rejection rate doubles with no deploy on your side. Name three possible causes.
4. Why is "we improved the prompt" not a result, and what would make it one?

**Traps.**
- ⚠️ Learning from a single dispute. That is the poisoning vector.
- ⚠️ Treating a drift alert as noise. Something changed, and it was not you.

---

## Suggested route through this - ✅

The phases are a learning and review order, not a strict build order, and the demo cut is what proves the engineering.

1. ✅ **Phase 0 now, on paper, no Cursor.** Half a day. It is the highest-value item here and it needs no code.
2. ✅ **Phase 1 and the Phase 2 design gate next**, also mostly paper. These unblock everything.
3. ✅ **Then the demo cut**: runtime Tasks 1, 1A, 2 through 5 and master Tasks 7 through 11, plus 15 through 17. That is signed webhook, hosted job, local runner, one-agent review, human approval, posted comment, with an eval report behind it.
4. ✅ **Task 10A is the best first Cursor task.** Pure functions, no I/O, no external service, deeply testable, and it teaches context engineering, which is the most transferable skill in the whole build.
5. ⬜ Everything else is post-demo: retrieval, specialists, the dashboard, LangGraph, the public installer.

## Open Decisions - ❓

- ❓ Which real FoodSpector PR walks through the Phase 0 map?
- ❓ What is the one-sentence definition of a useful finding?
- ❓ Which host and public HTTPS domain runs the control plane, and at what monthly cost?
- ❓ Linux only in v1, or Linux and macOS?
- ❓ Which OS secret-store library ships in v1?
- ❓ Which licensed public repositories supply the publishable holdout cases?
- ❓ Which provider and model is the v1 default, and what is the fallback chain?
- ❓ What is the context budget per model, and the reserved output allowance?
- ❓ What counts as a finding match: file plus overlapping lines, or also category?
- ❓ Do you accept USD 0.25 as the default per-PR budget?
- ❓ On a new head SHA mid-run: cancel immediately, or finish and discard?
- ❓ GitHub login only for the dashboard, or also a generated local admin session?
