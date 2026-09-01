# Phase 13 - ⚠️ Multi-Agent Systems

| Mark | Means |
|---|---|
| ⬜ | Not done yet. I tick it when it lands |
| ✅ | Done, or in scope and agreed |
| ❌ | Deliberately not doing this |
| ❓ | Open decision, waiting on me |
| ⚠️ | Known trap. Read before writing the code |

**Status - ⚠️ PROOF GATE REPRODUCED AS A BLOCK 2026-09-01.** Master Tasks 19 and 20 are
implemented (`379b358`, `0869afd`). The phase proof asks whether specialists beat the
one-agent baseline. That comparison needs a frozen holdout. The public dataset has none.

## 1 - ✅ Four concerns, off by default

`SPECIALIST_CONCERNS` is security, correctness, tests, docs (`specialists.py:14`).
`ReviewPolicy.specialist_mode` defaults to False (`instruction_sources.py:36`).
`specialists_enabled` is that flag (`specialists.py:37`). The one-agent path in
`review_pull_request.py` stays the live reviewer. Enabling specialists is a policy flip,
not a new default.

## 2 - ✅ Timeout and a missing agent do not drop the rest

`run_specialists` walks the four concerns in tuple order (`specialists.py:41`). A missing
key is recorded on `missing_concerns`. `SpecialistTimeout` records the concern and leaves
already-finished findings in place (`specialists.py:22`). The merge still runs on what
arrived.

## 3 - ✅ Deterministic merge

`aggregate_findings` merges on repository, head SHA, file, overlapping lines, and a
normalised category (`aggregate_findings.py:1`). `normalise_category` collapses case and
separators to hyphen form (`aggregate_findings.py:22`). Higher severity wins. Order does
not come from set or dict iteration. The suite passes a set and a map whose `__iter__`
raises.

## 4 - ✅ LangGraph is an adapter, and it is off

`langgraph_engine_enabled` returns False (`langgraph_engine.py:28`). `LangGraphEngine`
implements the same constructor and `run` / `resume` / `get_state` shape as
`SimpleEngine`. Shared `WorkflowEngine` tests are parametrized over both
(`tests/test_workflow_engine.py`). `simple_engine.py` still does not import langgraph.

## 5 - ⚠️ The measurement is refused, not invented

`run_specialist_comparison` filters `split == "holdout"` and raises `BaselineBlocked`
when that list is empty (`run_eval.py:86`). `useful_findings_per_dollar` raises the same
class when `cost_usd <= 0` (`run_eval.py:101`). It divides `useful_finding_count` by
cost only when a real cost exists. Task 20's `compare_eval_reports` can block precision,
false findings per PR, high-value recall, cost, and latency on synthetic `EvalRun`
objects (`regression_gate.py:48`). It cannot close this phase against a missing holdout.

## 6 - ✅ What this phase did not build

Specialists run in a fixed concern order. That is not parallel execution. There is no
per-file specialist router. One dispute still cannot change a prompt, a policy, a label,
or routing (`feedback_candidates.py`). Those are Task 20 controls around the experiment,
not a claim that the experiment won.

## Design gate - ✅

✅ The specialist path and the LangGraph adapter exist, share the one-agent contracts, and
stay disabled. Merge order is deterministic. A timeout or a missing agent is a partial
result, not a dropped run.

## Test gate - ⚠️ reproduced as a block

The proof gate is: specialist mode remains disabled unless it beats the one-agent
baseline on recall, precision, and useful-findings-per-dollar.

Command, run 2026-09-01 against this checkout:

```text
$ uv run python -c "from pr_reviewer.evals.fixture_reviewer import FixtureReviewer; from pr_reviewer.evals.run_eval import load_public_eval_cases, run_specialist_comparison; from pr_reviewer.reviewer.specialists import specialists_enabled; from pr_reviewer.security.instruction_sources import default_review_policy; from pr_reviewer.workflow.langgraph_engine import langgraph_engine_enabled; print('specialists_enabled', specialists_enabled(default_review_policy())); print('langgraph_engine_enabled', langgraph_engine_enabled()); run_specialist_comparison(load_public_eval_cases(), FixtureReviewer.perfect(), FixtureReviewer.perfect())"
specialists_enabled False
langgraph_engine_enabled False
BaselineBlocked: holdout is empty; refusing to report a specialist comparison
```

No precision, recall, cost, or useful-findings-per-dollar number is recorded. The
harness refused. That is the gate result.

## Settled - ✅

- ✅ Specialists and LangGraph stay off until a holdout comparison passes.
- ✅ Merge key is repository, head SHA, file, overlap, normalised category.
- ✅ Useful-findings-per-dollar is not a ratio times a PR count. It needs a counted
  useful finding and a positive cost, or it raises.

## Open Decisions - ❓

- ❓ Whether specialists are worth keeping waits on a human-audited holdout. The miner
  already produces candidates. The auditor does not exist tonight.
