# Phase 8 - ⚠️ LLM and Reasoning Baseline

| Mark | Means |
|---|---|
| ⬜ | Not done yet. I tick it when it lands |
| ✅ | Done, or in scope and agreed |
| ❌ | Deliberately not doing this |
| ❓ | Open decision, waiting on me |
| ⚠️ | Known trap. Read before writing the code |

**Status - ⚠️ IMPLEMENTATION LANDED, MEASURED BASELINE BLOCKED 2026-09-01.** Master Tasks 10,
10A, 10B, and 11 are ✅ in `2026-08-25-ai-pr-reviewer.md`. Master Task 18 is still marked ⬜ in
that file; this write-up treats it as done because `9685b23` shipped the declared reliability
files and is tonight's start HEAD. The proof gate needs a frozen holdout. The public dataset
has one `dev` case and zero `holdout`.

## 1 - ✅ Why the smallest path is measured first

The learning goal is to measure one model call over a packed diff before retrieval or
specialists spend budget. That order is already in the roadmap: evaluation exists before the
baseline, and the baseline exists before extra context. A specialist comparison that has no
one-agent number is not a comparison.

The one-agent path is `review_pull_request` (`review_pull_request.py:34`). It makes one
`complete_json` call (`review_pull_request.py:67`) and returns `FindingCandidate` values only.

## 2 - ✅ Provider interface and adapters

`ModelProvider` is a protocol with one method, `complete_json` (`provider.py:89`). The request
names the prompt and the schema (`provider.py:60`). The response carries parsed JSON plus
`input_tokens`, `output_tokens`, `cost_usd`, and `latency_ms` (`provider.py:73`). Those four
fields are what a baseline report would quote. They are not filled in on the public dataset
tonight because the holdout path never runs.

OpenAI and Anthropic adapters live under `src/pr_reviewer/models/`. The eval harness does not
import them. `run_eval.py` takes an injected `ReviewerCallable` and makes no HTTP call.

## 3 - ✅ Immutable prompt registry

`PromptRegistry.register` raises `PromptVersionImmutable` if the same name and version is
written twice (`registry.py:27`). `get` raises `PromptNotFound` on a miss (`registry.py:35`).
The one-agent path pins `diff_only_reviewer` version `1`
(`review_pull_request.py:23`).

## 4 - ✅ Structured candidates, not findings

The model may emit `FindingDraft` only (`finding_candidate.py:13`). System-owned fields
(`id`, `review_job_id`, `verified`, `verification_method`, `public_safe`, `status`) are absent
from the draft, not stripped after the fact. `FindingCandidate` is the same shape
(`finding_candidate.py:36`). A posted `Finding` is a later, system-owned type.

## 5 - ✅ Quoted untrusted input

`UntrustedText.__str__` and `__format__` raise (`prompt_boundaries.py:18`). The only string
exit is `wrap_untrusted` (`prompt_boundaries.py:34`). The one-agent path wraps the packed
diff, title, body, and retrieved chunks before they enter the prompt
(`review_pull_request.py:56`).

## 6 - ✅ Deterministic diff budgeting

`pack_diff` packs whole files (`diff_budget.py:27`). Order is a sort key, not dict or set
iteration (`diff_budget.py:36`). The strategy version is
`v1-sensitivity-desc-change-size-desc-path-asc` (`review_context.py:12`). Every omitted file
carries a closed-set `OmissionReason` on `PackedDiff` (`review_context.py:63`).

## 7 - ✅ Reliability around the one call

Task 18 added capped retry (`reliability/retry.py:54`), a circuit breaker, and fail-closed
budgets (`reliability/budget.py:1`). Unset budget denies. That is part of the baseline path:
a model call that cannot name its cap does not run as unlimited.

## 8 - ⚠️ Baseline eval report

`run_eval` repeats each case `config.repeats` times (`run_eval.py:30`). The default for
`run_diff_only_baseline` is 3 (`run_eval.py:40`). `EvalMetrics` already has the named quality,
latency, and cost fields (`types.py:88`). `EvalCase` rejects a holdout row without a human
auditor (`types.py:75`).

The public file `datasets/public/eval_cases.jsonl` has one row: `public-1`, `split=dev`.
`run_diff_only_baseline` raises rather than invent a number (`run_eval.py:47`).

## Design gate - ✅

✅ The one-agent path is a single structured call over a packed, quoted diff. The model cannot
set routing or posting fields. Prompt versions cannot be silently rewritten.

## Test gate - ⚠️ blocked on holdout

⚠️ The proof gate requires the same holdout set, at least three repeats per case, and a report
that names dataset, prompt, provider, model, run count, quality, latency, and cost.

Command, run 2026-09-01 against this checkout:

```text
$ uv run python - <<'PY'
from pr_reviewer.evals.fixture_reviewer import FixtureReviewer
from pr_reviewer.evals.run_eval import load_public_eval_cases, run_diff_only_baseline
cases = load_public_eval_cases()
print([(c.id, c.split) for c in cases])
run_diff_only_baseline(cases, FixtureReviewer.perfect())
PY
public_cases [('public-1', 'dev', 'niresh')]
run_diff_only_baseline BaselineBlocked: holdout is empty; refusing to report a baseline
```

`FixtureReviewer` was the reviewer. No model HTTP client ran. No quality, latency, or cost
number is reported here because none was produced.

## Settled - ✅

- ✅ One model call for the baseline. Retrieval and specialists stay off until they beat this
  path on a real holdout.
- ✅ Holdout cases require a named human auditor. That rule is in the type, not in a comment.
- ✅ An empty holdout refuses a baseline. It does not synthesise one.

## Open Decisions - ❓

- ❓ The eval dataset is still one `dev` case. The miner at `c35c7d1` can produce candidates.
  A human has to audit them before any holdout row exists. Morning job.
