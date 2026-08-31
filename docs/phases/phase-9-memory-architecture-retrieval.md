# Phase 9 - ⚠️ Memory Architecture and Retrieval

| Mark | Means |
|---|---|
| ⬜ | Not done yet. I tick it when it lands |
| ✅ | Done, or in scope and agreed |
| ❌ | Deliberately not doing this |
| ❓ | Open decision, waiting on me |
| ⚠️ | Known trap. Read before writing the code |

**Status - ⚠️ IMPLEMENTATION LANDED, MEASURED COMPARISON BLOCKED 2026-09-01.** Master Tasks
10A, 12, 13, and 13A are ✅. Product-runtime Task 7 is ✅. The proof gate asks for a comparison
on the frozen eval set. That set has no holdout row, so no source can be kept or discarded on
measured quality or cost tonight.

## 1 - ✅ One shared budget with the packed diff

`pack_diff` spends `ContextBudget.tokens` on whole changed files first (`diff_budget.py:27`).
`fit_retrieved_chunks` spends only what remains after `packed.prompt_tokens`
(`hybrid_search.py:89`). A retrieved chunk cannot push a changed file out of the packed diff.
That is the Phase 9 rule that already exists in code, not a later preference.

## 2 - ✅ Stable chunks and embedding generations

`chunk_source` splits one file (`chunk_code.py:53`). `chunk_tree` walks a tree
(`chunk_code.py:62`). Python uses the AST walk (`chunk_code.py:92`); other languages use
windows (`chunk_code.py:140`). Embeddings are stored against an embedding generation so a
stale generation can be left behind without mixing vectors from two indexes.

## 3 - ✅ Hybrid retrieval and RRF

`retrieve_context` runs a vector rank and a full-text rank, then merges with reciprocal rank
fusion (`hybrid_search.py:40`). `reciprocal_rank_fusion` uses `k = 60` (`rrf.py:6`). Tie
breaks are first-seen order (`rrf.py:16`), not set iteration.

Both ranks are scoped by `installation_id`, `repository_id`, `commit_sha`, and
`g.state = 'active'` (`hybrid_search.py:131`). That is repository isolation and freshness in
the query, not in a later filter.

## 4 - ✅ Default off

`RETRIEVAL_ENABLED_DEFAULT` is `False` (`hybrid_search.py:17`). `retrieve_context` returns
`[]` unless `enabled` is passed true (`hybrid_search.py:52`). The path exists. It does not
spend tokens until a measured gate says it should.

Selected chunk IDs can be recorded through `record_selection` (`hybrid_search.py:84`) so a
review can be replayed with the same context.

Retrieved text is wrapped as untrusted (`hybrid_search.py:105`).

## 5 - ✅ Candidate-only repository profile

`apply_profile` returns the same `ReviewPolicy` it was given and puts claim text in
`focus_text` only (`repo_profile.py:73`). Profile claims are inferred prompt blocks, not
asserted instruction files (`repo_profile.py:78`). A profile cannot flip `auto_post`,
`specialist_mode`, or routing.

## 6 - ✅ Deterministic code graph

`CodeGraph.blast_radius` walks `calls` and `re_exports` edges with `EXTRACTED` confidence
(`code_graph.py:41`). The walk has a 5.0 second deadline (`code_graph.py:18`). The module
reads `graph.json`. It does not shell out to the graphify CLI (`code_graph.py:4`).

## 7 - ⚠️ Comparison on the frozen eval set

`run_retrieval_comparison` and `run_context_source_comparison` both require holdout cases
(`run_eval.py:51`, `run_eval.py:66`). They raise `BaselineBlocked` when the list is empty.
The public dataset still has one `dev` case.

No precision, recall, cost, or "useful findings per dollar" number is written here. Those
numbers were not produced.

## Design gate - ✅

✅ Retrieval spends leftover budget only. Isolation is in the SQL. Profile text cannot change
gates. The feature is off until a holdout says otherwise.

## Test gate - ⚠️ blocked on holdout

⚠️ The proof gate requires comparing no retrieval, vector-only, text-only, hybrid,
profile-only, graph-only, and profile-plus-graph on the frozen eval set, then keeping a
source only if it improves the stated quality and cost gates.

Command, run 2026-09-01 against this checkout:

```text
$ uv run python - <<'PY'
from pr_reviewer.evals.fixture_reviewer import FixtureReviewer
from pr_reviewer.evals.run_eval import (
    load_public_eval_cases,
    run_retrieval_comparison,
    run_context_source_comparison,
)
cases = load_public_eval_cases()
print("public_cases", [(c.id, c.split) for c in cases])
reviewer = FixtureReviewer.perfect()
run_retrieval_comparison(cases, reviewer, reviewer)
run_context_source_comparison(cases, reviewer, reviewer, reviewer)
PY
public_cases [('public-1', 'dev')]
run_retrieval_comparison BaselineBlocked: holdout is empty; refusing to report a retrieval comparison
run_context_source_comparison BaselineBlocked: holdout is empty; refusing to report a context-source comparison
```

No source is marked kept. No source is marked discarded. The negative result that can be
recorded tonight is that the comparison refused to run.

## Settled - ✅

- ✅ Packed diff always wins the shared budget.
- ✅ Retrieval stays disabled by default.
- ✅ Profile claims are focus text. They do not write policy.

## Open Decisions - ❓

- ❓ Which retrieval sources to keep is unanswerable until a holdout exists. Do not enable
  retrieval from this document.
