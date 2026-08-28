# Phase 0 - ⬜ Cognitive Design

| Mark | Means |
|---|---|
| ⬜ | Not done yet. I tick it when it lands |
| ✅ | Done, or in scope and agreed |
| ❌ | Deliberately not doing this |
| ❓ | Open decision, waiting on me |
| ⚠️ | Known trap. Read before writing the code |

**Status - ✅ APPROVED 2026-08-27.** Trigger, autonomy level, selectivity cap, and the definition of a
useful finding are all approved by the owner. Proof gate reproduced against a real FoodSpector change.
Phase 1 is now the active phase.

## Provenance - ⚠️

⚠️ This was **drafted from general code-review practice plus the FoodSpector invariants already
recorded in the workspace `CLAUDE.md`**. It was not derived from observing a real review session,
because the owner does not have a large body of review habit to draw on.

That matters later. Where a normal Phase 0 records *what a senior reviewer does here*, this one
records *what a competent reviewer should do here*. Those are not the same, and the difference is
an assumption the shadow run in Phase 19 will test. Revisit this file with real labels afterwards.

## 1 - ✅ What a reviewer actually does, in order

Ordered by value, which is close to the reverse of how most people review.

1. Read the description and the linked issue. What is this meant to do?
2. Look at the **file list before any code**. Does the shape match the description? A "fix a typo"
   PR touching 30 files is itself the finding.
3. Are there tests, and do they test the **new behaviour** or only the happy path?
4. Read the main change. Does it do what the description says it does?
5. Check the repository's own invariants. For FoodSpector these are already written down:
   a submitted run must project a `complianceRecord` on all three submit paths; the store snapshot
   is immutable once written; every `auditInstance` needs a valid store; soft deletes only; every
   Convex function carries an auth check; `convex/_generated/` is never hand-edited; any reader of
   run photos must handle **both** photo seams or it silently drops evidence.
6. Check the edges: swallowed errors, nulls, resource cleanup, ordering, concurrency.
7. Blast radius. Who else calls this? Is a contract changing?
8. Security-sensitive paths get a second pass: auth, user input, queries, file paths, secrets.
9. Style and naming. Lowest value. A linter should own this and we should not comment on it.

⚠️ Steps 1 through 3 catch more real problems than 4 through 9 combined, and they are the steps
people skip when they are busy. An AI reviewer that only does step 4 is doing the least valuable
half of the job.

## 2 - ✅ Trigger and deliverable

**Trigger - ✅ approved:** the pull request becomes **review-ready**. In GitHub terms that is
`opened` when the PR is not a draft, or `ready_for_review`. Plus `synchronize` when new commits
land, debounced, with the older run superseded (master Task 7 already builds supersession).

Why not *after CI passes*: it needs a second event source (`check_suite` / `workflow_run`), it
delays feedback by however long CI takes, and a PR that fails CI can still contain exactly the
bug you wanted caught. Keep it as a per-repository policy flag, **default off**.

Why not *every commit*: a 20-commit PR becomes 20 reviews and 20 times the cost, and most of
those commits are work in progress. Supersession already covers "new commits arrived".

**Deliverable, precisely:** at most five findings, each anchored to a file and a line range in the
**current** head SHA, each carrying a rationale, evidence, and a verification status. Posted as one
review on the pull request, or routed to the private queue when it is not safe to disclose.
Consumed by the PR author, and before them by the human approver.

## 3 - ✅ Which component does which step

**What a bucket is.** Every step in section 1 gets assigned to exactly one kind of component.
Four kinds:

- **trigger** - an event we react to.
- **tool** - it has a correct answer we can compute. No judgement, cannot hallucinate.
- **model** - genuinely needs reading comprehension or fuzzy judgement.
- **human** - the consequence of being wrong is high and the action is hard to undo.

⚠️ The reason this matters: if you let the model do a tool's job, you pay tokens for a guess where
you could have had certainty. Several steps below look like judgement and are actually `grep`.

| Step | Bucket | Note |
|---|---|---|
| PR becomes review-ready | trigger | GitHub webhook |
| Read description and issue | model | |
| File list versus description | model | judgement about whether the shape fits |
| Are there tests at all | **tool** | does any path matching the test pattern change |
| Do the tests cover the new behaviour | model | |
| Does the code do what it says | model | the core review call |
| `convex/_generated/` untouched | **tool** | pure path match |
| Soft deletes only | **tool** | look for hard delete calls in the diff |
| Auth check in every Convex function | **tool then model** | tool finds new exported functions, model judges the check |
| `complianceRecord` on every submit path | model | needs to understand what a submit path is |
| Both photo seams handled | **tool then model** | tool finds readers, model judges completeness |
| Edges: errors, nulls, cleanup | model | |
| Blast radius, who calls this | **tool then model** | grep callers, model judges the impact |
| Security-sensitive paths | model, then **human** | model finds, human decides disclosure |
| Style and naming | **tool** | linter owns it, we stay silent |
| Approve a public post | **human** | until the release gates pass |
| Disclose a security finding publicly | **human** | always, permanently |

## 4 - ✅ Autonomy

⚠️ **Correcting a misunderstanding worth naming.** Giving the agent good docs and requirements is
**grounding**, not autonomy. Grounding improves the quality of the output. Autonomy is *how much
the system does without a person checking first*. They are linked, but only through evidence:
better grounding produces better output, measured output earns more autonomy. Skipping the
measurement and granting autonomy because the context looks good is exactly how an agent ships
confident garbage.

The grounding idea is already in the plan, and it is a good one. Master Task 10B reads instruction
files from the repository default branch. FoodSpector's `CLAUDE.md` is already that file.

**The ladder.**

| Level | What it means | When |
|---|---|---|
| 0 | Off | |
| 1 | System drafts, visible in the dashboard, nothing posted | ✅ launch here, shadow mode |
| 2 | System posts only what a human approved | after the shadow run in Phase 19 |
| 3 | Verified public-safe findings post automatically, everything else queues | only after the eval gates pass |
| 4 | Everything posts unattended | ❌ not in v1 |
| - | System approves or merges a PR | ❌ never |

**Launch autonomy: level 1.** Consequence of a wrong public comment is a developer losing trust in
the tool, which is slow to win back. Reversibility is poor: you can delete a comment, you cannot
delete having been wrong in front of the team. Evidence today is zero. All three point to level 1.

## 5 - ✅ Failure matrix

| # | Failure | Looks like | Who notices | How fast | What stops it |
|---|---|---|---|---|---|
| 1 | Hallucinated finding | confident comment about a bug that is not there | author | immediately | sandbox verification, required evidence |
| 2 | Noise | 15 findings, 2 useful | author | within a week | selectivity cap, precision gate |
| 3 | Missed real bug | silence | nobody, until production | months | recall measured on the holdout set |
| 4 | **Silent truncation** | a clean review of a file it never read | **nobody** | **never** | Task 10A omission reporting |
| 5 | Stale review | comments on lines that have moved | author | immediately | head SHA check before posting |
| 6 | Public security disclosure | an exploit described on a public PR | the internet | permanent | private routing, never auto-post |
| 7 | **Prompt injection** | agent obeys instructions inside the diff | **nobody** | **never** | `wrap_untrusted`, model cannot set gates |
| 8 | Cost runaway | one huge PR eats the month's budget | you, on the bill | end of month | budget reservation before the call |
| 9 | Duplicate posting | the same comment five times | author | immediately | idempotency key per repo, PR, head SHA |
| 10 | **Silent non-delivery** | the review simply never happens | **nobody** | **never** | dead-letter state plus an alert |

⚠️ Rows 4, 7 and 10 are the dangerous class: **nobody notices and nothing complains**. Everything
looks fine. These are the ones worth building tests for first, because no user will ever report them.

Row 4 is the answer to "give me a failure where the system is confidently wrong and no test would
catch it". The budget drops a file, the model never knew it existed, the reviewer sees no comment
and concludes there was nothing to say. Three parties agree and all three are wrong.

## 6 - ✅ Definition of a useful finding

> **A finding is useful if a competent reviewer would have raised it, and the author would change
> the code because of it.**

Two clauses, and the second is the sharp one. It excludes findings that are *true but ignorable*.

- Style and naming are not useful. The linter owns them.
- "Consider extracting this into a helper" is not useful unless there is a defect.
- A correct observation the author will read and skip is noise, and noise is what gets the tool muted.

## 7 - ✅ Selectivity policy

- ✅ Hard cap of **five** posted findings per pull request.
- ✅ **Zero findings is a normal, successful outcome.** Not a failure, not retried, not padded.
- ✅ Over the cap: keep the highest-severity verified findings, drop the rest, and record how many
  were dropped so the number is visible in the report.
- ❌ Never pad a review to look thorough.

## Proof gate - ✅ Reproduced

✅ Walked commit `43ec43a`, *fix(auditor): share device token across subdomains, fix auditor host
routing*, through section 1. Described, not quoted, so no private source enters this file.

**What the change does.** A device-lock token lived in `localStorage`, which is scoped per origin, so
each tenant subdomain minted its own. An internal auditor redirected to the auditor host was treated
as a brand-new device and locked out of an account they were already approved on. The fix moves the
token to a cookie scoped to the registrable domain, keeping `localStorage` as a read fallback so
already-approved devices survive, and still writing it so the token survives a cookie purge. It also
changes host routing in three files, and touches two Convex files.

| Step | What it produced here | Guards |
|---|---|---|
| 1 Description and issue | Clear. States the bug, the cause, and the fix. | row 3 |
| 2 File list versus description | ⚠️ **Fires.** The description is about tokens and routing, but the change also deletes 8 screenshots, refreshes READMEs, and rewrites `CLAUDE.md`. A reviewer asks whether this should have been two PRs. | rows 2, 3 |
| 3 Tests present | ✅ Tool answers yes: four test files change, covering `deviceId`, `tenant`, `auditorApp`, `auditorRoutes`. | row 3 |
| 3b Tests cover new behaviour | Model question. Do they cover the **fallback path**, not just the cookie path? | row 3 |
| 4 Does it do what it says | Model reads the routing change across three files. | row 3 |
| 5 Repo invariants | Two Convex files change, so *auth check in every Convex function* applies. Tool finds the changed exports, model judges the checks. | rows 1, 3 |
| 6 Edges | ⚠️ **Fires.** `localStorage` is kept as a fallback. Is there a window where a stale or planted `localStorage` token is honoured after the cookie exists? That is the review question this PR turns on. | rows 1, 3 |
| 7 Blast radius | Who else reads the device token or calls `auditorAppOrigin`? A parsed call graph answers this, not a guess. | row 3 |
| 8 Security second pass | This is a device-identity boundary change. Any finding here routes **privately**, never onto the PR. | row 6 |
| 9 Style and naming | Unused-import cleanup is in the diff. We say nothing. The linter owns it. | row 2 |

✅ **Every step traces to a human need or to a named row in section 5.** No step traced to neither, so
nothing was deleted from section 1.

✅ **What this validated.** Steps 2 and 6 are where the real findings are, and both are cheap. Step 2 is
a file-list comparison before reading any code. Step 6 needs the diff and nothing else. Neither needs
repository exploration, which supports the recorded decision against an agentic loop.

⚠️ **What it did not validate.** This is one change, chosen by me, and the map was drafted from general
practice rather than from watching the owner review. The Phase 19 shadow run over at least 30 PRs is
what actually tests it.

## Settled - ✅

- ✅ Trigger: pull request becomes review-ready, plus `synchronize` with supersession. CI-gating is a
  per-repository flag, default off.
- ✅ Launch autonomy: level 1, shadow mode. Nothing posts.
- ✅ Selectivity cap: five posted findings per pull request. Zero is a normal successful outcome.
- ✅ A finding is useful if a competent reviewer would have raised it, and the author would change the
  code because of it.
- ✅ Proof gate walked against `43ec43a`.

## Open Decisions - ❓

- ❓ Should this file be tracked by git? `docs/phases/` is not currently ignored, unlike `docs/specs/`.
