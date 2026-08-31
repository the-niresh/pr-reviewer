# Phase 12 - ✅ Workflow Orchestration

| Mark | Means |
|---|---|
| ⬜ | Not done yet. I tick it when it lands |
| ✅ | Done, or in scope and agreed |
| ❌ | Deliberately not doing this |
| ❓ | Open decision, waiting on me |
| ⚠️ | Known trap. Read before writing the code |

**Status - ✅ PROOF GATE REPRODUCED 2026-09-01.** Master Tasks 16 and 17 are ✅. Master Task 18
is still marked ⬜ in the master plan; treated as done because `9685b23` is HEAD and shipped
the declared reliability files. Product-runtime Tasks 3, 4, 5, and 9 are ✅.

## 1 - ✅ A contract, not a framework

ADR-003 put a `WorkflowEngine` protocol in front of any graph library
(`engine.py:42`). The three methods are `run`, `resume`, and `get_state`. LangGraph is a
later adapter. It is not required for this phase. Binding the runner to one framework would
make Task 19 a rewrite instead of an addition.

## 2 - ✅ Typed steps and typed outcomes

`STEP_NAMES` is fetch, baseline_review, retrieval, verification, routing, storage
(`engine.py:10`). `WorkflowResult.status` is `completed`, `cancelled`, or `failed`
(`engine.py:8`). `WorkflowState` has completed steps and an outcome. It has no queue
`running` field (`engine.py:35`). Queue state stays on `review_jobs`.

## 3 - ✅ Step state is local

`SqliteWorkflowStore` writes `workflow_runs` and `workflow_steps` on the runner
(`workflow/store.py:21`). Hosted Neon has no `workflow%` tables. The suite asserts that
(`tests/test_workflow_engine.py`, `test_hosted_schema_has_no_workflow_tables`). A hosted
step table would either grow findings-adjacent text or invent a second running state.

## 4 - ✅ Resume without repeating effects

`SimpleEngine._advance` skips any step already present in `completed_outputs`
(`simple_engine.py:110`). A crash inside a handler does not mark that step complete. Resume
retries only the incomplete tail. Model calls live in `baseline_review`. Posting lives in
`storage`. The resume tests count both.

## 5 - ✅ Cancellation, stale head, and bad leases

`_checkpoint` runs before each incomplete step (`simple_engine.py:130`). A cancelled lease
records `cancelled`, not `invalid_or_expired`. A moved head SHA records `superseded` and
stops before the next handler. Those reasons are distinct on purpose: one is an operator
action, one is a GitHub fact, one is a dead lease.

## 6 - ✅ Deadlines that fail loudly

`wait_for_artifact` uses a monotonic deadline and raises `TIMEOUT`
(`simple_engine.py:21`). A step timeout is the same word (`simple_engine.py:121`). There is
no hang-and-hope wait.

## 7 - ✅ Events and reliability around the engine

Every completed step can emit a flat `workflow.step_completed` payload
(`simple_engine.py:125`). Task 18 wraps the work the steps call: retry with a hard deadline
(`reliability/retry.py:54`) and fail-closed budgets (`reliability/budget.py:1`). The engine
does not import `pr_reviewer.db` or `pr_reviewer.control_plane`.

Task 17 sits on the storage end of the same pipeline: `post_review` checks the head SHA
immediately before submit and recovers a timed-out-but-accepted review from an idempotency
marker. Resume must not post a second review. That is why storage is a counted effect in
the crash tests.

## Design gate - ✅

✅ The runner can die after any completed step and continue without a second model call or a
second GitHub post. The hosted queue does not store step progress.

## Test gate - ✅ reproduced

The proof gate is: kill the worker at each durable boundary and resume without repeating
model calls, verification, or GitHub posting.

Command, run 2026-09-01 against this checkout:

```text
$ flock -w 3600 /tmp/pr-reviewer-pytest.lock uv run pytest -q tests/test_workflow_engine.py -k 'resume or rerunning or cancelled or superseded or timeout or six_steps'
...........                                                              [100%]
11 passed, 8 deselected in 0.71s
```

`test_resume_after_crash_before_each_step_does_not_repeat_completed_effects` parametrizes
the crash point across all six steps. After resume, `model_calls`, `posts`, and `notifies`
are each 1. `test_rerunning_a_completed_workflow_is_a_no_op_for_external_effects` is the
same count on a second `run`.

## Settled - ✅

- ✅ Simple Python engine first. LangGraph is an adapter behind the same tests.
- ✅ Step state is local SQLite. `review_jobs` remains the only queue state.
- ✅ Outcome cannot be `running`. That word belongs to the lease, not the workflow row.

## Open Decisions - ❓

- ❓ Whether LangGraph is worth keeping is Task 19's measurement, and that measurement is
  already blocked on the empty holdout. This phase does not decide it.
