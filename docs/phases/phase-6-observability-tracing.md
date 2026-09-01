# Phase 6 - ✅ Observability and Tracing

| Mark | Means |
|---|---|
| ⬜ | Not done yet. I tick it when it lands |
| ✅ | Done, or in scope and agreed |
| ❌ | Deliberately not doing this |
| ❓ | Open decision, waiting on me |
| ⚠️ | Known trap. Read before writing the code |

**Status - ✅ TRACE PROOF GATE REPRODUCED 2026-09-01.** Master Tasks 5, 8, and 10 are ✅.
Master Tasks 18 and 20 through 22 are still marked ⬜ in the master plan; treated as done
because `9685b23`, `0869afd`, `e704cd7`, and `5a95d15` shipped them. Product-runtime
Tasks 3 through 5, 5A, and 9 are ✅. Master Task 26 stays ❌ tonight (hiring README).
Product-runtime Task 10 stays ⬜. Neither is this reconstruction gate.

## 1 - ✅ One job ID, two stores, one merge

`reconstruct_trace` (`observability/trace.py:171`) takes hosted and local halves.
None means the store has no record, not an empty list. A hosted-only or local-only
result is incomplete and names the missing origin
(`tests/test_trace_join.py`). Mismatched `trace_id` values raise
`TraceIntegrityError`.

## 2 - ✅ Order is protocol, not wall clock

Hosted `review_job_acknowledged` is placed after the local chain even when its
timestamp is earlier (`observability/trace.py:74`). Other hosted kinds default to
before the local chain. Within a store, order is the recorded sequence, not input
order. Local segments are proven. A failed hosted segment is unordered.

## 3 - ✅ Redaction never leaks a credential

Secret-like keys (`token`, `key`, `secret`, `password`, `credential`,
`authorization`, `bearer`) are stripped at every level
(`observability/trace.py:76`). Patch, source, and rationale are stripped at the
default `redacted` level. Nested local payloads are walked. Hosted payloads with
no sensitive keys pass through.

## 4 - ✅ `reviewer trace` is the reproduction command

`cli/trace.py` fetches hosted via `fetch_hosted_trace`
(`control_plane/runner_jobs.py:299`) and local via `LocalStore.fetch_trace`
(`local_store/sqlite.py:465`), then calls `reconstruct_trace`. No manual SQL.
`--json` and the human view share the same reconstruction. Unknown to both stores
is nonzero (`tests/test_trace_cli.py`). This is a support tool. The shipped runner
does not hold `DATABASE_URL`.

## 5 - ✅ Events and model calls are append-only

`record_event` (`events/record_event.py:41`) and `record_model_call`
(`events/record_model_call.py:26`) write the hosted spine. The dashboard trace
route uses the same merge (`web/dashboard_api.py:181`). A local-only list would
drop hosted lifecycle events.

## Design gate - ✅

✅ One job ID reconstructs webhook, claim, GitHub, model, decision, post, cost,
and error segments without reading secrets or unrestricted private source. The
trace spans both stores.

## Test gate - ✅ reproduced

The proof gate is: starting from one review job ID, reconstruct the review
without reading secrets. `reviewer trace <job-id>` is the reproduction command.

Command, run 2026-09-01 against this checkout:

```text
$ flock -w 3600 /tmp/pr-reviewer-pytest.lock uv run pytest -q tests/test_dashboard_auth.py::test_unauthenticated_docs_and_unknown_paths_are_not_ok tests/test_trace_join.py tests/test_trace_cli.py tests/test_events_and_models.py
...............................                                          [100%]
31 passed, 1 warning in 1.95s
```

`test_reconstructing_a_trace_from_real_storage_needs_no_manual_database_work`
is the live-storage proof. `test_cli_json_export_redacts_secret_like_keys_and_shapes_segments`
is the redaction proof. `test_unauthenticated_docs_and_unknown_paths_are_not_ok`
is the 06:11 FIX.

⚠️ Task 26 (hiring README) is forbidden tonight. This document invents no
precision, cost, or latency number.

⚠️ Runtime Task 10 is not this gate.

## Settled - ✅

- ✅ Merge lives in `observability/trace.py`. CLI and dashboard both call it.
- ✅ `HOSTED_EXEMPTIONS` stays empty.

## Open Decisions - ❓

- ❓ None for this reconstruction gate. Public deploy remains runtime Task 10.
